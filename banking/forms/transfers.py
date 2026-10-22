# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owned-account transfer input."""

from django import forms
from django.utils.translation import gettext_lazy as _
from banking.models import BankAccount, BankTransfer
from .base import OwnedModelForm


class BankTransferForm(OwnedModelForm):
    class Meta:
        model = BankTransfer
        fields = (
            'source_account',
            'destination_account',
            'source_amount',
            'destination_amount',
            'date',
            'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'source_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'destination_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'destination_amount': _('For another currency, enter the amount actually received.'),
        }
        labels = {
            'source_account': _('Source account'),
            'destination_account': _('Destination account'),
            'source_amount': _('Source amount'),
            'destination_amount': _('Destination amount'),
            'date': _('Date'),
            'notes': _('Notes'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('source_account', 'destination_account'):
            self._instrument_choice(name, 'account')
        accounts = BankAccount.objects.none()
        if self.user is not None:
            accounts = BankAccount.objects.filter(user=self.user).select_related('bank')
        self.fields['source_account'].queryset = accounts
        self.fields['destination_account'].queryset = accounts
