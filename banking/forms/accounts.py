# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bank identities and currency-specific account forms."""

from django import forms
from django.utils.translation import gettext_lazy as _
from banking.models import Bank, BankAccount
from .base import OwnedModelForm


class BankForm(OwnedModelForm):
    class Meta:
        model = Bank
        fields = ('name', 'color')
        labels = {'name': _('Name'), 'color': _('Marker color')}
        widgets = {'color': forms.TextInput(attrs={'type': 'color', 'list': 'bank-color-palette'})}

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
            'opening_balance': _('Balance immediately before the first ledger movement.'),
            'opening_date': _('Balance at the start of this date, before its movements. Legacy dates may remain unknown.'),
            'planning_enabled': _('Include this account in monthly planning. Negative balances remain visible.'),
            'reserved_amount': _('Keep this amount outside planning. The account balance and history do not change.'),
        }
        labels = {
            'bank': _('Bank'),
            'name': _('Name'),
            'currency': _('Currency'),
            'opening_balance': _('Opening balance'),
            'opening_date': _('Opening balance date'),
            'pix_enabled': _('Pix enabled'),
            'planning_enabled': _('Use in monthly planning'),
            'reserved_amount': _('Reserved amount'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reserved_amount'].required = False
        if self.user is not None:
            self.fields['bank'].queryset = Bank.objects.filter(user=self.user)

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
