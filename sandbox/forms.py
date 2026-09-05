from decimal import Decimal, InvalidOperation

from django import forms
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
    gross_salary = decimal_field(
        _('Gross monthly salary'),
        initial=None,
        min_value=Decimal('0.01'),
        help_text=_('Monthly salary before any automatic or manually entered deductions.'),
    )
    use_clt = forms.BooleanField(
        label=_('Calculate CLT deductions automatically'),
        required=False,
        initial=True,
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
        self.fields['use_clt'].widget.attrs['data-use-clt'] = ''
        self.fields['fixed_cost_type'].widget.attrs['aria-label'] = _('Fixed costs unit')
        self.fields['fixed_cost_type'].widget.attrs['aria-describedby'] = 'id_fixed_cost_value-help'

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('gross_salary'):
            self.add_error('gross_salary', _('Enter the gross monthly salary.'))
        if cleaned.get('fixed_cost_type') == 'percent' and _value(cleaned, 'fixed_cost_value') > Decimal('100'):
            self.add_error('fixed_cost_value', _('Enter a percentage from 0 to 100.'))
        for name in ('emergency_percent', 'investments_percent'):
            if _value(cleaned, name) > Decimal('100'):
                self.add_error(name, _('Enter a percentage from 0 to 100.'))
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


def variables_from_data(data, prefix: str) -> tuple[CustomVariable, ...]:
    variables = []
    for label, value_type, raw_value in zip(
        data.getlist(f'{prefix}_label'),
        data.getlist(f'{prefix}_type'),
        data.getlist(f'{prefix}_value'),
    ):
        label = label.strip()
        raw_value = raw_value.strip()
        if not label and not raw_value:
            continue
        if not label or value_type not in {'currency', 'percent'}:
            continue
        try:
            value = Decimal(raw_value.replace(',', '.'))
        except (InvalidOperation, ValueError):
            continue
        if value < 0 or (value_type == 'percent' and value > 100):
            continue
        variables.append(CustomVariable(label[:80], value_type, value))
    return tuple(variables[:20])


def variable_rows(data, prefix: str, *, include_blank=False) -> list[dict[str, str]]:
    rows = []
    if data:
        rows = [
            {'label': label, 'value_type': value_type, 'value': value}
            for label, value_type, value in zip(
                data.getlist(f'{prefix}_label'),
                data.getlist(f'{prefix}_type'),
                data.getlist(f'{prefix}_value'),
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
