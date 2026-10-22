# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import datetime, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import BankMovement, CardInvoice, CardInvoiceCredit, InvoicePayment

ZERO = Decimal('0.00')


def _statement_amount_at(invoice, through_date):
    """Exclude future credit forecasts from today's settlement evidence."""
    if not CardInvoiceCredit.objects.filter(
        user_id=invoice.user_id, card_id=invoice.card_id,
        reference_month=invoice.reference_month, date__gt=through_date,
    ).exists():
        return invoice.amount
    from banking.credits import invoice_credit_totals

    return max(ZERO, invoice.gross_amount - invoice_credit_totals(
        invoice.user, card_id=invoice.card_id,
        reference_month=invoice.reference_month, as_of=through_date,
    ))


def invoice_projection(invoice, through_date, *, statement_amount=None):
    """Manual mode is sticky for an invoice, preserving confirmed evidence."""
    manual = invoice.manual_settlement or bool(
        invoice.card.manual_settlement_from and invoice.due_date >= invoice.card.manual_settlement_from
    )
    if not manual:
        return {'status': CardInvoice.Status.PAID if invoice.due_date <= through_date else CardInvoice.Status.SCHEDULED,
                'paid_at': invoice.paid_at, 'manual_settlement': False, 'movement_amount': invoice.amount}
    if statement_amount is None:
        # Payment edits may refresh outside the source reconciliation loop.
        # A future credit is a forecast, not evidence of settlement today.
        statement_amount = _statement_amount_at(invoice, through_date)
    payments = [payment for payment in invoice.payments.all() if payment.date <= through_date] if invoice.pk else []
    paid = sum((payment.amount for payment in payments), ZERO)
    if statement_amount <= paid and (payments or statement_amount == ZERO):
        status = CardInvoice.Status.PAID
    elif paid > ZERO:
        status = CardInvoice.Status.PARTIAL
    elif invoice.due_date < through_date:
        status = CardInvoice.Status.OVERDUE
    else:
        status = CardInvoice.Status.SCHEDULED
    paid_at = timezone.make_aware(datetime.combine(max(payment.date for payment in payments), time.min)) if status == CardInvoice.Status.PAID and payments else None
    return {'status': status, 'paid_at': paid_at, 'manual_settlement': True, 'movement_amount': None}


def manual_invoice_obligations(user, as_of):
    """Outstanding obligations as of a cutoff, without inventing cash debits."""
    invoices = CardInvoice.objects.filter(user=user, manual_settlement=True).select_related('card__account__bank').prefetch_related('payments')
    rows = []
    for invoice in invoices:
        paid = sum((payment.amount for payment in invoice.payments.all() if payment.date <= as_of), ZERO)
        # Today's net statement may include credits posted after this read's
        # cutoff. Historical obligations only use credits already posted.
        invoice.remaining_amount_at_cutoff = max(ZERO, _statement_amount_at(invoice, as_of) - paid)
        # A temporary attribute avoids confusing current remaining_amount with
        # a historical or forecast cutoff selected by the caller.
        if invoice.remaining_amount_at_cutoff:
            rows.append(invoice)
    return rows


@transaction.atomic
def save_invoice_payment(payment):
    invoice = CardInvoice.objects.select_for_update().select_related('card__account').get(pk=payment.invoice_id, user_id=payment.user_id)
    payment.invoice = invoice
    if not payment.pk:
        previous = InvoicePayment.objects.filter(user_id=payment.user_id, confirmation_key=payment.confirmation_key).first()
        if previous:
            if any(getattr(previous, field) != getattr(payment, field) for field in ('invoice_id', 'account_id', 'amount', 'date', 'notes')):
                raise ValidationError(_('This confirmation was already used. Reload the invoice before submitting another payment.'))
            return previous
    payment.full_clean()
    others = invoice.payments.exclude(pk=payment.pk).aggregate(total=Sum('amount'))['total'] or ZERO
    if others + payment.amount > _statement_amount_at(invoice, timezone.localdate()):
        raise ValidationError({'amount': _('Payments cannot exceed the current invoice amount.')})
    payment.save()
    key = f'invoice-payment:{payment.pk}'
    movement, _created = BankMovement.objects.update_or_create(
        user=payment.user, source_key=key,
        defaults={'account': payment.account, 'direction': BankMovement.Direction.DEBIT,
                  'kind': BankMovement.Kind.INVOICE, 'amount': payment.amount,
                  'effective_date': payment.date, 'description': _('%(card)s confirmed invoice payment') % {'card': invoice.card.name}},
    )
    payment.movement = movement
    payment.save(update_fields=['movement', 'updated_at'])
    _refresh(invoice)
    return payment


def _refresh(invoice):
    projected = invoice_projection(invoice, timezone.localdate())
    for field in ('status', 'paid_at', 'manual_settlement'):
        setattr(invoice, field, projected[field])
    invoice.save(update_fields=['status', 'paid_at', 'manual_settlement', 'updated_at'])


@transaction.atomic
def delete_invoice_payment(payment):
    invoice = CardInvoice.objects.select_for_update().get(pk=payment.invoice_id, user_id=payment.user_id)
    movement_id = payment.movement_id
    payment.delete()
    if movement_id:
        BankMovement.objects.filter(pk=movement_id, user_id=invoice.user_id).delete()
    _refresh(invoice)
