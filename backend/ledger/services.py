from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from banking.models import (
    BankMovement,
    CardInvoice,
    CardInvoiceCredit,
    LoyaltyEntry,
    RewardRedemption,
)
from banking.services import sync_redemption_iof_transaction
from config import clock
from ledger.models import LedgerSyncState, Transaction, attach_schedule_rows
from ledger.projection import projection_horizon, validate_occurrences
from ledger.projection_plan import build_projection_plan

ZERO = Decimal("0.00")

# Increase this number in a change that makes the synchronization derive other
# rows from unchanged inputs, for example a new due-date or settlement rule. A
# state recorded by other rules is not current: migrate synchronizes each such
# user once. Version 2 ends
# the projection horizon on the last day of its month.
LEDGER_RULES_VERSION = 2


def _sources(user):
    """Return the locked sources of the user with their R4 rows (0 to 2 more queries)."""
    items = list(
        Transaction.objects.filter(user=user)
        .with_schedule_flags()
        .select_related(
            "bank_account__bank",
            "debit_card__account__bank",
            "credit_card__account__bank",
        )
        .select_for_update()
    )
    return attach_schedule_rows(items, user_id=user.pk)


def _save_derived_changes(instance, values):
    """Keep a projection's identity and timestamp when its source is unchanged."""
    changed = []
    for field, value in values.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed.append(field)
    if changed:
        instance.save(update_fields=[*changed, "updated_at"])
    return instance


def _project_movement(user, existing, source_key, values):
    movement = existing.get(source_key)
    if movement is None:
        movement = BankMovement.objects.create(user=user, source_key=source_key, **values)
        existing[source_key] = movement
        return movement
    return _save_derived_changes(movement, values)


@dataclass(frozen=True)
class LedgerReadState:
    """What a page load knows about the derived ledger rows of its user.

    ``covered_through`` is the last date of complete derived rows: the
    ``horizon_end`` of a state recorded by the current
    ``LEDGER_RULES_VERSION``, otherwise None (no known limit). ``stale`` is
    True when the state row is missing, ``synced_on`` is null or the rules
    version is not current.
    """

    covered_through: date | None
    stale: bool


def _state_values(user_id):
    return (
        LedgerSyncState.objects.filter(user_id=user_id)
        .values_list("synced_on", "horizon_end", "rules_version")
        .first()
    )


def _is_current(state, today):
    if state is None:
        return False
    synced_on, horizon_end, rules_version = state
    # The day of the synchronization does not matter: no stored value that a
    # page reads depends on it (invoice status is calculated on read). The
    # horizon ends on a month end, so a ledger stays current until the next
    # month, a change of a ledger input or a rules change.
    return (
        synced_on is not None
        and rules_version == LEDGER_RULES_VERSION
        and horizon_end is not None
        and horizon_end >= projection_horizon(today)
    )


def ledger_is_current(user_id):
    """Return whether ``ensure_ledger_current`` would skip the synchronization (one SELECT)."""
    return _is_current(_state_values(user_id), clock.today())


def ensure_ledger_current(user):
    """Synchronize the ledger only when it is not current.

    The ledger is current when its ``LedgerSyncState`` records a
    synchronization (``synced_on`` is not null), by the current
    ``LEDGER_RULES_VERSION``, with a horizon that reaches
    ``projection_horizon(today)``. Then this call issues one SELECT and no
    write. Otherwise it calls ``sync_user_ledger(user)``. Return True when the
    call synchronized. Because the horizon ends on a month end, a ledger
    without changed inputs needs a synchronization once each month.

    The commit and sign-in triggers call it (``transactions.ledger_state``).
    The ``migrate`` trigger calls ``sync_user_ledger`` directly, because a
    state with another rules version is never current. Page loads never call
    it: they call ``read_ledger_state``.
    """
    if _is_current(_state_values(user.pk), clock.today()):
        return False
    sync_user_ledger(user)
    return True


def read_ledger_state(user):
    """Return the ``LedgerReadState`` of a page load; never write (R3 step B).

    One SELECT reads the state. When the state is stale, the read-only
    occurrence-limit check of ``sync_user_ledger`` also runs, so a source
    that the next synchronization would refuse raises
    ``ProjectionLimitExceeded``; ``LedgerProjectionMiddleware`` then redirects
    to the recovery list. A stale ledger is not synchronized here: writes,
    sign-in, ``migrate`` and ``reconcile_ledger`` do that.
    """
    state = _state_values(user.pk)
    current_rules = state is not None and state[2] == LEDGER_RULES_VERSION
    stale = state is None or state[0] is None or not current_rules
    if stale:
        _preflight(user, projection_horizon(clock.today()))
    return LedgerReadState(covered_through=state[1] if current_rules else None, stale=stale)


def mark_ledger_stale(user_id):
    """Record that the derived rows of the user may be out of date.

    One UPDATE sets ``synced_on`` to null; a user without a state row needs no
    change, because a missing state is stale too. The ledger-input signal
    receivers in ``transactions.ledger_state`` call this in the transaction
    of the change. The next ``ensure_ledger_current`` then synchronizes, and
    ``read_ledger_state`` runs its occurrence-limit check.
    """
    LedgerSyncState.objects.filter(user_id=user_id, synced_on__isnull=False).update(synced_on=None)


def _record_sync_state(user, through_date, horizon):
    # Only a synchronization as of today makes the ledger current. A
    # synchronization as of another date, for example demo seeding, leaves it
    # stale, so the next write or sign-in synchronizes as of today. Compare before
    # the write: a repeated synchronization keeps its "no unchanged writes"
    # property. This runs last, after the writes of the synchronization, which
    # can mark the ledger stale (the IOF backfill saves a Transaction).
    synced_on = through_date if through_date == clock.today() else None
    values = {"synced_on": synced_on, "horizon_end": horizon, "rules_version": LEDGER_RULES_VERSION}
    recorded = LedgerSyncState.objects.filter(user=user).values(*values).first()
    if recorded is None:
        LedgerSyncState.objects.create(user=user, **values)
    elif recorded != values:
        LedgerSyncState.objects.filter(user=user).update(**values)


def sync_user_ledger(user, through_date=None, projection_months=12):
    """Idempotently project transactions into account movements and invoices.

    The synchronization also records its date and horizon in
    ``LedgerSyncState`` (see ``ensure_ledger_current``).
    """
    through_date = through_date or clock.today()
    horizon = projection_horizon(through_date, projection_months)
    # Reject legacy/direct-ORM workloads before acquiring SQLite's writer.
    # Existing callers may already own an atomic source mutation; it rolls back
    # if this guard fails, and no derived projection is partially reconciled.
    _preflight(user, horizon)
    return _sync_user_ledger(user, through_date, horizon)


def _preflight(user, horizon):
    """Raise ``ProjectionLimitExceeded`` for a source over the occurrence limit; only read.

    Only fixed schedules can exceed the occurrence budget. This pass needs
    their calendar fields, not every account/bank object in the full history.
    """
    preflight = (
        Transaction.objects.filter(user=user, is_fixed=True)
        .select_related("credit_card")
        .only(
            "id",
            "user_id",
            "date",
            "payment_channel",
            "credit_card_id",
            "installments",
            "installment_start",
            "billing_override",
            "is_fixed",
            "fixed_until",
            "credit_card__closing_day",
        )
    )
    for item in preflight.iterator(chunk_size=500):
        validate_occurrences(item, horizon)


@transaction.atomic
def _sync_user_ledger(user, through_date, horizon):
    transactions = _sources(user)
    # Recheck locked source state before even backfilling legacy IOF expenses.
    for item in transactions:
        validate_occurrences(item, horizon)
    # Legacy sources and direct ORM imports gain the same derived expense.
    redemptions = list(
        RewardRedemption.objects.filter(
            user=user,
            iof_amount__gt=ZERO,
            iof_transaction__isnull=True,
        )
    )
    for redemption in redemptions:
        sync_redemption_iof_transaction(redemption)
    if redemptions:
        transactions = _sources(user)
    # Reconcile actual source values on every call rather than trusting a
    # timestamp cache: direct ORM imports and changes to card dates also count.
    existing_movements = {
        movement.source_key: movement
        for movement in BankMovement.objects.select_for_update()
        .filter(user=user)
        .filter(Q(source_key__startswith="transaction:") | Q(source_key__startswith="invoice:"))
    }

    loyalty_purchases = list(
        LoyaltyEntry.objects.filter(
            user=user,
            kind=LoyaltyEntry.Kind.PURCHASE,
            funding_credit_card__isnull=False,
            cash_amount__gt=ZERO,
        ).select_related("funding_credit_card")
    )
    invoice_credits = list(
        CardInvoiceCredit.objects.select_for_update()
        .filter(
            user=user,
        )
        .select_related("card__account")
    )
    existing = list(
        CardInvoice.objects.select_for_update()
        .filter(user=user)
        .select_related("card__account")
        .prefetch_related("payments")
    )
    plan = build_projection_plan(
        transactions,
        loyalty_purchases,
        invoice_credits,
        existing,
        through_date,
        horizon,
    )
    desired_keys = set(plan["transaction_movements"])
    for source_key, values in plan["transaction_movements"].items():
        _project_movement(user, existing_movements, source_key, values)
    stale_transaction_ids = [
        movement.pk
        for key, movement in existing_movements.items()
        if key.startswith("transaction:") and key not in desired_keys
    ]
    if stale_transaction_ids:
        BankMovement.objects.filter(user=user, pk__in=stale_transaction_ids).delete()

    desired_invoice_keys = set()
    for (_card_id, reference_month), target in plan["invoices"].items():
        invoice = target["invoice"]
        values = target["values"]
        if invoice is None:
            invoice = CardInvoice(
                user=user, card=target["card"], reference_month=reference_month, **values
            )
            invoice.save()
        else:
            _save_derived_changes(invoice, values)
        if target["movement_values"] is not None:
            source_key = f"invoice:{invoice.pk}"
            desired_invoice_keys.add(source_key)
            _project_movement(
                user,
                existing_movements,
                source_key,
                {**target["movement_values"], "invoice_id": invoice.pk},
            )

    stale_ids = [
        invoice.pk
        for invoice in existing
        if (invoice.card_id, invoice.reference_month) not in plan["retained_invoice_keys"]
    ]
    if stale_ids:
        BankMovement.objects.filter(user=user, invoice_id__in=stale_ids).delete()
        CardInvoice.objects.filter(user=user, pk__in=stale_ids).delete()
    stale_invoice_movement_ids = [
        movement.pk
        for key, movement in existing_movements.items()
        if key.startswith("invoice:") and key not in desired_invoice_keys
    ]
    if stale_invoice_movement_ids:
        BankMovement.objects.filter(user=user, pk__in=stale_invoice_movement_ids).delete()
    _record_sync_state(user, through_date, horizon)
