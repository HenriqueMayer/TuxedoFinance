# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Local observed-price registration and validation."""

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from core.dates import configure_date_fields
from investments.models import Asset, PriceObservation
from ._styles import INPUT_CLASSES


class PriceObservationForm(forms.ModelForm):
    class Meta:
        model = PriceObservation
        fields = ('asset', 'date', 'unit_price', 'source')
        labels = {'asset': _('Asset')}
        widgets = {'unit_price': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        available = Q(is_archived=False)
        if self.instance.pk:
            available |= Q(pk=self.instance.asset_id)
        self.fields['asset'].queryset = Asset.objects.filter(user=user, valuation_mode=Asset.ValuationMode.UNITS).filter(available)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
        configure_date_fields(self, user)

    def clean(self):
        data = super().clean()
        if data.get('asset') and data.get('date'):
            matching = PriceObservation.objects.filter(asset=data['asset'], date=data['date'])
            if self.instance.pk:
                matching = matching.exclude(pk=self.instance.pk)
            if matching.exists():
                self.add_error('date', _('A price exists for this asset and date. Edit that observation instead.'))
        return data
