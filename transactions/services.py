from calendar import monthrange
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import BankMovement, CardInvoice, CardInvoiceCredit, LoyaltyEntry, RewardRedemption
from transactions.models import Transaction
from transactions.projection import occurrence_months, projection_horizon, validate_occurrences
from banking.services import sync_redemption_iof_transaction
from banking.settlements import invoice_projection


ZERO = Decimal('0.00')


def _sources(user):
    return Transaction.objects.filter(user=user).select_related(
        'bank_account__bank', 'debit_card__account__bank', 'credit_card__account__bank',
    )


def _save_derived_changes(instance, values):
    """Keep a projection's identity and timestamp when its source is unchanged."""
    changed = []
    for field, value in values.items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed.append(field)
    if changed:
        instance.save(update_fields=[*changed, 'updated_at'])
    return instance


def _project_movement(user, existing, source_key, values):
    movement = existing.get(source_key)
    if movement is None:
        movement = BankMovement.objects.create(user=user, source_key=source_key, **values)
        existing[source_key] = movement
        return movement
    return _save_derived_changes(movement, values)


def sync_user_ledger(user, through_date=None, projection_months=12):
    """Idempotently project transactions into account movements and invoices."""
    through_date = through_date or timezone.localdate()
    horizon = projection_horizon(through_date, projection_months)
    # Reject legacy/direct-ORM workloads before acquiring SQLite's writer.
    # Existing callers may already own an atomic source mutation; it rolls back
    # if this guard fails, and no derived projection is partially reconciled.
    for item in _sources(user):
        validate_occurrences(item, horizon)
    return _sync_user_ledger(user, through_date, horizon)


@transaction.atomic
def _sync_user_ledger(user, through_date, horizon):
    transactions = list(_sources(user).select_for_update())
    # Recheck locked source state before even backfilling legacy IOF expenses.
    for item in transactions:
        validate_occurrences(item, horizon)
    # Legacy sources and direct ORM imports gain the same derived expense.
    redemptions = list(RewardRedemption.objects.filter(
        user=user, iof_amount__gt=ZERO, iof_transaction__isnull=True,
    ))
    for redemption in redemptions:
        sync_redemption_iof_transaction(redemption)
    if redemptions:
        transactions = list(_sources(user).select_for_update())
    # Reconcile actual source values on every call rather than trusting a
    # timestamp cache: direct ORM imports and changes to card dates also count.
    existing_movements = {
        movement.source_key: movement
        for movement in BankMovement.objects.select_for_update().filter(user=user).filter(
            Q(source_key__startswith='transaction:') | Q(source_key__startswith='invoice:')
        )
    }

    desired_keys = set()
    for item in transactions:
        if item.is_credit_card or item.reward_redemption_id:
            # Account IOF already owns an immediate redemption movement.
            continue
        occurrences = occurrence_months(item, horizon) if item.is_fixed else [item.date]
        for occurrence_month in occurrences:
            amount = item.amount_for_month(occurrence_month.year, occurrence_month.month)
            if not amount:
                continue
            effective_date = (
                item.date if not item.is_fixed
                else occurrence_month.replace(
                    day=min(item.date.day, monthrange(occurrence_month.year, occurrence_month.month)[1])
                )
            )
            if effective_date > horizon:
                continue
            source_key = f'transaction:{item.pk}:{occurrence_month:%Y-%m}'
            desired_keys.add(source_key)
            direction = (
                BankMovement.Direction.CREDIT
                if item.transaction_type == Transaction.TransactionType.INCOME
                else BankMovement.Direction.DEBIT
            )
            kind = {
                Transaction.TransactionType.INCOME: BankMovement.Kind.INCOME,
                Transaction.TransactionType.EXPENSE: BankMovement.Kind.EXPENSE,
            }[item.transaction_type]
            _project_movement(
                user, existing_movements, source_key,
                {
                    'account_id': item.payment_account.pk,
                    'direction': direction,
                    'kind': kind,
                    'amount': amount,
                    'effective_date': effective_date,
                    'description': item.title,
                    'invoice_id': None,
                    'transfer_id': None,
                },
            )
    stale_transaction_ids = [
        movement.pk for key, movement in existing_movements.items()
        if key.startswith('transaction:') and key not in desired_keys
    ]
    if stale_transaction_ids:
        BankMovement.objects.filter(user=user, pk__in=stale_transaction_ids).delete()

    credit_transactions = [item for item in transactions if item.is_credit_card]
    loyalty_purchases = list(
        LoyaltyEntry.objects.filter(
            user=user,
            kind=LoyaltyEntry.Kind.PURCHASE,
            funding_credit_card__isnull=False,
            cash_amount__gt=ZERO,
        ).select_related('funding_credit_card')
    )
    invoice_credits = list(CardInvoiceCredit.objects.select_for_update().filter(
        user=user,
    ).select_related('card__account'))
    credits_by_key = {}
    for credit in invoice_credits:
        key = (credit.card_id, credit.reference_month)
        credits_by_key[key] = credits_by_key.get(key, ZERO) + credit.amount
    computed = {}
    for item in credit_transactions:
        for reference_month in occurrence_months(item, horizon):
            amount = item.amount_for_month(reference_month.year, reference_month.month)
            if amount:
                key = (item.credit_card_id, reference_month)
                computed[key] = computed.get(key, ZERO) + amount
    for entry in loyalty_purchases:
        reference_month = entry.funding_credit_card.statement_month(entry.date)
        if reference_month <= horizon:
            key = (entry.funding_credit_card_id, reference_month)
            computed[key] = computed.get(key, ZERO) + entry.cash_amount
    for key in credits_by_key:
        if key[1] <= horizon:
            # A statement with only credit must remain discoverable, including
            # excess credit that cannot be represented as a negative bill.
            computed.setdefault(key, ZERO)

    existing = list(
        CardInvoice.objects.select_for_update().filter(user=user)
        .select_related('card__account').prefetch_related('payments')
    )
    cards = {item.credit_card_id: item.credit_card for item in credit_transactions}
    cards.update(
        {item.funding_credit_card_id: item.funding_credit_card for item in loyalty_purchases}
    )
    cards.update({credit.card_id: credit.card for credit in invoice_credits})
    for invoice in existing:
        cards[invoice.card_id] = invoice.card

    existing_by_key = {(invoice.card_id, invoice.reference_month): invoice for invoice in existing}
    # Confirmed cash evidence survives a shorter projection horizon or deletion
    # of a source purchase. Recompute its actual bill without erasing payments.
    for key, invoice in existing_by_key.items():
        if key in computed or not invoice.payments.all():
            continue
        card_id, reference_month = key
        computed[key] = sum((
            item.amount_for_month(reference_month.year, reference_month.month)
            for item in credit_transactions if item.credit_card_id == card_id
        ), ZERO) + sum((
            entry.cash_amount for entry in loyalty_purchases
            if entry.funding_credit_card_id == card_id
            and entry.funding_credit_card.statement_month(entry.date) == reference_month
        ), ZERO)
    desired_invoice_keys = set()
    for key, amount in computed.items():
        gross_amount = amount
        amount = max(ZERO, amount - credits_by_key.get(key, ZERO))
        card_id, reference_month = key
        card = cards[card_id]
        due_date = card.due_date_for(reference_month)
        invoice = existing_by_key.pop(key, None)
        if invoice is None:
            invoice = CardInvoice(user=user, card=card, reference_month=reference_month)
        # The settlement policy sees the newly calculated source total/date,
        # including a sticky manual mode and confirmed payments at the cutoff.
        original_amount, original_due_date = invoice.amount, invoice.due_date
        invoice.amount, invoice.due_date = amount, due_date
        credits_at_cutoff = sum((
            credit.amount for credit in invoice_credits
            if (credit.card_id, credit.reference_month) == key and credit.date <= through_date
        ), ZERO)
        projection = invoice_projection(
            invoice, through_date,
            statement_amount=max(ZERO, gross_amount - credits_at_cutoff),
        )
        invoice.amount, invoice.due_date = original_amount, original_due_date
        if not projection['manual_settlement']:
            # A credit posted after settlement remains a card asset; it cannot
            # retroactively reduce the bank debit made on the due date.
            credits_at_due = sum((
                credit.amount for credit in invoice_credits
                if (credit.card_id, credit.reference_month) == key and credit.date <= due_date
            ), ZERO)
            projection['movement_amount'] = max(ZERO, gross_amount - credits_at_due)
        values = {
            'due_date': due_date, 'amount': amount,
            **{field: projection[field] for field in ('status', 'paid_at', 'manual_settlement')},
        }
        if invoice.pk is None:
            for field, value in values.items():
                setattr(invoice, field, value)
            invoice.save()
        else:
            _save_derived_changes(invoice, values)
        if projection['movement_amount'] is None or projection['movement_amount'] <= ZERO:
            continue
        source_key = f'invoice:{invoice.pk}'
        desired_invoice_keys.add(source_key)
        _project_movement(
            user, existing_movements, source_key,
            {
                'account_id': card.account_id,
                'direction': BankMovement.Direction.DEBIT,
                'kind': BankMovement.Kind.INVOICE,
                'amount': projection['movement_amount'],
                'effective_date': due_date,
                'description': _('%(card_name)s invoice %(reference_month)s') % {
                    'card_name': card.name,
                    'reference_month': reference_month.strftime('%Y-%m'),
                },
                'invoice_id': invoice.pk,
                'transfer_id': None,
            },
        )

    stale_invoices = list(existing_by_key.values())
    if stale_invoices:
        stale_ids = [invoice.pk for invoice in stale_invoices]
        BankMovement.objects.filter(user=user, invoice_id__in=stale_ids).delete()
        CardInvoice.objects.filter(user=user, pk__in=stale_ids).delete()

    stale_invoice_movement_ids = [
        movement.pk for key, movement in existing_movements.items()
        if key.startswith('invoice:') and key not in desired_invoice_keys
    ]
    if stale_invoice_movement_ids:
        BankMovement.objects.filter(user=user, pk__in=stale_invoice_movement_ids).delete()
