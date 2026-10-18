# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Confirmed invoice payments and read-only invoice criteria."""

from django import forms
from django.utils.translation import gettext_lazy as _
from sandbox.forms import parse_month
from banking.models import (
    Bank,
    BankAccount,
    CardInvoice,
    InvoicePayment,
)
from .base import INPUT_CLASSES, OwnedModelForm


class InvoicePaymentForm(OwnedModelForm):
    confirmation_key = forms.UUIDField(widget=forms.HiddenInput)
    class Meta:
        model = InvoicePayment
        fields = ('account', 'amount', 'date', 'notes')
        labels = {'account': _('Payment account'), 'amount': _('Amount paid'), 'date': _('Payment date'), 'notes': _('Notes')}
        widgets = {'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}), 'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, invoice, **kwargs):
        super().__init__(*args, **kwargs)
        self._instrument_choice('account', 'account')
        self.instance.invoice = invoice
        self.initial['confirmation_key'] = self.instance.confirmation_key
        self.fields['account'].queryset = BankAccount.objects.filter(user=self.user, currency=invoice.account.currency).select_related('bank')

    def save(self, commit=True):
        payment = super().save(commit=False)
        if not payment.pk:
            payment.confirmation_key = self.cleaned_data['confirmation_key']
        if commit:
            payment.save()
        return payment


class InvoiceFilterForm(forms.Form):
    q = forms.CharField(required=False, label=_('Search'),
                        widget=forms.TextInput(attrs={'type': 'search', 'data-live-search': '', 'placeholder': _('Card, account or bank')}))
    month = forms.CharField(required=False, label=_('Invoice month'),
                            widget=forms.TextInput(attrs={'type': 'month', 'min': '1901-01', 'max': '9988-12', 'data-live-change': ''}))
    bank = forms.ModelChoiceField(required=False, queryset=Bank.objects.none(), label=_('Bank'), empty_label=_('All banks'))
    status = forms.ChoiceField(required=False, label=_('Status'), choices=[('', _('All statuses')), *CardInvoice.Status.choices])

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, auto_id='invoice-filter-%s', **kwargs)
        self.fields['bank'].queryset = Bank.objects.filter(user=user)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASSES
            if name != 'q':
                field.widget.attrs['data-live-change'] = ''
        # Keep malformed native month text recoverable after an invalid GET.
        if self.is_bound and self.errors.get('month'):
            self.fields['month'].widget = forms.TextInput(attrs={key: value for key, value in self.fields['month'].widget.attrs.items() if key != 'type'})

    def clean_month(self):
        value = self.cleaned_data['month']
        return parse_month(value) if value else None
