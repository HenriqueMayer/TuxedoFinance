"""Reconciliation of an account with the bank balance.

A balance check (``BalanceCheckpoint``) records the balance that the bank
shows for an account at the end of one day.

* Tracked balance: ``banking.services.account_balance(account, as_of=date)``.
  It is the opening balance that applies on the date plus every movement of the
  account dated on or before the date, of every kind. This includes derived
  ``transaction:`` and ``invoice:`` rows, transfers, confirmed payments,
  investments, rewards and the adjustments of all checks, also the adjustment
  of the check itself. Manual invoice obligations are not subtracted: the
  tracked balance is recorded, not projected.
* Difference: statement balance minus tracked balance. It is calculated each
  time it is read. When T0 is the tracked balance without the own adjustment
  and D = S - T0, an adjustment of D gives a tracked balance of T0 + D, so the
  difference becomes 0.00. An adjustment of an earlier check also changes the
  difference of each later check of the account, because balances accumulate.
* Adjustment: a ``BankMovement`` of kind ``ADJUSTMENT`` with the source key
  ``checkpoint:<id>``, dated on the check date and without description. Only
  ``record_adjustment`` creates it, and only after the owner confirms the
  amount. It is not income or expense. Synchronization of the derived ledger
  does not load or delete it, because its key has another prefix and it has no
  invoice.
* Baseline: ``checked_difference`` and ``checked_at``. A current difference
  that is not equal to the baseline shows that the tracked balance changed
  after the check.

This module is in layer 3 and cannot import ``transactions`` or ``queries``.
Write views synchronize the ledger in the same database transaction before
they call ``record_adjustment``.
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from itertools import accumulate

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, DecimalField, F, Max, OuterRef, Subquery, Sum, When
from django.utils import timezone
from django.utils.translation import gettext

from banking.models import CHECKPOINT_KEY_PREFIX, BalanceCheckpoint, BankMovement
from banking.services import ZERO, account_balance, create_movement, opening_balance_as_of
from config import clock

CENT = Decimal("0.01")


class AlreadyAdjusted(Exception):
    """The check already has an adjustment. A view treats this as success."""


class NoDifference(Exception):
    """The current difference is 0.00, so no adjustment is necessary."""


class StaleDifference(Exception):
    """The current difference is not the difference that the owner confirmed."""

    def __init__(self, current):
        super().__init__("stale difference")
        self.current = current


@dataclass(frozen=True)
class CheckpointStatus:
    """The reconciliation state of one check, calculated when it is read.

    ``changed`` is true when ``difference`` is not equal to the baseline.
    ``last_change`` is the latest ``updated_at`` of a movement of the account,
    dated on or before the check date, that changed after the baseline. It is
    None when no such movement exists, for example when a movement was deleted
    or the opening balance changed.
    """

    checkpoint: BalanceCheckpoint
    tracked: Decimal
    difference: Decimal
    changed: bool
    last_change: datetime | None

    @property
    def checked_on(self):
        """Return the financial date of the baseline."""
        return clock.local_date(self.checkpoint.checked_at)

    @property
    def last_change_on(self):
        return clock.local_date(self.last_change) if self.last_change else None

    @property
    def needs_adjustment(self):
        return bool(self.difference) and not self.checkpoint.adjustment_id

    @property
    def opening_date_unknown(self):
        account = self.checkpoint.account
        return account.opening_date is None and account.opening_balance != ZERO


def _cents(value):
    # SQLite returns sums with more decimal places, for example
    # Decimal('44569.1000000000'). The amounts are whole cents, so this only
    # sets the exponent that the two-decimal model fields require.
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def tracked(account, on):
    """Return the tracked end-of-day balance of ``account`` on ``on``."""
    return _cents(account_balance(account, as_of=on))


def difference(checkpoint):
    """Return the statement balance minus the tracked balance of ``checkpoint``."""
    return checkpoint.statement_balance - tracked(checkpoint.account, checkpoint.date)


def _signed_amount():
    return Case(
        When(direction=BankMovement.Direction.CREDIT, then=F("amount")),
        default=-F("amount"),
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )


def _daily_totals(account_ids, through):
    """Return ``{account_id: (dates, running totals)}`` with one grouped query.

    ``dates`` is sorted. ``running totals[i]`` is the signed sum of the
    movements dated on or before ``dates[i]``.
    """
    if not account_ids:
        return {}
    rows = (
        BankMovement.objects.filter(account_id__in=account_ids, effective_date__lte=through)
        .order_by()
        .values("account_id", "effective_date")
        .annotate(total=Sum(_signed_amount()))
        .order_by("account_id", "effective_date")
    )
    grouped = {}
    for row in rows:
        dates, totals = grouped.setdefault(row["account_id"], ([], []))
        dates.append(row["effective_date"])
        totals.append(row["total"])
    return {key: (dates, list(accumulate(totals))) for key, (dates, totals) in grouped.items()}


def _tracked_from(series, account, on):
    dates, running = series.get(account.pk, ((), ()))
    index = bisect_right(dates, on)
    movements = running[index - 1] if index else ZERO
    return _cents(opening_balance_as_of(account, on) + movements)


def _last_change(checkpoint):
    return BankMovement.objects.filter(
        account_id=checkpoint.account_id,
        effective_date__lte=checkpoint.date,
        updated_at__gt=checkpoint.checked_at,
    ).aggregate(latest=Max("updated_at"))["latest"]


def _status(checkpoint, tracked_balance):
    current = checkpoint.statement_balance - tracked_balance
    changed = current != checkpoint.checked_difference
    return CheckpointStatus(
        checkpoint=checkpoint,
        tracked=tracked_balance,
        difference=current,
        changed=changed,
        last_change=_last_change(checkpoint) if changed else None,
    )


def statuses(account, checkpoints):
    """Return a ``CheckpointStatus`` for each check of ``account``, in order.

    The movement totals come from one grouped query up to the latest check
    date. A changed check needs one more query for its last change.
    """
    checkpoints = list(checkpoints)
    if not checkpoints:
        return []
    series = _daily_totals([account.pk], max(row.date for row in checkpoints))
    for row in checkpoints:
        row.account = account
    return [_status(row, _tracked_from(series, account, row.date)) for row in checkpoints]


def latest_statuses(user, account_ids):
    """Return ``{account_id: CheckpointStatus}`` of the latest check of each account.

    Accounts without a check are not in the result. The latest checks come
    from one query and the movement totals from one grouped query.
    """
    account_ids = list(account_ids)
    if not account_ids:
        return {}
    latest = BalanceCheckpoint.objects.filter(account_id=OuterRef("account_id")).order_by(
        "-date", "-pk"
    )
    checkpoints = list(
        BalanceCheckpoint.objects.filter(
            user=user,
            account__user=user,
            account_id__in=account_ids,
            pk=Subquery(latest.values("pk")[:1]),
        ).select_related("account", "adjustment")
    )
    if not checkpoints:
        return {}
    series = _daily_totals(
        [row.account_id for row in checkpoints], max(row.date for row in checkpoints)
    )
    return {
        row.account_id: _status(row, _tracked_from(series, row.account, row.date))
        for row in checkpoints
    }


def _locked(user, checkpoint_id):
    return (
        BalanceCheckpoint.objects.select_for_update()
        .select_related("account")
        .get(pk=checkpoint_id, user=user)
    )


def _set_baseline(checkpoint, value):
    checkpoint.checked_difference = value
    checkpoint.checked_at = timezone.now()


@transaction.atomic
def save_checkpoint(*, user, account, checkpoint=None, date, statement_balance, note=""):
    """Create or change a check. This never creates a movement.

    The baseline is taken on creation and when the date or the balance
    changes. While the check has an adjustment, only the note can change.
    """
    if checkpoint is None:
        checkpoint = BalanceCheckpoint(user=user, account=account)
        reset = True
    else:
        checkpoint = _locked(user, checkpoint.pk)
        if checkpoint.account_id != account.pk:
            raise ValidationError(gettext("The account must belong to the balance check owner."))
        reset = (checkpoint.date, checkpoint.statement_balance) != (date, statement_balance)
        if reset and checkpoint.adjustment_id:
            raise ValidationError(
                gettext("Remove the adjustment to change the date or the statement balance.")
            )
    checkpoint.date = date
    checkpoint.statement_balance = statement_balance
    checkpoint.note = note
    checkpoint.full_clean()
    if reset:
        _set_baseline(checkpoint, difference(checkpoint))
    checkpoint.save()
    return checkpoint


def _has_foreign_movements(user, account):
    # Same rule as the ledger reader (Q13): a movement of another owner on
    # this account makes its balance unreliable for an adjustment.
    return BankMovement.objects.filter(account=account).exclude(user=user).exists()


def parse_expected(value):
    """Return the posted expected difference as a Decimal, or None."""
    try:
        parsed = Decimal(str(value).strip())
    except ArithmeticError:
        return None
    return parsed if parsed.is_finite() else None


@transaction.atomic
def record_adjustment(*, user, checkpoint_id, expected_difference):
    """Record the adjustment that the owner confirmed, and return the movement.

    Raises ``AlreadyAdjusted`` when the check already has one,
    ``NoDifference`` when the current difference is 0.00 and
    ``StaleDifference`` when the current difference is not
    ``expected_difference``. The caller synchronizes the ledger first, in the
    same transaction.
    """
    checkpoint = _locked(user, checkpoint_id)
    if checkpoint.adjustment_id:
        raise AlreadyAdjusted
    if _has_foreign_movements(user, checkpoint.account):
        raise ValidationError(
            gettext(
                "This account has movements of another owner. Review them before you record an adjustment."
            )
        )
    current = difference(checkpoint)
    if current == ZERO:
        raise NoDifference
    if expected_difference is None or current != expected_difference:
        raise StaleDifference(current)
    if BankMovement.objects.filter(user=user, source_key=checkpoint.adjustment_key).exists():
        raise AlreadyAdjusted
    try:
        with transaction.atomic():
            movement = create_movement(
                user=user,
                account=checkpoint.account,
                direction=BankMovement.Direction.CREDIT
                if current > 0
                else BankMovement.Direction.DEBIT,
                kind=BankMovement.Kind.ADJUSTMENT,
                amount=abs(current),
                effective_date=checkpoint.date,
                description="",
                source_key=checkpoint.adjustment_key,
            )
    except IntegrityError as error:
        raise AlreadyAdjusted from error
    except ValidationError as error:
        if "amount" in getattr(error, "error_dict", {}):
            raise ValidationError(
                gettext("The difference is too large for an adjustment.")
            ) from error
        raise
    checkpoint.adjustment = movement
    _set_baseline(checkpoint, ZERO)
    checkpoint.save(update_fields=["adjustment", "checked_difference", "checked_at", "updated_at"])
    return movement


def _remove(user, checkpoint):
    movement = (
        BankMovement.objects.select_for_update()
        .filter(
            pk=checkpoint.adjustment_id,
            user=user,
            account=checkpoint.account,
            source_key=checkpoint.adjustment_key,
            kind=BankMovement.Kind.ADJUSTMENT,
        )
        .first()
    )
    if movement is None:
        raise ValidationError(gettext("The adjustment movement does not match this balance check."))
    if movement.statement_matches.exists():
        raise ValidationError(
            gettext(
                "This adjustment is linked to a bank statement import. Resolve the import before removing it."
            )
        )
    checkpoint.adjustment = None
    checkpoint.save(update_fields=["adjustment", "updated_at"])
    movement.delete()


@transaction.atomic
def remove_adjustment(*, user, checkpoint_id):
    """Delete the adjustment movement, keep the check and return the new difference."""
    checkpoint = _locked(user, checkpoint_id)
    if checkpoint.adjustment_id:
        _remove(user, checkpoint)
    current = difference(checkpoint)
    _set_baseline(checkpoint, current)
    checkpoint.save(update_fields=["checked_difference", "checked_at", "updated_at"])
    return current


@transaction.atomic
def delete_checkpoint(*, user, checkpoint_id):
    """Delete a check and its adjustment movement."""
    checkpoint = _locked(user, checkpoint_id)
    if checkpoint.adjustment_id:
        _remove(user, checkpoint)
    checkpoint.delete()


def adjustment_checkpoint_id(movement):
    """Return the check id in the source key of an adjustment movement, or None."""
    if movement.kind != BankMovement.Kind.ADJUSTMENT or not movement.source_key.startswith(
        CHECKPOINT_KEY_PREFIX
    ):
        return None
    value = movement.source_key[len(CHECKPOINT_KEY_PREFIX) :]
    return int(value) if value.isascii() and value.isdecimal() else None


__all__ = [
    "AlreadyAdjusted",
    "CheckpointStatus",
    "NoDifference",
    "StaleDifference",
    "adjustment_checkpoint_id",
    "delete_checkpoint",
    "difference",
    "latest_statuses",
    "parse_expected",
    "record_adjustment",
    "remove_adjustment",
    "save_checkpoint",
    "statuses",
    "tracked",
]
