"""Pure, non-persistent compensation and budget calculations.

The sandbox deliberately has no relationship with the financial ledger.  Its
inputs are value objects and its outputs are safe to render directly in a
server-side template.
"""

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.utils.translation import gettext as _

from sandbox.tax_rules import get_tax_rules
from sandbox.tax_rules.y2026 import ProgressiveBand, SimpleBand, TaxRuleSet


D = Decimal
CENT = D('0.01')
ZERO = D('0')


def money(value: Decimal | int | str) -> Decimal:
    return D(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def ratio(value: Decimal | int | str) -> Decimal:
    return D(str(value))


def truncate_two(value: Decimal) -> Decimal:
    return value.quantize(D('0.01'), rounding=ROUND_DOWN)


def progressive_tax(base: Decimal, bands: tuple[ProgressiveBand, ...]) -> Decimal:
    base = max(base, ZERO)
    previous = ZERO
    total = ZERO
    for band in bands:
        upper = band.upper if band.upper is not None else base
        taxable = min(base, upper) - previous
        if taxable > ZERO:
            total += taxable * band.rate
        if band.upper is None or base <= upper:
            break
        previous = upper
    return money(total)


def bracket_tax(base: Decimal, bands: tuple[ProgressiveBand, ...]) -> Decimal:
    base = max(base, ZERO)
    for band in bands:
        if band.upper is None or base <= band.upper:
            return money(base * band.rate - band.deduction)
    return ZERO


def irrf_tax(
    taxable_income: Decimal,
    dependents: int,
    pension: Decimal,
    rules: TaxRuleSet,
    deductible_inss: Decimal = ZERO,
) -> tuple[Decimal, Decimal, str]:
    legal = max(
        taxable_income - deductible_inss - pension - (rules.irrf_dependent_deduction * dependents),
        ZERO,
    )
    simplified = max(taxable_income - rules.irrf_simplified_deduction, ZERO)
    # The taxpayer uses whichever deduction produces the lowest taxable base.
    base = min(legal, simplified)
    tax = bracket_tax(base, rules.irrf)
    if taxable_income <= rules.irrf_reduction_zero_limit:
        reduction = min(tax, rules.irrf_reduction_full_amount)
    elif taxable_income <= rules.irrf_reduction_upper_limit:
        reduction = rules.irrf_reduction_constant - rules.irrf_reduction_slope * taxable_income
        reduction = min(max(reduction, ZERO), tax)
    else:
        reduction = ZERO
    method = 'legal' if legal <= simplified else 'simplified'
    return money(max(tax - reduction, ZERO)), money(base), method


def individual_inss(amount: Decimal, rules: TaxRuleSet) -> Decimal:
    return money(min(max(amount, ZERO), rules.inss_ceiling) * rules.individual_inss_rate)


def dividend_withholding(annual_profit: Decimal, billed_months: int, rules: TaxRuleSet) -> Decimal:
    """Apply the 2026 monthly distribution threshold to an annual projection."""
    months = max(billed_months, 1)
    return money(annual_profit * rules.dividend_withholding_rate) if annual_profit / months > rules.dividend_withholding_threshold else ZERO


def _simple_band(rbt12: Decimal, bands: tuple[SimpleBand, ...]) -> tuple[int, SimpleBand] | None:
    for index, band in enumerate(bands, start=1):
        if rbt12 <= band.upper:
            return index, band
    return None


@dataclass(frozen=True)
class CltScenario:
    gross_monthly: Decimal
    dependents: int = 0
    pension: Decimal = ZERO
    vt_enabled: bool = False
    vt_cost: Decimal = ZERO
    food_employee: Decimal = ZERO
    health_employee: Decimal = ZERO
    other_deductions: Decimal = ZERO
    employer_benefits: Decimal = ZERO
    employer_profile: str = 'general'
    rat_rate: Decimal = D('0.01')
    fap: Decimal = D('1')
    third_party_rate: Decimal = D('0.058')


@dataclass(frozen=True)
class PayPeriod:
    gross: Decimal
    inss: Decimal
    irrf: Decimal
    deductions: Decimal
    net: Decimal
    irrf_base: Decimal
    irrf_method: str


@dataclass(frozen=True)
class CltResult:
    ordinary: PayPeriod
    thirteenth: PayPeriod
    vacation: PayPeriod
    annual_net: Decimal
    annual_fgts: Decimal
    annual_employer_benefits: Decimal
    annual_worker_value: Decimal
    annual_employer_cost: Decimal
    monthly_normalized_net: Decimal
    monthly_normalized_worker_value: Decimal
    employer_lines: tuple[tuple[str, Decimal], ...]
    warnings: tuple[str, ...]


def _clt_period(
    gross: Decimal,
    scenario: CltScenario,
    rules: TaxRuleSet,
    include_employee_deductions: bool = False,
) -> PayPeriod:
    gross = money(gross)
    inss = progressive_tax(gross, rules.employee_inss)
    irrf, irrf_base, method = irrf_tax(
        gross, scenario.dependents, scenario.pension, rules, deductible_inss=inss,
    )
    deductions = ZERO
    if include_employee_deductions:
        vt = min(gross * D('0.06'), scenario.vt_cost) if scenario.vt_enabled else ZERO
        deductions = money(vt + scenario.food_employee + scenario.health_employee + scenario.other_deductions)
    return PayPeriod(gross, inss, irrf, deductions, money(gross - inss - irrf - deductions), irrf_base, method)


def calculate_clt(scenario: CltScenario, rules: TaxRuleSet | None = None) -> CltResult:
    rules = rules or get_tax_rules()
    ordinary = _clt_period(scenario.gross_monthly, scenario, rules, True)
    thirteenth = _clt_period(scenario.gross_monthly, scenario, rules)
    vacation = _clt_period(scenario.gross_monthly * D('1.333333333333333333'), scenario, rules)
    annual_net = money(ordinary.net * 11 + vacation.net + thirteenth.net)
    annual_salary_base = money(scenario.gross_monthly * D('13.333333333333333333'))
    annual_fgts = money(annual_salary_base * rules.fgts_rate)
    annual_benefits = money(scenario.employer_benefits * 12)

    if scenario.employer_profile == 'simple_iii_v':
        cpp = ZERO
        rat = ZERO
        third = ZERO
    elif scenario.employer_profile == 'simple_iv':
        cpp = money(annual_salary_base * rules.employer_cpp_rate)
        rat = money(annual_salary_base * scenario.rat_rate * scenario.fap)
        third = ZERO
    else:
        cpp = money(annual_salary_base * rules.employer_cpp_rate)
        rat = money(annual_salary_base * scenario.rat_rate * scenario.fap)
        third = money(annual_salary_base * scenario.third_party_rate)
    employer_lines = (
        (_('Salary, 13th and vacation 1/3'), annual_salary_base),
        (_('FGTS'), annual_fgts),
        (_('Employer CPP'), cpp),
        (_('RAT adjusted by FAP'), rat),
        (_('Third parties'), third),
        (_('Employer benefits'), annual_benefits),
    )
    annual_cost = money(sum(value for _, value in employer_lines))
    worker_value = money(annual_net + annual_fgts + annual_benefits)
    return CltResult(
        ordinary=ordinary,
        thirteenth=thirteenth,
        vacation=vacation,
        annual_net=annual_net,
        annual_fgts=annual_fgts,
        annual_employer_benefits=annual_benefits,
        annual_worker_value=worker_value,
        annual_employer_cost=annual_cost,
        monthly_normalized_net=money(annual_net / 12),
        monthly_normalized_worker_value=money(worker_value / 12),
        employer_lines=employer_lines,
        warnings=(_('The 40% FGTS severance fine is contingent and is not included in recurring cost.'),),
    )


@dataclass(frozen=True)
class PjScenario:
    revenue_monthly: Decimal
    regime: str = 'simples'
    pro_labore: Decimal = D('1621')
    months_billed: int = 11
    company_age_months: int = 13
    prior_revenue: Decimal = ZERO
    prior_payroll: Decimal = ZERO
    iss_rate: Decimal = D('0.05')
    iss_outside_monthly: Decimal = ZERO
    accounting_monthly: Decimal = ZERO
    bank_monthly: Decimal = ZERO
    certificate_annual: Decimal = ZERO
    municipal_annual: Decimal = ZERO
    council_annual: Decimal = ZERO
    other_costs_monthly: Decimal = ZERO


@dataclass(frozen=True)
class PjResult:
    regime: str
    monthly_revenue: Decimal
    annual_revenue: Decimal
    monthly_business_taxes: Decimal
    annual_business_taxes: Decimal
    pro_labore_inss: Decimal
    pro_labore_irrf: Decimal
    annual_operating_costs: Decimal
    annual_profit_available: Decimal
    annual_dividend_withholding: Decimal
    annual_net: Decimal
    monthly_normalized_net: Decimal
    company_cost_annual: Decimal
    factor_r: Decimal | None
    annex: str | None
    effective_rate: Decimal | None
    tax_lines: tuple[tuple[str, Decimal], ...]
    warnings: tuple[str, ...]
    valid: bool = True

    @property
    def effective_rate_percent(self):
        return self.effective_rate * 100 if self.effective_rate is not None else None

    @property
    def factor_r_percent(self):
        return self.factor_r * 100 if self.factor_r is not None else None


def _operating_annual(scenario: PjScenario) -> Decimal:
    monthly = scenario.accounting_monthly + scenario.bank_monthly + scenario.other_costs_monthly
    return money(monthly * 12 + scenario.certificate_annual + scenario.municipal_annual + scenario.council_annual)


def _factor_r(scenario: PjScenario) -> tuple[Decimal, Decimal]:
    if scenario.company_age_months == 1:
        revenue = scenario.revenue_monthly
        payroll = scenario.pro_labore
        factor = D('0.28') if payroll > ZERO and revenue == ZERO else (payroll / revenue if revenue else D('0.01'))
        return truncate_two(factor), money(revenue * 12)
    if 2 <= scenario.company_age_months <= 12:
        revenue = scenario.prior_revenue
        payroll = scenario.prior_payroll
        factor = D('0.28') if payroll > ZERO and revenue == ZERO else (payroll / revenue if revenue else D('0.01'))
        months = scenario.company_age_months - 1
        return truncate_two(factor), money(revenue / months * 12 if months else ZERO)
    revenue = scenario.prior_revenue
    payroll = scenario.prior_payroll
    factor = D('0.28') if payroll > ZERO and revenue == ZERO else (payroll / revenue if revenue else D('0.01'))
    return truncate_two(factor), money(revenue)


def _simple_result(scenario: PjScenario, rules: TaxRuleSet) -> PjResult:
    factor, rbt12 = _factor_r(scenario)
    bands = rules.simple_iii if factor >= D('0.28') else rules.simple_v
    selected = _simple_band(rbt12, bands)
    annual_revenue = money(scenario.revenue_monthly * scenario.months_billed)
    if selected is None or annual_revenue > rules.simple_revenue_limit:
        return PjResult(
            regime='Simples Nacional', monthly_revenue=money(scenario.revenue_monthly),
            annual_revenue=annual_revenue, monthly_business_taxes=ZERO,
            annual_business_taxes=ZERO, pro_labore_inss=ZERO, pro_labore_irrf=ZERO,
            annual_operating_costs=ZERO, annual_profit_available=ZERO,
            annual_dividend_withholding=ZERO, annual_net=ZERO,
            monthly_normalized_net=ZERO, company_cost_annual=annual_revenue,
            factor_r=factor, annex=None, effective_rate=None, tax_lines=(),
            warnings=(_('Revenue exceeds the Simples Nacional limit.'),), valid=False,
        )
    band_number, band = selected
    effective = (rbt12 * band.rate - band.deduction) / rbt12 if rbt12 else ZERO
    das = money(scenario.revenue_monthly * effective)
    annual_das = money(das * scenario.months_billed)
    iss_outside = money(scenario.iss_outside_monthly * scenario.months_billed) if rbt12 > rules.simple_iss_sublimit else ZERO
    annual_business = money(annual_das + iss_outside)
    inss = individual_inss(scenario.pro_labore, rules)
    irrf, irrf_base, irrf_method = irrf_tax(scenario.pro_labore, 0, ZERO, rules, deductible_inss=inss)
    costs = _operating_annual(scenario)
    profit = max(money(annual_revenue - annual_business - scenario.pro_labore * 12 - costs), ZERO)
    dividend_tax = dividend_withholding(profit, scenario.months_billed, rules)
    net = money((scenario.pro_labore - inss - irrf) * 12 + profit - dividend_tax)
    warnings = [_('The annual projection repeats the current competence; future RBT12 is not recalculated.')]
    if rbt12 > rules.simple_iss_sublimit:
        warnings.append(_('ISS above the sublimite was entered manually, so this estimate is partial.'))
    if dividend_tax:
        warnings.append(_('A ten percent dividend withholding was applied to monthly distributions above R$ 50,000.00.'))
    return PjResult(
        regime='Simples Nacional', monthly_revenue=money(scenario.revenue_monthly), annual_revenue=annual_revenue,
        monthly_business_taxes=money(das + scenario.iss_outside_monthly), annual_business_taxes=annual_business,
        pro_labore_inss=inss, pro_labore_irrf=irrf, annual_operating_costs=costs,
        annual_profit_available=profit, annual_dividend_withholding=dividend_tax,
        annual_net=net, monthly_normalized_net=money(net / 12), company_cost_annual=annual_revenue,
        factor_r=factor, annex=f'Anexo {"III" if factor >= D("0.28") else "V"} · faixa {band_number}',
        effective_rate=effective, tax_lines=(('DAS', annual_das), ('ISS externo', iss_outside)), warnings=tuple(warnings),
    )


def _presumed_base(quarter_revenue: Decimal, quarter: int, rules: TaxRuleSet) -> Decimal:
    normal_limit = rules.presumed_increase_threshold / 4
    normal = min(quarter_revenue, normal_limit)
    excess = max(quarter_revenue - normal_limit, ZERO)
    increase = rules.presumed_increase_rate if rules.year >= 2026 and (quarter >= 1) else ZERO
    # The 2026 rule applies to IRPJ from Q1 and CSLL from Q2; the caller uses
    # the same helper with a zero increase for CSLL in Q1.
    return money(normal * rules.presumed_service_rate + excess * rules.presumed_service_rate * (D('1') + increase))


def _presumido_taxes(annual_revenue: Decimal, rules: TaxRuleSet) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    quarter_revenue = annual_revenue / 4
    irpj = ZERO
    csll = ZERO
    for quarter in range(1, 5):
        irpj_base = _presumed_base(quarter_revenue, quarter, rules)
        csll_base = _presumed_base(quarter_revenue, quarter, rules) if quarter >= 2 else money(quarter_revenue * rules.presumed_service_rate)
        irpj += irpj_base * rules.presumed_irpj_rate
        irpj += max(irpj_base - rules.presumed_irpj_monthly_threshold * 3, ZERO) * rules.presumed_irpj_additional_rate
        csll += csll_base * rules.presumed_csll_rate
    pis = annual_revenue * rules.presumed_pis_rate
    cofins = annual_revenue * rules.presumed_cofins_rate
    return money(irpj), money(csll), money(pis), money(cofins)


def calculate_pj_presumido(scenario: PjScenario, rules: TaxRuleSet | None = None) -> PjResult:
    rules = rules or get_tax_rules()
    annual_revenue = money(scenario.revenue_monthly * scenario.months_billed)
    if annual_revenue > rules.presumed_revenue_limit:
        return PjResult(
            regime='Lucro Presumido', monthly_revenue=money(scenario.revenue_monthly),
            annual_revenue=annual_revenue, monthly_business_taxes=ZERO,
            annual_business_taxes=ZERO, pro_labore_inss=ZERO, pro_labore_irrf=ZERO,
            annual_operating_costs=ZERO, annual_profit_available=ZERO,
            annual_dividend_withholding=ZERO, annual_net=ZERO,
            monthly_normalized_net=ZERO, company_cost_annual=annual_revenue,
            factor_r=None, annex=None, effective_rate=None, tax_lines=(),
            warnings=(_('Revenue exceeds the Lucro Presumido limit.'),), valid=False,
        )
    irpj, csll, pis, cofins = _presumido_taxes(annual_revenue, rules)
    iss = money(annual_revenue * scenario.iss_rate)
    business = money(irpj + csll + pis + cofins + annual_revenue * scenario.iss_rate)
    inss = individual_inss(scenario.pro_labore, rules)
    irrf, irrf_base, irrf_method = irrf_tax(scenario.pro_labore, 0, ZERO, rules, deductible_inss=inss)
    cpp = money(scenario.pro_labore * 12 * rules.employer_cpp_rate)
    costs = _operating_annual(scenario)
    profit = max(money(annual_revenue - business - scenario.pro_labore * 12 - cpp - costs), ZERO)
    dividend_tax = dividend_withholding(profit, scenario.months_billed, rules)
    net = money((scenario.pro_labore - inss - irrf) * 12 + profit - dividend_tax)
    warnings = [_('The annual projection repeats the same revenue in all four quarters and is an estimate.')]
    if dividend_tax:
        warnings.append(_('A ten percent dividend withholding was applied to monthly distributions above R$ 50,000.00.'))
    lines = (('IRPJ', irpj), ('CSLL', csll), ('PIS', pis), ('COFINS', cofins), ('ISS', iss), (_('CPP on pro-labore'), cpp))
    return PjResult(
        regime='Lucro Presumido', monthly_revenue=money(scenario.revenue_monthly), annual_revenue=annual_revenue,
        monthly_business_taxes=money(business / 12), annual_business_taxes=business,
        pro_labore_inss=inss, pro_labore_irrf=irrf, annual_operating_costs=costs,
        annual_profit_available=profit, annual_dividend_withholding=dividend_tax,
        annual_net=net, monthly_normalized_net=money(net / 12), company_cost_annual=annual_revenue,
        factor_r=None, annex=None, effective_rate=business / annual_revenue if annual_revenue else ZERO,
        tax_lines=lines, warnings=tuple(warnings),
    )


def calculate_pj(scenario: PjScenario, rules: TaxRuleSet | None = None) -> PjResult:
    rules = rules or get_tax_rules()
    return _simple_result(scenario, rules) if scenario.regime == 'simples' else calculate_pj_presumido(scenario, rules)


@dataclass(frozen=True)
class EquivalentResult:
    revenue_monthly: Decimal | None
    annual_revenue: Decimal | None
    target_annual_value: Decimal
    achieved_annual_value: Decimal | None
    warnings: tuple[str, ...]


def solve_equivalent_pj(clt: CltResult, scenario: PjScenario, rules: TaxRuleSet | None = None) -> EquivalentResult:
    rules = rules or get_tax_rules()
    target = clt.annual_worker_value
    max_annual = rules.simple_revenue_limit if scenario.regime == 'simples' else rules.presumed_revenue_limit
    billed_months = max(scenario.months_billed, 1)
    maximum_monthly = max_annual / billed_months
    if scenario.regime == 'simples' and scenario.company_age_months == 1:
        maximum_monthly = min(maximum_monthly, rules.simple_revenue_limit / 12)

    def value(revenue: Decimal) -> PjResult:
        return calculate_pj(replace(scenario, revenue_monthly=revenue), rules)

    maximum_result = value(maximum_monthly)
    if not maximum_result.valid or maximum_result.annual_net < target:
        return EquivalentResult(None, None, target, None, (_('The annual CLT value exceeds the calculable limit for this PJ regime.'),))
    low, high = ZERO, maximum_monthly
    for iteration in range(64):
        middle = (low + high) / 2
        if value(middle).annual_net >= target:
            high = middle
        else:
            low = middle
    rounded_high = money(high)
    result = value(rounded_high)
    while result.annual_net < target:
        rounded_high += CENT
        result = value(rounded_high)
    return EquivalentResult(rounded_high, result.annual_revenue, target, result.annual_net, result.warnings)


@dataclass(frozen=True)
class EquivalentCltResult:
    gross_monthly: Decimal
    target_annual_value: Decimal
    achieved_annual_value: Decimal


def solve_equivalent_clt(
    pj: PjResult,
    scenario: CltScenario,
    rules: TaxRuleSet | None = None,
) -> EquivalentCltResult:
    """Find the CLT gross salary whose package matches the PJ annual net."""
    rules = rules or get_tax_rules()
    target = pj.annual_net
    low = ZERO
    high = max(pj.monthly_normalized_net, D('1'))
    while calculate_clt(replace(scenario, gross_monthly=high), rules).annual_worker_value < target:
        high *= 2
        if high > D('1000000000'):
            break
    for iteration in range(64):
        middle = (low + high) / 2
        if calculate_clt(replace(scenario, gross_monthly=middle), rules).annual_worker_value >= target:
            high = middle
        else:
            low = middle
    rounded_high = money(high)
    result = calculate_clt(replace(scenario, gross_monthly=rounded_high), rules)
    while result.annual_worker_value < target:
        rounded_high += CENT
        result = calculate_clt(replace(scenario, gross_monthly=rounded_high), rules)
    return EquivalentCltResult(rounded_high, target, result.annual_worker_value)


@dataclass(frozen=True)
class CustomBudgetVariable:
    label: str
    value_type: str
    value: Decimal


@dataclass(frozen=True)
class AppliedBudgetVariable:
    label: str
    value_type: str
    value: Decimal
    monthly_amount: Decimal


@dataclass(frozen=True)
class BudgetInput:
    fixed_bills: Decimal = ZERO
    variable_expenses: Decimal = ZERO
    emergency_percent: Decimal = ZERO
    investments_percent: Decimal = ZERO
    fixed_percent: Decimal = ZERO
    custom_variables: tuple[CustomBudgetVariable, ...] = ()


@dataclass(frozen=True)
class BudgetRow:
    income: Decimal
    fixed_bills: Decimal
    fixed_percent_equivalent: Decimal
    variable_expenses: Decimal
    emergency: Decimal
    investments: Decimal
    custom_expenses: Decimal
    remaining: Decimal


def apply_custom_variables(income: Decimal, budget: BudgetInput) -> tuple[AppliedBudgetVariable, ...]:
    applied = []
    for variable in budget.custom_variables:
        amount = income * variable.value / 100 if variable.value_type == 'percent' else variable.value
        applied.append(AppliedBudgetVariable(variable.label, variable.value_type, variable.value, money(amount)))
    return tuple(applied)


def _budget_row(income: Decimal, budget: BudgetInput) -> BudgetRow:
    fixed = money(budget.fixed_bills + income * budget.fixed_percent)
    fixed_percent_equivalent = money(fixed / income * 100) if income else ZERO
    emergency = money(income * budget.emergency_percent)
    investments = money(income * budget.investments_percent)
    custom = money(sum((item.monthly_amount for item in apply_custom_variables(income, budget)), ZERO))
    remaining = money(income - fixed - budget.variable_expenses - emergency - investments - custom)
    return BudgetRow(
        income=money(income),
        fixed_bills=fixed,
        fixed_percent_equivalent=fixed_percent_equivalent,
        variable_expenses=money(budget.variable_expenses),
        emergency=emergency,
        investments=investments,
        custom_expenses=custom,
        remaining=remaining,
    )


def build_budget(clt_income: Decimal, pj_income: Decimal, budget: BudgetInput) -> dict[str, BudgetRow]:
    return {'clt': _budget_row(clt_income, budget), 'pj': _budget_row(pj_income, budget)}
