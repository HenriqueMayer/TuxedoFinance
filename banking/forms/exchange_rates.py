# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Exchange-rate evidence and read-only rate criteria."""

from django import forms
from django.utils.translation import gettext_lazy as _
from core.dates import configure_date_fields
from banking.models import ExchangeRate
from .base import INPUT_CLASSES, OwnedModelForm


class ExchangeRateForm(OwnedModelForm):
    def clean(self):
        cleaned = super().clean()
        pair_date = {field: cleaned.get(field) for field in (
            'from_currency', 'to_currency', 'effective_date',
        )}
        if self.user and all(pair_date.values()) and self._duplicate(
            ExchangeRate.objects.filter(user=self.user, **pair_date)
        ):
            raise forms.ValidationError(_('A record with these values already exists.'))
        return cleaned

    class Meta:
        model = ExchangeRate
        fields = ('from_currency', 'to_currency', 'rate', 'effective_date', 'notes')
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'rate': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'}),
        }
        help_texts = {'rate': _('How many target-currency units equal one source unit.')}
        labels = {
            'from_currency': _('From currency (1 unit)'),
            'to_currency': _('To currency'),
            'rate': _('Value in the target currency'),
            'effective_date': _('Effective date'),
            'notes': _('Notes'),
        }


class ExchangeRateFilterForm(forms.Form):
    q = forms.CharField(required=False, label=_('Search'),
                        widget=forms.TextInput(attrs={'type': 'search', 'data-live-search': '', 'placeholder': _('Currency or notes')}))
    from_currency = forms.ChoiceField(required=False, label=_('From currency (1 unit)'), choices=[('', _('All currencies')), *ExchangeRate._meta.get_field('from_currency').choices])
    to_currency = forms.ChoiceField(required=False, label=_('To currency'), choices=[('', _('All currencies')), *ExchangeRate._meta.get_field('to_currency').choices])
    date_from = forms.DateField(required=False, label=_('From date'))
    date_to = forms.DateField(required=False, label=_('To date'))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, auto_id='rate-filter-%s', **kwargs)
        configure_date_fields(self, user)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASSES
            if name != 'q':
                field.widget.attrs['data-live-change'] = ''

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            self.add_error('date_to', _('Choose an end date on or after the start date.'))
        return data
