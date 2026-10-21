# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Invoice credits are owned source records, never cash or income entries."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext as _

from banking.models import CardInvoiceCredit, LoyaltyEntry

ZERO = Decimal('0.00')
PAYLOAD_FIELDS = ('card_id', 'category_id', 'title', 'amount', 'date', 'reference_month', 'notes')


def invoice_credit_totals(user, *, card_id=None, reference_month=None, as_of=None):
    """Read a native-currency total; callers must group cards/currencies."""
    credits = CardInvoiceCredit.objects.filter(user=user)
    if card_id is not None:
        credits = credits.filter(card_id=card_id)
    if reference_month is not None:
        credits = credits.filter(reference_month=reference_month)
    if as_of is not None:
        credits = credits.filter(date__lte=as_of)
    return credits.aggregate(total=Sum('amount'))['total'] or ZERO


def invoice_gross_amount(invoice):
    """Gross statement sources before separately recorded credits."""
    from transactions.models import Transaction

    month = invoice.reference_month
    purchases = Transaction.objects.filter(user_id=invoice.user_id, credit_card_id=invoice.card_id)
    amount = sum((item.amount_for_month(month.year, month.month) for item in purchases), ZERO)
    loyalty = LoyaltyEntry.objects.filter(
        user_id=invoice.user_id, kind=LoyaltyEntry.Kind.PURCHASE,
        funding_credit_card_id=invoice.card_id, cash_amount__gt=ZERO,
    ).select_related('funding_credit_card')
    return amount + sum((
        entry.cash_amount for entry in loyalty
        if entry.funding_credit_card.statement_month(entry.date) == month
    ), ZERO)


def _owned_credit(credit, user):
    if credit.user_id != user.pk:
        raise ValidationError(_('This invoice credit must belong to you.'))
    if credit.pk:
        return CardInvoiceCredit.objects.select_for_update().get(pk=credit.pk, user=user)
    return None


@transaction.atomic
def save_invoice_credit(credit, *, user):
    """Save and reconcile once; a repeated confirmation cannot duplicate credit."""
    from transactions.services import sync_user_ledger

    stored = _owned_credit(credit, user)
    # Normalize Decimal/date/UUID values before comparing repeat submissions.
    credit.full_clean(validate_unique=False)
    if stored and stored.idempotency_key != credit.idempotency_key:
        raise ValidationError(_('The invoice credit confirmation cannot be changed.'))
    if stored is None:
        previous = CardInvoiceCredit.objects.select_for_update().filter(
            idempotency_key=credit.idempotency_key,
        ).first()
        if previous:
            if previous.user_id != user.pk or any(
                getattr(previous, field) != getattr(credit, field) for field in PAYLOAD_FIELDS
            ):
                raise ValidationError(_('This credit confirmation was already used. Reload before submitting another credit.'))
            sync_user_ledger(user)
            return previous
    credit.full_clean()
    credit.save()
    sync_user_ledger(user)
    return credit


@transaction.atomic
def delete_invoice_credit(credit, *, user):
    """Remove only this owned source and rebuild its affected statements."""
    from transactions.services import sync_user_ledger

    stored = _owned_credit(credit, user)
    if stored is None:
        raise ValidationError(_('Save the invoice credit before deleting it.'))
    stored.delete()
    sync_user_ledger(user)
