# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read-only investment and observed-price consultation criteria."""

from django import forms
from django.utils.translation import gettext_lazy as _
from core.dates import configure_date_fields
from core.currencies import CURRENCIES
from investments.models import Asset
from ._styles import INPUT_CLASSES


class InvestmentChartFilterForm(forms.Form):
    scope = forms.ChoiceField(
        label=_('Show positions'), required=False,
        choices=(('', _('Overall')), ('portfolio', _('Portfolio')), ('cash', _('Remunerated cash'))),
        widget=forms.Select(attrs={'class': INPUT_CLASSES, 'id': 'investment-chart-scope'}),
    )


class InvestmentOperationFilterForm(forms.Form):
    currency = forms.ChoiceField(label=_('Currency'), required=False,
        choices=[('', _('All currencies'))] + [(code, code) for code in CURRENCIES])
    asset_class = forms.ChoiceField(label=_('Asset class'), required=False,
        choices=[('', _('All asset classes'))] + list(Asset.AssetClass.choices))
    date_from = forms.DateField(label=_('From date'), required=False)
    date_to = forms.DateField(label=_('To date'), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': INPUT_CLASSES, 'id': f'investment-{name.replace("_", "-")}'})
        configure_date_fields(self, user)

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            self.add_error('date_to', _('The end date must be on or after the start date.'))
        return data


class PriceObservationFilterForm(forms.Form):
    asset = forms.ModelChoiceField(queryset=Asset.objects.none(), required=False,
        label=_('Asset'), empty_label=_('All assets'))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # Consultation includes archived assets; only new observations exclude them.
        self.fields['asset'].queryset = Asset.objects.filter(user=user)
        self.fields['asset'].widget.attrs.update({
            'id': 'investment-price-asset', 'class': INPUT_CLASSES, 'data-live-change': '',
        })
