from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import BankMovement, CardInvoice, LoyaltyEntry, RewardRedemption
from transactions.models import Transaction


ZERO = Decimal('0.00')


def _add_months(value, offset, day=None):
    index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(index, 12)
    month += 1
    target_day = value.day if day is None else day
    return date(year, month, min(target_day, monthrange(year, month)[1]))


def _month_range(start, end):
    current = start.replace(day=1)
    end = end.replace(day=1)
    while current <= end:
        yield current
        current = _add_months(current, 1)


@transaction.atomic
def sync_user_ledger(user, through_date=None, projection_months=12):
    """Idempotently project transactions into account movements and invoices."""
    through_date = through_date or timezone.localdate()
    horizon = _add_months(through_date, projection_months)
    transactions = list(
        Transaction.objects.select_for_update()
        .filter(user=user)
        .select_related(
            'bank_account__bank', 'debit_card__account__bank',
            'credit_card__account__bank'
        )
    )

    desired_keys = set()
    for item in transactions:
        if item.is_credit_card:
            continue
        occurrences = _month_range(item.date, horizon) if item.is_fixed else [item.date]
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
            BankMovement.objects.update_or_create(
                user=user,
                source_key=source_key,
                defaults={
                    'account': item.payment_account,
                    'direction': direction,
                    'kind': kind,
                    'amount': amount,
                    'effective_date': effective_date,
                    'description': item.title,
                    'invoice': None,
                    'transfer': None,
                },
            )
    BankMovement.objects.filter(user=user, source_key__startswith='transaction:').exclude(
        source_key__in=desired_keys
    ).delete()

    credit_transactions = [item for item in transactions if item.is_credit_card]
    redemptions = list(
        RewardRedemption.objects.filter(
            user=user, iof_credit_card__isnull=False, iof_amount__gt=ZERO
        ).select_related('iof_credit_card')
    )
    loyalty_purchases = list(
        LoyaltyEntry.objects.filter(
            user=user,
            kind=LoyaltyEntry.Kind.PURCHASE,
            funding_credit_card__isnull=False,
            cash_amount__gt=ZERO,
        ).select_related('funding_credit_card')
    )
    first_months = [item.billed_month for item in credit_transactions if item.billed_month]
    first_months.extend(
        redemption.iof_credit_card.statement_month(redemption.date)
        for redemption in redemptions
    )
    first_months.extend(
        entry.funding_credit_card.statement_month(entry.date)
        for entry in loyalty_purchases
    )
    computed = {}
    if first_months:
        first_month = min(first_months)
        for reference_month in _month_range(first_month, horizon):
            for item in credit_transactions:
                amount = item.amount_for_month(reference_month.year, reference_month.month)
                if amount:
                    computed[(item.credit_card_id, reference_month)] = (
                        computed.get((item.credit_card_id, reference_month), ZERO) + amount
                    )
            for redemption in redemptions:
                card = redemption.iof_credit_card
                if card.statement_month(redemption.date) == reference_month:
                    computed[(card.pk, reference_month)] = (
                        computed.get((card.pk, reference_month), ZERO)
                        + redemption.iof_amount
                    )
            for entry in loyalty_purchases:
                card = entry.funding_credit_card
                if card.statement_month(entry.date) == reference_month:
                    computed[(card.pk, reference_month)] = (
                        computed.get((card.pk, reference_month), ZERO)
                        + entry.cash_amount
                    )

    existing = list(
        CardInvoice.objects.select_for_update().filter(user=user).select_related('card__account')
    )
    cards = {item.credit_card_id: item.credit_card for item in credit_transactions}
    cards.update({item.iof_credit_card_id: item.iof_credit_card for item in redemptions})
    cards.update(
        {item.funding_credit_card_id: item.funding_credit_card for item in loyalty_purchases}
    )
    for invoice in existing:
        cards[invoice.card_id] = invoice.card

    existing_by_key = {(invoice.card_id, invoice.reference_month): invoice for invoice in existing}
    for key, amount in computed.items():
        card_id, reference_month = key
        card = cards[card_id]
        due_date = card.due_date_for(reference_month)
        invoice, created = CardInvoice.objects.update_or_create(
            card_id=card_id,
            reference_month=reference_month,
            defaults={
                'user': user,
                'due_date': due_date,
                'amount': amount,
                'status': (
                    CardInvoice.Status.PAID
                    if due_date <= through_date
                    else CardInvoice.Status.SCHEDULED
                ),
            },
        )
        BankMovement.objects.update_or_create(
            user=user,
            source_key=f'invoice:{invoice.pk}',
            defaults={
                'account': card.account,
                'direction': BankMovement.Direction.DEBIT,
                'kind': BankMovement.Kind.INVOICE,
                'amount': amount,
                'effective_date': due_date,
                'description': _('%(card_name)s invoice %(reference_month)s') % {
                    'card_name': card.name,
                    'reference_month': reference_month.strftime('%Y-%m'),
                },
                'invoice': invoice,
                'transfer': None,
            },
        )
        existing_by_key.pop(key, None)

    stale_invoices = list(existing_by_key.values())
    if stale_invoices:
        stale_ids = [invoice.pk for invoice in stale_invoices]
        BankMovement.objects.filter(user=user, invoice_id__in=stale_ids).delete()
        CardInvoice.objects.filter(pk__in=stale_ids).delete()

    valid_invoice_keys = {f'invoice:{invoice.pk}' for invoice in CardInvoice.objects.filter(user=user)}
    BankMovement.objects.filter(user=user, source_key__startswith='invoice:').exclude(
        source_key__in=valid_invoice_keys
    ).delete()
