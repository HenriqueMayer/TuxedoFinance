# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""User-preferred calendar dates at the UI boundary; machine dates stay ISO."""
from datetime import date, datetime
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from accounts.models import UserPreference


def date_order(user=None):
    return UserPreference.for_user(user).date_format if user is not None else 'DMY'


def parse_preferred_date(value, order='DMY'):
    """Accept ISO or one unambiguous user format, never guess the other order."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value).strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value)
        if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', value):
            first, second, year = map(int, value.split('/'))
            month, day = (first, second) if order == 'MDY' else (second, first)
            return date(year, month, day)
    except ValueError:
        pass
    raise ValidationError(_('Enter a valid date.'), code='invalid')


class PreferredDateInput(forms.DateInput):
    is_preferred_date = True

    def format_value(self, value):
        # GET URLs and existing ISO POST clients remain canonical, while their
        # rendered bound controls follow the preference. Invalid text is retained.
        if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                pass
        return super().format_value(value)


def configure_date_fields(form, user=None):
    """Apply the shared input contract to DateFields on an initialized form."""
    fields = [field for field in form.fields.values() if isinstance(field, forms.DateField)]
    if not fields:
        return
    order = date_order(user)
    display = '%m/%d/%Y' if order == 'MDY' else '%d/%m/%Y'
    for field in fields:
        attrs = {key: value for key, value in field.widget.attrs.items() if key != 'type'}
        field.input_formats = [display, '%Y-%m-%d']
        field.widget = PreferredDateInput(format=display, attrs={
            **attrs,
            'placeholder': 'MM/DD/YYYY' if order == 'MDY' else 'DD/MM/YYYY',
            'inputmode': 'numeric',
            'data-date-order': order,
        })
