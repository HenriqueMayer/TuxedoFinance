from decimal import Decimal, InvalidOperation

from django import forms
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from sandbox.services import BudgetInput, CltScenario, CustomBudgetVariable, PjScenario, _factor_r
from sandbox.tax_rules import get_tax_rules


INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-none focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-forest-deep dark:text-cream dark:placeholder:text-cream/40'
)
CHECKBOX_CLASSES = (
    'h-5 w-5 rounded-md border-forest/20 bg-white accent-caramel '
    'focus:outline-none focus:ring-2 focus:ring-caramel/30 dark:border-cream/20 dark:bg-forest-deep'
)


def decimal_field(label, *, initial=Decimal('0'), required=False, min_value=Decimal('0'), max_value=None, help_text=''):
    return forms.DecimalField(
        label=label, required=required, initial=initial, min_value=min_value,
        max_value=max_value, max_digits=14, decimal_places=2, help_text=help_text,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': str(min_value)}),
    )


class SalarySandboxForm(forms.Form):
    scenario_type = forms.ChoiceField(
        label=_('Income type'), choices=(('clt', _('CLT salary')), ('pj', _('PJ invoice'))),
        required=False, initial=None, widget=forms.RadioSelect,
    )
    tax_year = forms.ChoiceField(label=_('Tax year'), choices=((2026, '2026'),), initial=2026, required=False)

    clt_gross = decimal_field(
        _('Gross monthly salary'), initial=None, min_value=Decimal('0.01'),
        help_text=_('Salary before INSS, IRRF and other payroll deductions.'),
    )
    dependents = forms.IntegerField(
        label=_('Dependents'), required=False, initial=0, min_value=0, max_value=20,
        help_text=_('Legal dependents used in the monthly IRRF deduction comparison.'),
    )
    pension = decimal_field(_('Court-ordered pension'), help_text=_('Monthly amount deductible from IRRF.'))
    vt_enabled = forms.BooleanField(
        label=_('Receive transport voucher'), required=False,
        help_text=_('When enabled, the employee deduction is limited to 6% of salary or the actual transport cost.'),
    )
    vt_cost = decimal_field(
        _('Actual monthly transport cost'),
        help_text=_('Monthly cost of the public transport supplied by the employer.'),
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
    employer_benefits = decimal_field(
        _('Employer-paid benefits per month'),
        help_text=_('Benefits paid by the employer and added to the comparable annual package.'),
    )
    rat_percent = decimal_field(
        _('RAT rate (%)'), initial=Decimal('1.00'),
        help_text=_('Employer workplace-risk rate, usually from 1% to 3%, before the FAP multiplier.'),
    )
    fap = forms.DecimalField(
        label=_('FAP multiplier'), required=False, initial=Decimal('1.00'),
        min_value=Decimal('0.5'), max_value=Decimal('2'), max_digits=5, decimal_places=2,
        help_text=_('Multiplier from 0.50 to 2.00 applied to the employer RAT rate.'),
    )
    third_party_percent = decimal_field(
        _('Third-party contributions (%)'), initial=Decimal('5.80'), max_value=Decimal('20'),
        help_text=_('Employer contributions such as Salary-Education and Sistema S; the default estimate is 5.8%.'),
    )

    pj_revenue = decimal_field(
        _('Monthly invoice'), initial=None, min_value=Decimal('0.01'),
        help_text=_('Gross service revenue invoiced in each billed month.'),
    )
    pj_regime = forms.ChoiceField(
        label=_('Tax regime'), required=False, choices=(
            ('simples', _('Simples Nacional — Annex III/V')),
            ('presumido', _('Lucro Presumido')),
        ), initial='simples',
        help_text=_('Simples chooses Annex III or V through Fator R. Lucro Presumido applies separate federal and municipal taxes.'),
    )
    pro_labore = decimal_field(
        _('Monthly pró-labore'), initial=Decimal('1621.00'), min_value=Decimal('0.01'),
        help_text=_('Taxable monthly compensation for the partner’s work, subject to INSS and possibly IRRF.'),
    )
    months_billed = forms.IntegerField(
        label=_('Billed months per year'), required=False, initial=11, min_value=1, max_value=12,
        help_text=_('Number of months with revenue in the annual projection; 11 reserves one month without billing.'),
    )
    company_age_months = forms.ChoiceField(label=_('Company age'), required=False, choices=(
        *[(str(value), format_lazy('{} {}', value, _('month(s) of activity'))) for value in range(1, 13)],
        ('13', _('13+ months (mature company)')),
    ), initial='1', help_text=_('Determines how Simples annualizes revenue and payroll for the current period.'))
    prior_revenue = decimal_field(_('Previous revenue used for RBT12'), help_text=_('Only needed from the second month of activity onward.'))
    prior_payroll = decimal_field(_('Previous payroll used for Fator R'), help_text=_('Include pró-labore, payroll and applicable charges.'))
    iss_percent = decimal_field(
        _('ISS rate (%)'), initial=Decimal('5.00'), max_value=Decimal('100'),
        help_text=_('Municipal service-tax rate used by the Lucro Presumido estimate.'),
    )
    iss_outside_monthly = decimal_field(_('ISS outside Simples per billed month'), help_text=_('Required when the Simples ISS sublimite is exceeded.'))
    accounting_monthly = decimal_field(_('Accounting cost per month'), help_text=_('Recurring accounting service paid by the company.'))
    bank_monthly = decimal_field(_('PJ bank cost per month'), help_text=_('Recurring bank account and payment-service fees.'))
    certificate_annual = decimal_field(_('Digital certificate per year'), help_text=_('Annualized cost of the company digital certificate.'))
    municipal_annual = decimal_field(_('Municipal fees per year'), help_text=_('Annual municipal registration, inspection or operating fees.'))
    council_annual = decimal_field(_('Professional council per year'), help_text=_('Annual company registration fee when a professional council requires it.'))
    other_costs_monthly = decimal_field(_('Other PJ costs per month'), help_text=_('Other recurring operating costs paid by the company.'))

    fixed_cost_type = forms.ChoiceField(
        label=_('Fixed costs unit'), required=False, choices=(
            ('percent', '%'),
            ('currency', 'R$'),
        ), initial='percent',
    )
    fixed_cost_value = decimal_field(
        _('Fixed costs target'), initial=Decimal('50.00'),
        help_text=_(
            'Choose a percentage of normalized monthly net income or a fixed amount in reais. '
            'The result shows the amount and its equivalent percentage.'
        ),
    )
    emergency_percent = decimal_field(
        _('Emergency reserve target (%)'), initial=Decimal('10.00'), max_value=Decimal('100'),
        help_text=_('Share of normalized monthly net income set aside for an emergency fund.'),
    )
    investments_percent = decimal_field(
        _('Investments target (%)'), initial=Decimal('20.00'), max_value=Decimal('100'),
        help_text=_('Share of normalized monthly net income allocated to investments.'),
    )

    compare_pj_regime = forms.ChoiceField(
        label=_('PJ regime for comparison'), required=False, choices=(
            ('simples', _('Simples Nacional — Annex III/V')),
            ('presumido', _('Lucro Presumido')),
        ), initial='simples',
        help_text=_('Selects the company tax calculation used to find the equivalent PJ invoice.'),
    )
    compare_pro_labore = decimal_field(
        _('Pró-labore for comparison'), initial=Decimal('1621.00'), min_value=Decimal('0.01'),
        help_text=_('Pró-labore assumed while solving the equivalent PJ invoice.'),
    )
    compare_months_billed = forms.IntegerField(
        label=_('Billed months in comparison'), required=False, initial=11, min_value=1, max_value=12,
        help_text=_('Months of PJ revenue used to match the complete annual CLT package.'),
    )
    compare_employer_profile = forms.ChoiceField(
        label=_('CLT employer profile for comparison'), required=False, choices=(
            ('general', _('General regime (Presumed or Actual Profit)')),
            ('simple_iii_v', _('Simples Nacional — Annex III/V')),
            ('simple_iv', _('Simples Nacional — Annex IV')),
        ), initial='general',
        help_text=_(
            'General regime adds CPP, RAT/FAP and third parties. Simples III/V has no separate payroll charge for them. Simples IV adds CPP and RAT/FAP, without third parties.'
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.RadioSelect):
                continue
            field.widget.attrs['class'] = CHECKBOX_CLASSES if isinstance(field.widget, forms.CheckboxInput) else INPUT_CLASSES
            field.widget.attrs.setdefault('autocomplete', 'off')
            if field.help_text:
                field.widget.attrs['aria-describedby'] = f'id_{name}-help'
            if self.is_bound and self.errors.get(name):
                field.widget.attrs['aria-invalid'] = 'true'
        self.fields['tax_year'].disabled = True
        self.fields['tax_year'].widget.attrs['class'] = INPUT_CLASSES
        self.fields['fixed_cost_type'].widget.attrs['aria-label'] = _('Fixed costs unit')
        self.fields['fixed_cost_type'].widget.attrs['aria-describedby'] = 'id_fixed_cost_value-help'

    def clean(self):
        cleaned = super().clean()
        scenario_type = cleaned.get('scenario_type')
        if scenario_type not in {'clt', 'pj'}:
            self.add_error('scenario_type', _('Choose CLT or PJ to continue.'))
            return cleaned
        if self.data.get('intent') == 'select':
            return cleaned
        if (
            cleaned.get('fixed_cost_type') == 'percent'
            and _value(cleaned, 'fixed_cost_value') > Decimal('100')
        ):
            self.add_error('fixed_cost_value', _('Enter a percentage from 0 to 100.'))
        if scenario_type == 'clt' and not cleaned.get('clt_gross'):
            self.add_error('clt_gross', _('Enter the gross monthly salary.'))
        if scenario_type == 'pj':
            if not cleaned.get('pj_revenue'):
                self.add_error('pj_revenue', _('Enter the monthly invoice.'))
            if not cleaned.get('pro_labore'):
                self.add_error('pro_labore', _('Enter the monthly pró-labore.'))
            if cleaned.get('pj_regime') == 'simples':
                company_age = int(cleaned.get('company_age_months') or 1)
                if company_age > 1 and not cleaned.get('prior_revenue'):
                    self.add_error('prior_revenue', _('Enter the previous revenue for a company with more than one month of activity.'))
                if cleaned.get('pj_revenue'):
                    factor_r, rbt12 = _factor_r(pj_scenario_from_form_data(cleaned))
                    if rbt12 > get_tax_rules().simple_iss_sublimit and not cleaned.get('iss_outside_monthly'):
                        self.add_error('iss_outside_monthly', _('Enter the ISS paid outside Simples when the ISS sublimite is exceeded.'))
        return cleaned


def _value(data: dict, name: str, default=Decimal('0')):
    return data.get(name) or default


def clt_scenario_from_form(form: SalarySandboxForm, *, comparison=False) -> CltScenario:
    data = form.cleaned_data
    return CltScenario(
        gross_monthly=Decimal('1') if comparison else data['clt_gross'],
        dependents=0 if comparison else _value(data, 'dependents', 0),
        pension=Decimal('0') if comparison else _value(data, 'pension'),
        vt_enabled=False if comparison else data.get('vt_enabled', False),
        vt_cost=Decimal('0') if comparison else _value(data, 'vt_cost'),
        food_employee=Decimal('0') if comparison else _value(data, 'food_employee'),
        health_employee=Decimal('0') if comparison else _value(data, 'health_employee'),
        other_deductions=Decimal('0') if comparison else _value(data, 'other_deductions'),
        employer_benefits=Decimal('0') if comparison else _value(data, 'employer_benefits'),
        employer_profile=(data.get('compare_employer_profile') or 'general') if comparison else 'general',
        rat_rate=_value(data, 'rat_percent', Decimal('1')) / 100,
        fap=_value(data, 'fap', Decimal('1')),
        third_party_rate=_value(data, 'third_party_percent', Decimal('5.8')) / 100,
    )


def pj_scenario_from_form_data(data: dict, *, comparison=False) -> PjScenario:
    return PjScenario(
        revenue_monthly=Decimal('1') if comparison else data['pj_revenue'],
        regime=(data.get('compare_pj_regime') or 'simples') if comparison else (data.get('pj_regime') or 'simples'),
        pro_labore=_value(data, 'compare_pro_labore', Decimal('1621')) if comparison else data['pro_labore'],
        months_billed=_value(data, 'compare_months_billed', 11) if comparison else _value(data, 'months_billed', 11),
        company_age_months=1 if comparison else int(data.get('company_age_months') or 1),
        prior_revenue=Decimal('0') if comparison else _value(data, 'prior_revenue'),
        prior_payroll=Decimal('0') if comparison else _value(data, 'prior_payroll'),
        iss_rate=_value(data, 'iss_percent', Decimal('5')) / 100,
        iss_outside_monthly=_value(data, 'iss_outside_monthly'),
        accounting_monthly=_value(data, 'accounting_monthly'),
        bank_monthly=_value(data, 'bank_monthly'),
        certificate_annual=_value(data, 'certificate_annual'),
        municipal_annual=_value(data, 'municipal_annual'),
        council_annual=_value(data, 'council_annual'),
        other_costs_monthly=_value(data, 'other_costs_monthly'),
    )


def pj_scenario_from_form(form: SalarySandboxForm, *, comparison=False) -> PjScenario:
    return pj_scenario_from_form_data(form.cleaned_data, comparison=comparison)


def custom_variables_from_data(data) -> tuple[CustomBudgetVariable, ...]:
    variables = []
    for label, value_type, raw_value in zip(
        data.getlist('variable_label'), data.getlist('variable_type'), data.getlist('variable_value'),
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
        variables.append(CustomBudgetVariable(label[:80], value_type, value))
    return tuple(variables[:20])


def custom_variable_rows(data) -> list[dict[str, str]]:
    if not data:
        return []
    rows = [
        {'label': label, 'value_type': value_type, 'value': value}
        for label, value_type, value in zip(
            data.getlist('variable_label'), data.getlist('variable_type'), data.getlist('variable_value'),
        )
    ]
    return rows


def budget_from_form(form: SalarySandboxForm) -> BudgetInput:
    data = form.cleaned_data
    fixed_value = _value(data, 'fixed_cost_value')
    fixed_is_percent = data.get('fixed_cost_type') != 'currency'
    return BudgetInput(
        fixed_bills=Decimal('0') if fixed_is_percent else fixed_value,
        emergency_percent=_value(data, 'emergency_percent') / 100,
        investments_percent=_value(data, 'investments_percent') / 100,
        fixed_percent=fixed_value / 100 if fixed_is_percent else Decimal('0'),
        custom_variables=custom_variables_from_data(form.data),
    )
