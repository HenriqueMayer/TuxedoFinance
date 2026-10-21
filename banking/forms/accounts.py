# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bank identities and currency-specific account forms."""

from decimal import Decimal, InvalidOperation

from django import forms
from django.utils.translation import gettext_lazy as _
from core.widgets import ColorPicker
from banking.models import Bank, BankAccount
from .base import OwnedModelForm


class BankForm(OwnedModelForm):
    class Meta:
        model = Bank
        fields = ('name', 'color')
        labels = {'name': _('Name'), 'color': _('Marker color')}
        widgets = {'color': ColorPicker()}

    def clean_color(self):
        return (self.cleaned_data.get('color') or self.instance.color or '#B88D57').upper()

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.user and self._duplicate(Bank.objects.filter(user=self.user, name=name)):
            raise forms.ValidationError(_('You already have a bank with this name.'))
        return name


class BankColorForm(BankForm):
    class Meta(BankForm.Meta):
        fields = ('color',)


class BankAccountForm(OwnedModelForm):
    class Meta:
        model = BankAccount
        fields = (
            'bank', 'name', 'currency', 'opening_balance', 'opening_date', 'pix_enabled',
            'planning_enabled', 'reserved_amount',
        )
        widgets = {
            'opening_balance': forms.NumberInput(attrs={'step': '0.01'}),
            'reserved_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
        help_texts = {
            'opening_balance': _('Money already in the account before the movements you will record.'),
            'opening_date': _('The balance applies from the start of this date, before that day\'s movements. Existing unknown dates may stay empty.'),
            'planning_enabled': _('Include this account in monthly planning. Negative balances remain visible.'),
            'reserved_amount': _('An amount in this account\'s currency to exclude from monthly planning. It stays in your bank balance and does not create a transaction.'),
        }
        labels = {
            'bank': _('Bank'),
            'name': _('Name'),
            'currency': _('Currency'),
            'opening_balance': _('Balance when tracking starts'),
            'opening_date': _('Start tracking on'),
            'pix_enabled': _('Pix enabled'),
            'planning_enabled': _('Use in monthly planning'),
            'reserved_amount': _('Keep outside monthly planning'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reserved_amount'].required = False
        if self.user is not None:
            self.fields['bank'].queryset = Bank.objects.filter(user=self.user)

    @property
    def planning_adjustments_open(self):
        # Closing a disclosure never disables its fields. Surface saved settings
        # and invalid bound input without replacing either with default values.
        if self['reserved_amount'].errors or self['planning_enabled'].errors:
            return True
        try:
            reserved = Decimal(str(self['reserved_amount'].value() or 0)) > 0
        except (InvalidOperation, ValueError):
            reserved = False
        return reserved or not self['planning_enabled'].value()

    def clean_reserved_amount(self):
        return self.cleaned_data.get('reserved_amount') or 0

    def clean(self):
        cleaned = super().clean()
        bank = cleaned.get('bank')
        name = cleaned.get('name')
        currency = cleaned.get('currency')
        if bank and name and currency and self._duplicate(
            BankAccount.objects.filter(bank=bank, name=name, currency=currency)
        ):
            self.add_error('name', _('This bank already has an account with this name and currency.'))
        if self.instance.pk:
            original = BankAccount.objects.get(pk=self.instance.pk)
            has_history = (
                original.movements.exists()
                or original.transactions.exists()
                or original.debit_cards.filter(transactions__isnull=False).exists()
                or original.credit_cards.filter(transactions__isnull=False).exists()
            )
            if has_history and currency != original.currency:
                self.add_error('currency', _('Currency cannot change after financial activity.'))
            if has_history and bank != original.bank:
                self.add_error('bank', _('The bank cannot change after financial activity.'))
            opening_date = cleaned.get('opening_date')
            if opening_date and original.movements.filter(effective_date__lt=opening_date).exists():
                self.add_error('opening_date', _('Review earlier movements before changing the opening balance date.'))
        elif cleaned.get('opening_balance') and not cleaned.get('opening_date'):
            self.add_error('opening_date', _('Enter the date of a new opening balance.'))
        return cleaned
