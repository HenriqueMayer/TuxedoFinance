# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from categories.models import Category
from core.dates import configure_date_fields
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalSettings
from planning.services import goal_sources, validate_allocation
from sandbox.forms import parse_month

INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-hidden focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)
CHECKBOX_CLASSES = 'h-5 w-5 rounded-md border-forest/20 accent-caramel focus:outline-hidden focus:ring-2 focus:ring-caramel/30'


def style_fields(form):
    for name, field in form.fields.items():
        field.widget.attrs['class'] = CHECKBOX_CLASSES if isinstance(field.widget, forms.CheckboxInput) else INPUT_CLASSES
        if isinstance(field, forms.DecimalField):
            field.widget = forms.TextInput(attrs={**field.widget.attrs, 'inputmode': 'decimal'})
        if form.is_bound and form.errors.get(name):
            field.widget.attrs['aria-invalid'] = 'true'
            if getattr(field.widget, 'input_type', None) == 'month':
                # Native month widgets drop invalid bound text instead of allowing recovery.
                field.widget = forms.TextInput(attrs={key: value for key, value in field.widget.attrs.items() if key != 'type'})


class MonthForm(forms.Form):
    month = forms.CharField(label=_('Month'), widget=forms.TextInput(attrs={'type': 'month', 'min': '1901-01', 'max': '9988-12'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault('month', timezone.localdate().strftime('%Y-%m'))
        style_fields(self)

    def clean_month(self):
        return parse_month(self.cleaned_data['month'])


class CategoryBudgetForm(forms.ModelForm):
    month = forms.CharField(label=_('Month'), widget=forms.TextInput(attrs={'type': 'month', 'min': '1901-01', 'max': '9988-12'}))

    class Meta:
        model = CategoryBudget
        fields = ['month', 'category', 'currency', 'amount']
        labels = {'category': _('Category'), 'currency': _('Currency')}
        help_texts = {'category': _('Includes subcategories. Overlapping budgets in the same month and currency are not allowed.')}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        self.fields['category'].queryset = Category.objects.filter(user=user).filter(Q(transaction_type='EXPENSE') | Q(transaction_type__isnull=True) | Q(transaction_type='')).select_related('parent_category')
        self.fields['category'].empty_label = _('Select a category')
        if self.instance.pk:
            self.initial['month'] = self.instance.month.strftime('%Y-%m')
        else:
            self.initial.setdefault('month', timezone.localdate().strftime('%Y-%m'))
        style_fields(self)

    def clean_month(self):
        return parse_month(self.cleaned_data['month'])


class FinancialGoalForm(forms.ModelForm):
    class Meta:
        model = FinancialGoal
        fields = ['name', 'target_amount', 'currency', 'target_date']
        help_texts = {'target_date': _('Optional deadline. Progress comes only from balances explicitly reserved for this goal.')}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        configure_date_fields(self, user)
        style_fields(self)


class GoalAllocationForm(forms.Form):
    source = forms.ChoiceField(label=_('Cash source'), choices=[], widget=forms.Select(attrs={'data-search-select': '', 'data-search-id': 'source-search'}))
    amount = forms.DecimalField(label=_('Reserved amount'), max_digits=16, decimal_places=2, min_value=Decimal('0.01'), help_text=_('Amount in the source currency. This names part of the existing balance; it does not transfer money.'))

    def __init__(self, *args, user, goal, instance=None, **kwargs):
        self.instance = instance or GoalAllocation(user=user, goal=goal)
        self.user = user
        self.goal = goal
        self.sources = goal_sources(user)
        super().__init__(*args, **kwargs)
        self.fields['source'].choices = [('', _('Select a cash source'))] + [
            (key, f"{source['label']} · {source['currency']} {source['balance']:.2f}")
            for key, source in self.sources.items()
        ]
        if self.instance.pk and self.instance.source_key not in self.sources:
            # An existing reservation stays editable when its pot no longer
            # appears in the current ledger; server validation still rejects funding it.
            self.fields['source'].choices.append((self.instance.source_key, self.instance.source_label))
        if self.instance.pk:
            self.initial.update(source=self.instance.source_key, amount=self.instance.amount)
        style_fields(self)

    def clean(self):
        cleaned = super().clean()
        source = self.sources.get(cleaned.get('source'))
        if source and cleaned.get('amount') is not None:
            self.instance.user = self.user
            self.instance.goal = self.goal
            self.instance.bank_account = source['account']
            self.instance.product = source['product']
            self.instance.asset = source['asset']
            self.instance.amount = cleaned['amount']
            try:
                self.instance.full_clean()
                validate_allocation(self.instance, sources=self.sources)
            except ValidationError as error:
                self.add_error(None, '\n'.join(error.messages))
        elif cleaned.get('source'):
            self.add_error('source', _('This cash source is unavailable.'))
        return cleaned


class SignalSettingsForm(forms.ModelForm):
    class Meta:
        model = SignalSettings
        exclude = ['user']
        help_texts = {
            'duplicates_enabled': _('Same amount, description, currency and payment instrument. Always requires your review.'),
            'subscriptionincrease_enabled': _('Compares two recorded expenses 20–45 days apart; a recurring template has no past price history.'),
            'futurecashshortage_enabled': _('Uses recorded future bank movements and unpaid confirmed-mode invoices. Unrecorded income and cash-pot withdrawals are not assumed.'),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.user = user
        style_fields(self)
