# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Dated net worth from actual balances, local prices and incurred card debt."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import CardInvoice, LoyaltyEntry
from banking.services import ConversionContext, MissingExchangeRate, account_balances
from investments.positions import get_portfolio_valuation
from transactions.models import Transaction

ZERO = Decimal('0.00')


def _month(value, offset):
    year, month = divmod(value.year * 12 + value.month - 1 + offset, 12)
    return date(year, month + 1, 1)


def card_debt(user, as_of):
    """Recognize a purchase's full unpaid amount, including future installments.

    Future recurrence templates are not existing debts. Confirmed payments are
    applied to their invoice; a credit after source correction stays visible.
    """
    amounts = defaultdict(lambda: ZERO)
    cards = {}
    items = Transaction.objects.filter(user=user, payment_channel='CREDIT_CARD', date__lte=as_of).select_related('credit_card__account__bank')
    for item in items:
        cards[item.credit_card_id] = item.credit_card
        if item.is_fixed:
            final_offset = (as_of.year - item.date.year) * 12 + as_of.month - item.date.month
            if item.last_fixed_offset is not None:
                final_offset = min(final_offset, item.last_fixed_offset)
            offsets = range(final_offset + 1)
        else:
            offsets = range(item.installments)
        for offset in offsets:
            reference = _month(item.billed_month, offset)
            if item.is_fixed:
                occurrence = _month(item.date, offset)
                occurrence = occurrence.replace(day=min(item.date.day, monthrange(occurrence.year, occurrence.month)[1]))
                if occurrence > as_of:
                    continue
            amounts[(item.credit_card_id, reference)] += item.amount_for_month(reference.year, reference.month)
    for entry in LoyaltyEntry.objects.filter(user=user, funding_credit_card__isnull=False, kind='PURCHASE', date__lte=as_of).select_related('funding_credit_card__account__bank'):
        card = entry.funding_credit_card
        cards[card.pk] = card
        amounts[(card.pk, card.statement_month(entry.date))] += entry.cash_amount
    invoices = list(CardInvoice.objects.filter(user=user).select_related('card__account__bank', 'settlement_movement').prefetch_related('payments'))
    indexed = {(invoice.card_id, invoice.reference_month): invoice for invoice in invoices}
    for invoice in invoices:
        cards[invoice.card_id] = invoice.card
        if invoice.manual_settlement and any(payment.date <= as_of for payment in invoice.payments.all()):
            amounts.setdefault((invoice.card_id, invoice.reference_month), ZERO)
        elif not invoice.manual_settlement and hasattr(invoice, 'settlement_movement') and invoice.settlement_movement.effective_date <= as_of:
            amounts.setdefault((invoice.card_id, invoice.reference_month), ZERO)
    rows = []
    for key, amount in amounts.items():
        card = cards[key[0]]
        invoice = indexed.get(key)
        due = card.due_date_for(key[1])
        manual = (invoice and invoice.manual_settlement) or bool(card.manual_settlement_from and due >= card.manual_settlement_from)
        if manual:
            paid = sum((payment.amount for payment in invoice.payments.all() if payment.date <= as_of), ZERO) if invoice else ZERO
        else:
            # The automatic ledger may already contain a debit before the
            # purchase date (an explicit current-bill override). Account for
            # its actual amount as card credit until the purchase is incurred.
            movement = getattr(invoice, 'settlement_movement', None) if invoice else None
            paid = movement.amount if movement and movement.effective_date <= as_of else (amount if invoice is None and due <= as_of else ZERO)
        debt = amount - paid
        if debt:
            rows.append({'card': card, 'invoice': invoice, 'reference_month': key[1], 'amount': debt, 'currency': card.account.currency})
    return rows


def wealth_snapshot(user, as_of, *, conversion=None):
    conversion = ConversionContext(user) if conversion is None else conversion.check_user(user)
    missing = set()
    bank_total = debt_total = credits_total = ZERO
    bank_rows = account_balances(user, as_of)
    unknown_banks = []
    for row in bank_rows:
        account = row['account']
        if account.opening_balance and account.opening_date is None:
            unknown_banks.append(account)
        try:
            row['base_value'] = conversion.convert(row['balance'], account.currency, as_of=as_of) if row['balance'] else ZERO
            bank_total += row['base_value']
        except MissingExchangeRate:
            row['base_value'] = None
            missing.add(account.currency)
    valuation = get_portfolio_valuation(user, as_of=as_of, historical=True, conversion=conversion)
    missing.update(valuation['missing_currencies'])
    debts = card_debt(user, as_of)
    for row in debts:
        try:
            row['base_value'] = conversion.convert(row['amount'], row['currency'], as_of=as_of)
            if row['amount'] > ZERO:
                debt_total += row['base_value']
            else:
                credits_total -= row['base_value']
        except MissingExchangeRate:
            row['base_value'] = None
            missing.add(row['currency'])
    complete = not missing and valuation['complete'] and not unknown_banks and not valuation['unknown_baselines']
    assets = bank_total + valuation['total'] + credits_total
    return {'as_of': as_of, 'currency': conversion.base_currency, 'banks': bank_rows, 'bank_total': bank_total,
            'portfolio': valuation, 'debts': debts, 'debt_total': debt_total, 'card_credits': credits_total,
            'assets_total': assets, 'net_worth': assets - debt_total, 'complete': complete,
            'missing_currencies': sorted(missing), 'unknown_banks': unknown_banks}


class WealthRangeForm(forms.Form):
    start_month = forms.DateField(label=_('Start month'), input_formats=['%Y-%m'], widget=forms.DateInput(format='%Y-%m', attrs={'type': 'month', 'class': 'planning-sheet-input'}))

    def clean_start_month(self):
        value = self.cleaned_data['start_month'].replace(day=1)
        today = timezone.localdate()
        if value > today or value < _month(today.replace(day=1), -119):
            raise forms.ValidationError(_('Choose a start month within the last ten years.'))
        return value


@login_required
def wealth_view(request):
    from transactions.services import sync_user_ledger
    sync_user_ledger(request.user)
    today = timezone.localdate()
    default = _month(today.replace(day=1), -11)
    form = WealthRangeForm(request.GET or None, initial={'start_month': default})
    start = form.cleaned_data['start_month'] if form.is_bound and form.is_valid() else default
    conversion = ConversionContext(request.user)
    series = []
    current = start
    while current <= today:
        cutoff = min(today, current.replace(day=monthrange(current.year, current.month)[1]))
        series.append(wealth_snapshot(request.user, cutoff, conversion=conversion))
        current = _month(current, 1)
    return render(request, 'dashboard/wealth.html', {'form': form, 'series': series, 'snapshot': series[-1]})
