# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Loyalty programs, points entries and reward redemptions."""

from django import forms
from django.utils.translation import gettext_lazy as _
from banking.models import (
    Bank,
    BankAccount,
    CardInvoice,
    CreditCard,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from .base import OwnedModelForm


class LoyaltyProgramForm(OwnedModelForm):
    class Meta:
        model = LoyaltyProgram
        fields = ('name', 'bank', 'cards', 'unit_name')
        widgets = {'cards': forms.SelectMultiple(attrs={'size': '6'})}
        help_texts = {
            'bank': _('Optional. Independent programs may have no bank.'),
            'cards': _('Optional. Select one or more eligible credit cards.'),
        }
        labels = {
            'name': _('Name'),
            'bank': _('Bank'),
            'cards': _('Cards'),
            'unit_name': _('Unit name'),
        }

    def __init__(self, *args, **kwargs):
        self.locked_bank = kwargs.pop('locked_bank', None)
        super().__init__(*args, **kwargs)
        self._instrument_choice('cards', 'card')
        if self.user is not None:
            self.fields['bank'].queryset = Bank.objects.filter(user=self.user)
            cards = CreditCard.objects.filter(user=self.user).select_related('account__bank')
            if self.locked_bank is not None:
                self.fields['bank'].queryset = self.fields['bank'].queryset.filter(
                    pk=self.locked_bank.pk
                )
                self.fields['bank'].initial = self.locked_bank.pk
                self.fields['bank'].disabled = True
                cards = cards.filter(account__bank=self.locked_bank)
            bank_value = self.data.get('bank') if self.is_bound else None
            if not bank_value:
                bank_value = (
                    self.locked_bank
                    or self.initial.get('bank')
                    or self.instance.bank_id
                )
            if hasattr(bank_value, 'pk'):
                bank_value = bank_value.pk
            if bank_value:
                bank = Bank.objects.filter(pk=bank_value, user=self.user).first()
                if bank is not None:
                    cards = cards.filter(account__bank=bank)
            self.fields['cards'].queryset = cards

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.user and self._duplicate(
            LoyaltyProgram.objects.filter(user=self.user, name=name)
        ):
            raise forms.ValidationError(_('You already have a loyalty program with this name.'))
        return name

    def clean_cards(self):
        cards = self.cleaned_data['cards']
        if self.user is not None and cards.exclude(user=self.user).exists():
            raise forms.ValidationError(_('Every card must belong to you.'))
        bank = self.cleaned_data.get('bank')
        if bank and cards.exclude(account__bank=bank).exists():
            raise forms.ValidationError(_('Every selected card must belong to the selected bank.'))
        return cards

    def clean_bank(self):
        bank = self.cleaned_data.get('bank')
        if self.locked_bank is not None and bank != self.locked_bank:
            raise forms.ValidationError(_('The program must belong to the selected bank.'))
        return bank


class LoyaltyEntryForm(OwnedModelForm):
    class Meta:
        model = LoyaltyEntry
        fields = (
            'program',
            'direction',
            'kind',
            'amount',
            'date',
            'invoice',
            'funding_account',
            'funding_credit_card',
            'cash_amount',
            'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'cash_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'program': _('Program'),
            'direction': _('Direction'),
            'kind': _('Kind'),
            'amount': _('Points or miles'),
            'date': _('Date'),
            'invoice': _('Invoice'),
            'funding_account': _('Funding account'),
            'funding_credit_card': _('Funding credit card'),
            'cash_amount': _('Amount paid'),
            'notes': _('Notes'),
        }
        help_texts = {
            'invoice': _('Required only for points awarded from a selected credit-card invoice.'),
            'funding_account': _('For purchased points, choose this or a credit card.'),
            'cash_amount': _('Required only when purchasing points.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instrument_choice('funding_account', 'account')
        for name in ('funding_credit_card', 'invoice'):
            self._instrument_choice(name, 'card')
        if self.user is not None:
            self.fields['program'].queryset = LoyaltyProgram.objects.filter(user=self.user)
            self.fields['invoice'].queryset = CardInvoice.objects.filter(
                user=self.user
            ).select_related('card__account__bank').order_by('-reference_month')
            self.fields['funding_account'].queryset = BankAccount.objects.filter(
                user=self.user
            ).select_related('bank')
            self.fields['funding_credit_card'].queryset = CreditCard.objects.filter(
                user=self.user
            ).select_related('account__bank')


class RewardRedemptionForm(OwnedModelForm):
    class Meta:
        model = RewardRedemption
        fields = (
            'program',
            'points',
            'target_account',
            'target_amount',
            'iof_amount',
            'iof_account',
            'iof_credit_card',
            'date',
            'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'points': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'target_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'iof_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'target_amount': _('Money credited in the target account currency.'),
            'iof_amount': _('If positive, choose exactly one account or credit card below.'),
        }
        labels = {
            'program': _('Program'),
            'points': _('Points'),
            'target_account': _('Target account'),
            'target_amount': _('Target amount'),
            'iof_amount': _('Iof amount'),
            'iof_account': _('Iof account'),
            'iof_credit_card': _('Iof credit card'),
            'date': _('Date'),
            'notes': _('Notes'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('target_account', 'iof_account'):
            self._instrument_choice(name, 'account')
        self._instrument_choice('iof_credit_card', 'card')
        if self.user is not None:
            self.fields['program'].queryset = LoyaltyProgram.objects.filter(user=self.user)
            accounts = BankAccount.objects.filter(user=self.user).select_related('bank')
            self.fields['target_account'].queryset = accounts
            self.fields['iof_account'].queryset = accounts
            self.fields['iof_credit_card'].queryset = CreditCard.objects.filter(
                user=self.user
            ).select_related('account__bank')
