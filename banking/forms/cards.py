# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Debit and credit card settings and appearance."""

import re
from django import forms
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from core.widgets import ColorPicker
from banking.models import BankAccount, CreditCard, DebitCard
from .base import OwnedModelForm


class CardForm(OwnedModelForm):
    use_gradient = forms.BooleanField(required=False, label=_('Use a gradient'))
    is_card_form = True
    appearance_fields = ('color', 'use_gradient', 'gradient_end', 'gradient_angle')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instrument_choice('account', 'account')
        if self.user is not None:
            self.fields['account'].queryset = BankAccount.objects.filter(
                user=self.user
            ).select_related('bank')
        self.appearance_submitted = self.is_bound and any(
            self.add_prefix(name) in self.data for name in self.appearance_fields
        )
        # Presets are shortcuts, never an enum: custom HEX colors work on both
        # create and edit, while the model remains the validation authority.
        self.fields['color'].required = False
        self.fields['color'].label = _('Card color')
        self.fields['color'].widget = ColorPicker()
        self.fields['gradient_end'].label = _('Gradient end color')
        self.fields['gradient_end'].widget = ColorPicker(presets=False)
        self.fields['gradient_angle'].label = _('Gradient angle')
        self.fields['gradient_angle'].required = False
        self.fields['gradient_angle'].widget.attrs.update({'min': 0, 'max': 359, 'step': 1})
        self.initial['use_gradient'] = bool(self.instance.gradient_end)
        self.initial['gradient_end'] = self.instance.gradient_end or self.instance.color
        self.fields['use_gradient'].widget.attrs['class'] = 'card-gradient-toggle'

    @property
    def card_record_fields(self):
        return [self[name] for name in self.fields if name not in self.appearance_fields]

    @property
    def card_preview_color(self):
        value = self['color'].value() or self.instance.color
        return value.upper() if re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)) else '#253330'

    @property
    def card_preview_end(self):
        if 'use_gradient' not in self.fields or not self['use_gradient'].value():
            return self.card_preview_color
        value = self['gradient_end'].value() or ''
        return value.upper() if re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)) else self.card_preview_color

    @property
    def card_preview_angle(self):
        try:
            value = int(self['gradient_angle'].value()) if 'gradient_angle' in self.fields else 135
        except (TypeError, ValueError):
            return 135
        return value if 0 <= value <= 359 else 135

    def clean_color(self):
        return (self.cleaned_data.get('color') or self.instance.color or '#253330').upper()

    def clean_gradient_angle(self):
        value = self.cleaned_data.get('gradient_angle')
        return self.instance.gradient_angle if value is None else value

    def clean(self):
        cleaned = super().clean()
        if not self.appearance_submitted:
            # Older integrations may still post the original financial form.
            cleaned['gradient_end'] = self.instance.gradient_end
            cleaned['gradient_angle'] = self.instance.gradient_angle
        elif not cleaned.get('use_gradient'):
            # Ignore inactive presentation inputs on create and edit, while
            # keeping native fields available after an invalid POST without JS.
            self._errors.pop('gradient_end', None)
            self._errors.pop('gradient_angle', None)
            cleaned['gradient_end'] = ''
            cleaned['gradient_angle'] = self.instance.gradient_angle
        elif not cleaned.get('gradient_end'):
            self.add_error('gradient_end', _('Choose a gradient end color.'))
        else:
            cleaned['gradient_end'] = cleaned['gradient_end'].upper()
        account = cleaned.get('account')
        name = cleaned.get('name')
        if account and name and self._duplicate(
            self._meta.model.objects.filter(account=account, name=name)
        ):
            self.add_error('name', _('This account already has a card with this name.'))
        if self.instance.pk and account:
            original = self._meta.model.objects.get(pk=self.instance.pk)
            has_history = original.transactions.exists()
            if isinstance(original, CreditCard):
                has_history = has_history or original.invoices.exists()
            if has_history and account != original.account:
                self.add_error('account', _('The account cannot change after card activity.'))
        return cleaned


class DebitCardForm(CardForm):
    class Meta:
        model = DebitCard
        fields = ('account', 'name', 'color', 'gradient_end', 'gradient_angle')
        labels = {'account': _('Account'), 'name': _('Name')}


class CreditCardForm(CardForm):
    class Meta:
        model = CreditCard
        fields = ('account', 'name', 'card_type', 'closing_day', 'due_day', 'manual_settlement_from', 'color', 'gradient_end', 'gradient_angle')
        widgets = {
            'closing_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
            'due_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
        }
        help_texts = {
            'closing_day': _('Purchases on or after this day enter the next statement.'),
            'due_day': _('Clamped to the last day in shorter months.'),
            'manual_settlement_from': format_lazy('{} {}', CreditCard._meta.get_field('manual_settlement_from').help_text, _('Existing confirmed invoices keep their mode if this date is changed or cleared.')),
        }
        labels = {
            'account': _('Account'),
            'name': _('Name'),
            'card_type': _('Card type'),
            'closing_day': _('Closing day'),
            'due_day': _('Due day'),
            'manual_settlement_from': _('Confirm payments from'),
        }

    def clean_manual_settlement_from(self):
        value = self.cleaned_data.get('manual_settlement_from')
        original = CreditCard.objects.filter(pk=self.instance.pk).values_list('manual_settlement_from', flat=True).first() if self.instance.pk else None
        if value and value != original and value < timezone.localdate():
            raise forms.ValidationError(_('Choose today or a future date to preserve historical automatic payments.'))
        return value
