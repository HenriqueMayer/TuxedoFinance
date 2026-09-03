"""Pure, non-persistent salary and monthly-plan calculations."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.utils.translation import gettext as _

from sandbox.tax_rules import get_tax_rules
from sandbox.tax_rules.y2026 import ProgressiveBand, TaxRuleSet


D = Decimal
CENT = D('0.01')
ZERO = D('0')


def money(value: Decimal | int | str) -> Decimal:
    return D(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


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
    monthly_normalized_net: Decimal
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
        transport = min(gross * D('0.06'), scenario.vt_cost) if scenario.vt_enabled else ZERO
        deductions = money(transport + scenario.food_employee + scenario.health_employee + scenario.other_deductions)
    return PayPeriod(
        gross=gross,
        inss=inss,
        irrf=irrf,
        deductions=deductions,
        net=money(gross - inss - irrf - deductions),
        irrf_base=irrf_base,
        irrf_method=method,
    )


def calculate_clt(scenario: CltScenario, rules: TaxRuleSet | None = None) -> CltResult:
    rules = rules or get_tax_rules()
    ordinary = _clt_period(scenario.gross_monthly, scenario, rules, True)
    thirteenth = _clt_period(scenario.gross_monthly, scenario, rules)
    vacation = _clt_period(scenario.gross_monthly * D('1.333333333333333333'), scenario, rules)
    annual_net = money(ordinary.net * 11 + vacation.net + thirteenth.net)
    annual_salary_base = money(scenario.gross_monthly * D('13.333333333333333333'))
    return CltResult(
        ordinary=ordinary,
        thirteenth=thirteenth,
        vacation=vacation,
        annual_net=annual_net,
        annual_fgts=money(annual_salary_base * rules.fgts_rate),
        monthly_normalized_net=money(annual_net / 12),
        warnings=(_('The 40% FGTS severance fine is contingent and is not included in this projection.'),),
    )


@dataclass(frozen=True)
class CustomVariable:
    label: str
    value_type: str
    value: Decimal


@dataclass(frozen=True)
class AppliedVariable:
    label: str
    value_type: str
    value: Decimal
    monthly_amount: Decimal


def apply_variables(base: Decimal, variables: tuple[CustomVariable, ...]) -> tuple[AppliedVariable, ...]:
    applied = []
    for variable in variables:
        amount = base * variable.value / 100 if variable.value_type == 'percent' else variable.value
        applied.append(AppliedVariable(variable.label, variable.value_type, variable.value, money(amount)))
    return tuple(applied)


@dataclass(frozen=True)
class ManualResult:
    gross_monthly: Decimal
    deductions: tuple[AppliedVariable, ...]
    monthly_deductions: Decimal
    monthly_net: Decimal
    annual_gross: Decimal
    annual_deductions: Decimal
    annual_net: Decimal


def calculate_manual(gross_monthly: Decimal, deductions: tuple[CustomVariable, ...]) -> ManualResult:
    gross = money(gross_monthly)
    applied = apply_variables(gross, deductions)
    monthly_deductions = money(sum((item.monthly_amount for item in applied), ZERO))
    monthly_net = money(gross - monthly_deductions)
    return ManualResult(
        gross_monthly=gross,
        deductions=applied,
        monthly_deductions=monthly_deductions,
        monthly_net=monthly_net,
        annual_gross=money(gross * 12),
        annual_deductions=money(monthly_deductions * 12),
        annual_net=money(monthly_net * 12),
    )


@dataclass(frozen=True)
class BudgetInput:
    fixed_bills: Decimal = ZERO
    emergency_percent: Decimal = ZERO
    investments_percent: Decimal = ZERO
    fixed_percent: Decimal = ZERO
    custom_variables: tuple[CustomVariable, ...] = ()


@dataclass(frozen=True)
class BudgetRow:
    income: Decimal
    fixed_bills: Decimal
    fixed_percent_equivalent: Decimal
    emergency: Decimal
    investments: Decimal
    custom_expenses: Decimal
    remaining: Decimal


def build_budget(income: Decimal, budget: BudgetInput) -> BudgetRow:
    percentage_base = max(income, ZERO)
    fixed = money(budget.fixed_bills + percentage_base * budget.fixed_percent)
    emergency = money(percentage_base * budget.emergency_percent)
    investments = money(percentage_base * budget.investments_percent)
    custom = money(sum((item.monthly_amount for item in apply_variables(percentage_base, budget.custom_variables)), ZERO))
    fixed_percent_equivalent = money(fixed / percentage_base * 100) if percentage_base else ZERO
    return BudgetRow(
        income=money(income),
        fixed_bills=fixed,
        fixed_percent_equivalent=fixed_percent_equivalent,
        emergency=emergency,
        investments=investments,
        custom_expenses=custom,
        remaining=money(income - fixed - emergency - investments - custom),
    )
