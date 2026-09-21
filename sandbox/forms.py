from decimal import Decimal, InvalidOperation
from datetime import date
from itertools import zip_longest

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from sandbox.services import BudgetInput, CltScenario, CustomVariable


INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-none focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)
CHECKBOX_CLASSES = (
    'h-5 w-5 rounded-md border-forest/20 bg-white accent-caramel '
    'focus:outline-none focus:ring-2 focus:ring-caramel/30 dark:border-cream/20 dark:bg-night'
)


def decimal_field(label, *, initial=Decimal('0'), min_value=Decimal('0'), help_text=''):
    return forms.DecimalField(
        label=label,
        required=False,
        initial=initial,
        min_value=min_value,
        max_digits=14,
        decimal_places=2,
        help_text=help_text,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': str(min_value)}),
    )


class SalarySandboxForm(forms.Form):
    planning_month = forms.CharField(label=_('Planning month'), required=False,
                                    widget=forms.TextInput(attrs={'placeholder': 'YYYY-MM', 'inputmode': 'numeric'}))
    expense_basis = forms.ChoiceField(label=_('Expense basis'), required=False, initial='free', choices=(
        ('free', _('Free estimate')), ('recorded', _('Recorded commitments')),
    ))
    gross_salary = decimal_field(
        _('Gross monthly salary'),
        initial=None,
        min_value=Decimal('0.01'),
        help_text=_('Monthly salary before any automatic or manually entered deductions.'),
    )
    use_clt = forms.BooleanField(
        label=_('Calculate CLT deductions automatically'),
        required=False,
        initial=False,
        help_text=_('Uses the official 2026 INSS and IRRF rules and includes vacation, 13th salary and FGTS.'),
    )
    dependents = forms.IntegerField(
        label=_('Dependents'),
        required=False,
        initial=0,
        min_value=0,
        max_value=20,
        help_text=_('Legal dependents considered when choosing the most favorable monthly IRRF deduction.'),
    )
    pension = decimal_field(_('Court-ordered pension'), help_text=_('Monthly amount deductible from IRRF.'))
    vt_enabled = forms.BooleanField(
        label=_('Receive transport voucher'),
        required=False,
        help_text=_('Limits the payroll deduction to 6% of salary or the actual transport cost, whichever is lower.'),
    )
    vt_cost = decimal_field(
        _('Actual monthly transport cost'),
        help_text=_('Monthly public-transport cost supplied by the employer.'),
    )
    food_employee = decimal_field(
        _('Food benefit employee share'),
        help_text=_('Amount deducted from payroll for meal or food benefits.'),
    )
    health_employee = decimal_field(
        _('Health plan employee share'),
        help_text=_('Monthly plan fee or copayment deducted from payroll.'),
    )
    other_deductions = decimal_field(
        _('Other payroll deductions'),
        help_text=_('Other recurring amounts deducted directly from the employee.'),
    )

    fixed_cost_type = forms.ChoiceField(
        label=_('Fixed costs unit'),
        required=False,
        choices=(('percent', '%'), ('currency', 'R$')),
        initial='percent',
    )
    fixed_cost_value = decimal_field(
        _('Fixed costs target'),
        initial=Decimal('50.00'),
        help_text=_(
            'Choose a percentage of monthly net income or a fixed amount in reais. '
            'The result shows the amount and its equivalent percentage.'
        ),
    )
    emergency_percent = decimal_field(
        _('Emergency reserve target (%)'),
        initial=Decimal('10.00'),
        help_text=_('Share of monthly net income set aside for an emergency fund.'),
    )
    investments_percent = decimal_field(
        _('Investments target (%)'),
        initial=Decimal('20.00'),
        help_text=_('Share of monthly net income allocated to investments.'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = CHECKBOX_CLASSES if isinstance(field.widget, forms.CheckboxInput) else INPUT_CLASSES
            field.widget.attrs.setdefault('autocomplete', 'off')
            if field.help_text:
                field.widget.attrs['aria-describedby'] = f'id_{name}-help'
            if self.is_bound and self.errors.get(name):
                field.widget.attrs['aria-invalid'] = 'true'
                if isinstance(field, (forms.DecimalField, forms.IntegerField)):
                    field.widget = forms.TextInput(attrs={**field.widget.attrs, 'inputmode': 'decimal'})
        self.fields['use_clt'].widget.attrs['data-use-clt'] = ''
        self.fields['fixed_cost_type'].widget.attrs['aria-label'] = _('Fixed costs unit')
        self.fields['fixed_cost_type'].widget.attrs['aria-describedby'] = 'id_fixed_cost_value-help'
        if not self.is_bound:
            self.initial.setdefault('planning_month', timezone.localdate().strftime('%Y-%m'))

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('gross_salary'):
            self.add_error('gross_salary', _('Enter the gross monthly salary.'))
        if cleaned.get('expense_basis') != 'recorded' and cleaned.get('fixed_cost_type') == 'percent' and _value(cleaned, 'fixed_cost_value') > Decimal('100'):
            self.add_error('fixed_cost_value', _('Enter a percentage from 0 to 100.'))
        for name in ('emergency_percent', 'investments_percent'):
            if _value(cleaned, name) > Decimal('100'):
                self.add_error(name, _('Enter a percentage from 0 to 100.'))
        try:
            cleaned['planning_month'] = parse_month(cleaned.get('planning_month') or timezone.localdate().strftime('%Y-%m'))
        except ValidationError as error:
            self.add_error('planning_month', error)
        cleaned['expense_basis'] = cleaned.get('expense_basis') or 'free'
        for prefix in ('deduction', 'variable'):
            if prefix == 'deduction' and cleaned.get('use_clt'):
                continue
            try:
                variables_from_data(self.data, prefix)
            except ValidationError as error:
                self.add_error(None, error)
        return cleaned


def _value(data: dict, name: str, default=Decimal('0')):
    return data.get(name) or default


def clt_scenario_from_form(form: SalarySandboxForm) -> CltScenario:
    data = form.cleaned_data
    return CltScenario(
        gross_monthly=data['gross_salary'],
        dependents=_value(data, 'dependents', 0),
        pension=_value(data, 'pension'),
        vt_enabled=data.get('vt_enabled', False),
        vt_cost=_value(data, 'vt_cost'),
        food_employee=_value(data, 'food_employee'),
        health_employee=_value(data, 'health_employee'),
        other_deductions=_value(data, 'other_deductions'),
    )


def _list_values(data, name):
    if hasattr(data, 'getlist'):
        return data.getlist(name)
    value = data.get(name, [])
    return value if isinstance(value, (list, tuple)) else [value]


def variables_from_data(data, prefix: str) -> tuple[CustomVariable, ...]:
    variables = []
    lists = [_list_values(data, f'{prefix}_{name}') for name in ('label', 'type', 'value')]
    if len({len(values) for values in lists}) > 1 or len(lists[0]) > 20:
        raise ValidationError(_('Enter at most 20 complete rows in each list.'))
    for index, (label, value_type, raw_value) in enumerate(zip(*lists), start=1):
        label = label.strip()
        raw_value = raw_value.strip()
        if not label and not raw_value:
            continue
        error = _('Row %(row)s: enter a description and a valid nonnegative amount or percentage (0–100).') % {'row': index}
        if not label or len(label) > 80 or value_type not in {'currency', 'percent'}:
            raise ValidationError(error)
        try:
            value = Decimal(raw_value.replace(',', '.'))
        except (InvalidOperation, ValueError):
            raise ValidationError(error)
        if (not value.is_finite() or value < 0 or value > Decimal('999999999999.99')
                or value.as_tuple().exponent < -2 or (value_type == 'percent' and value > 100)):
            raise ValidationError(error)
        variables.append(CustomVariable(label, value_type, value))
    return tuple(variables)


def variable_rows(data, prefix: str, *, include_blank=False) -> list[dict[str, str]]:
    rows = []
    if data:
        rows = [
            {'label': label, 'value_type': value_type, 'value': value}
            for label, value_type, value in zip_longest(
                _list_values(data, f'{prefix}_label'),
                _list_values(data, f'{prefix}_type'),
                _list_values(data, f'{prefix}_value'),
                fillvalue='',
            )
        ]
    return rows or ([{}] if include_blank else [])


def budget_from_form(form: SalarySandboxForm) -> BudgetInput:
    data = form.cleaned_data
    fixed_value = _value(data, 'fixed_cost_value')
    fixed_is_percent = data.get('fixed_cost_type') != 'currency'
    return BudgetInput(
        fixed_bills=Decimal('0') if fixed_is_percent else fixed_value,
        emergency_percent=_value(data, 'emergency_percent') / 100,
        investments_percent=_value(data, 'investments_percent') / 100,
        fixed_percent=fixed_value / 100 if fixed_is_percent else Decimal('0'),
        custom_variables=variables_from_data(form.data, 'variable'),
    )


def parse_month(value):
    try:
        year, month = value.split('-')
        if len(year) != 4 or len(month) != 2:
            raise ValueError
        result = date(int(year), int(month), 1)
        if not 1901 <= result.year <= 9988:
            raise ValueError
        return result
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(_('Enter a month as YYYY-MM, between 1901 and 9988.'))


class YieldSimulationForm(forms.Form):
    currency = forms.ChoiceField(label=_('Currency'), choices=[(code, code) for code in ('BRL', 'USD', 'EUR', 'GBP', 'JPY', 'CHF')], initial='BRL')
    start_month = forms.CharField(label=_('Starting month'), widget=forms.TextInput(attrs={'placeholder': 'YYYY-MM', 'inputmode': 'numeric'}))
    months = forms.IntegerField(label=_('Months'), min_value=1, max_value=120, initial=12)
    initial_balance = forms.DecimalField(label=_('Initial balance'), max_digits=14, decimal_places=2, min_value=0)
    rate = forms.DecimalField(label=_('Effective rate (%)'), max_digits=9, decimal_places=6, min_value=Decimal('-99.999999'), max_value=Decimal('999.999999'))
    rate_period = forms.ChoiceField(label=_('Rate period'), choices=(('monthly', _('Monthly')), ('annual', _('Annual'))), initial='monthly')
    contribution = forms.DecimalField(label=_('Monthly contribution'), max_digits=14, decimal_places=2, min_value=0, initial=0)
    withdrawal = forms.DecimalField(label=_('Monthly withdrawal'), max_digits=14, decimal_places=2, min_value=0, initial=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault('start_month', timezone.localdate().strftime('%Y-%m'))
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASSES
            if isinstance(field, forms.DecimalField):
                field.widget = forms.TextInput(attrs={'class': INPUT_CLASSES, 'inputmode': 'decimal'})
            if self.is_bound and self.errors.get(name):
                field.widget.attrs['aria-invalid'] = 'true'
                if isinstance(field, forms.IntegerField):
                    field.widget = forms.TextInput(attrs={**field.widget.attrs, 'inputmode': 'numeric'})

    def clean_start_month(self):
        return parse_month(self.cleaned_data['start_month'])

    def clean(self):
        cleaned = super().clean()
        overrides = {}
        amount_field = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
        for index in range(cleaned.get('months') or 0):
            values = []
            for name in ('contribution', 'withdrawal'):
                raw = self.data.get(f'{name}_{index}', '').strip()
                try:
                    value = amount_field.clean(raw)
                except ValidationError:
                    self.add_error(None, _('Month %(month)s: enter a valid nonnegative amount with at most two decimal places.') % {'month': index + 1})
                    value = None
                values.append(value if value is not None else cleaned.get(name, Decimal('0')))
            overrides[index] = tuple(values)
        cleaned['overrides'] = overrides
        return cleaned


class DraftNameForm(forms.Form):
    draft_name = forms.CharField(label=_('Draft name'), max_length=120, widget=forms.TextInput(attrs={'class': INPUT_CLASSES}))
