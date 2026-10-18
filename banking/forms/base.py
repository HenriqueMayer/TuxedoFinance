# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Shared owner-scoped fields and payment-instrument presentation."""

from django import forms
from core.dates import configure_date_fields
from core.widgets import SelectWithMetadata, SelectMultipleWithMetadata
from banking.models import CardInvoice


INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-hidden focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)


class OwnedModelForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        configure_date_fields(self, user)
        if user is not None:
            self.instance.user = user
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES

    def _instrument_choice(self, name, kind):
        field = self.fields[name]
        widget_class = SelectMultipleWithMetadata if isinstance(field, forms.ModelMultipleChoiceField) else SelectWithMetadata
        widget = widget_class(attrs={**field.widget.attrs,
            'data-payment-choices': 'true', 'data-payment-kind': kind})

        def card_label(card):
            return f'{card.name} - {card.account.bank.name} > {card.account.name} ({card.account.currency})'

        def metadata(record):
            if kind == 'account':
                return {'data-choice-name': record.name,
                    'data-choice-detail': f'{record.bank.name} · {record.currency}',
                    'data-bank-color': record.bank.color}
            card = record.card if isinstance(record, CardInvoice) else record
            period = f' · {record.reference_month:%Y-%m}' if isinstance(record, CardInvoice) else ''
            return {'data-choice-name': card.name + period,
                'data-choice-detail': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})',
                'data-bank-color': card.account.bank.color,
                'data-card-color': card.color,
                'data-card-gradient-end': card.gradient_end,
                'data-card-gradient-angle': str(card.gradient_angle)}

        if kind == 'card':
            field.label_from_instance = lambda record: (
                f'{card_label(record.card)} · {record.reference_month:%Y-%m}'
                if isinstance(record, CardInvoice) else card_label(record))
        widget.choice_data = metadata
        widget.choices = field.choices
        field.widget = widget

    def _duplicate(self, queryset):
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        return queryset.exists()
