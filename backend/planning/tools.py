"""Calculators of the Plan page. They read no record and save nothing.

- ``salary``: the net pay of a Brazilian CLT employee from the gross salary,
  with the tables of ``planning.tax_rules``.
- ``growth``: a balance that receives a contribution and a yield each month.
"""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from planning.tax_rules import rules_for

D = Decimal
CENT = D("0.01")
ZERO = D("0")
MAX_AMOUNT = D("999999999999.99")
MAX_MONTHS = 600


def money(value):
    return D(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def progressive_tax(base, bands):
    """Return the tax of ``base`` when each band taxes only its own part (INSS)."""
    base = max(base, ZERO)
    previous = total = ZERO
    for band in bands:
        upper = band.upper if band.upper is not None else base
        taxable = min(base, upper) - previous
        if taxable > ZERO:
            total += taxable * band.rate
        if band.upper is None or base <= upper:
            break
        previous = upper
    return money(total)


def bracket_tax(base, bands):
    """Return the tax of ``base`` by the rate and the deduction of its band (IRRF)."""
    base = max(base, ZERO)
    for band in bands:
        if band.upper is None or base <= band.upper:
            return money(base * band.rate - band.deduction)
    return ZERO


def irrf_tax(taxable_income, dependents, pension, rules, deductible_inss=ZERO):
    """Return ``(tax, base, method)``. The base is the lower of the legal and simplified bases."""
    legal = max(
        taxable_income - deductible_inss - pension - rules.irrf_dependent_deduction * dependents,
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
    method = "legal" if legal <= simplified else "simplified"
    return money(max(tax - reduction, ZERO)), money(base), method


def _period(gross, dependents, pension, rules, deductions=ZERO):
    gross = money(gross)
    inss = progressive_tax(gross, rules.employee_inss)
    irrf, _base, _method = irrf_tax(gross, dependents, pension, rules, deductible_inss=inss)
    deductions = money(deductions)
    return {
        "gross": gross,
        "inss": inss,
        "irrf": irrf,
        "deductions": deductions,
        "net": money(gross - inss - irrf - deductions),
    }


def salary(
    gross,
    year,
    *,
    dependents=0,
    pension=ZERO,
    transport=ZERO,
    food=ZERO,
    health=ZERO,
    other=ZERO,
):
    """Return the net pay of a CLT salary: the month, the 13th salary, the vacation and the year.

    ``pension`` is a private pension contribution and lowers the income-tax
    base. ``transport`` is the cost of the transport benefit; the employee
    pays it up to 6% of the gross salary. ``food``, ``health`` and ``other``
    are deducted from the monthly pay only. The year has eleven ordinary
    months, one vacation month with one third more, and the 13th salary. The
    40% FGTS fine of a dismissal is not included.
    """
    rules = rules_for(year)
    employee = pension + min(gross * D("0.06"), transport) + food + health + other
    month = _period(gross, dependents, pension, rules, employee)
    thirteenth = _period(gross, dependents, pension, rules)
    vacation = _period(gross * D("4") / D("3"), dependents, pension, rules)
    annual_net = money(month["net"] * 11 + vacation["net"] + thirteenth["net"])
    return {
        "year": rules.year,
        "assumed": rules.year != year,
        "month": month,
        "thirteenth": thirteenth,
        "vacation": vacation,
        "annual_net": annual_net,
        "annual_fgts": money(gross * D("40") / D("3") * rules.fgts_rate),
        "monthly_average_net": money(annual_net / 12),
    }


def salary_split(gross, year, advance_percent, **deductions):
    """Return the two receipts of a CLT salary that pays an advance.

    The advance is ``advance_percent`` of the gross salary, without
    deductions. The rest is the net pay of the month less the advance, so the
    INSS, the income tax and the other deductions leave the second receipt.
    The rest is zero or less when the advance takes the whole net pay.
    """
    result = salary(gross, year, **deductions)
    month = result["month"]
    advance = money(gross * advance_percent / D("100"))
    return {
        "year": result["year"],
        "assumed": result["assumed"],
        "gross": month["gross"],
        "inss": month["inss"],
        "irrf": month["irrf"],
        "deductions": month["deductions"],
        "net": month["net"],
        "advance": advance,
        "remainder": month["net"] - advance,
    }


def growth(*, initial, contribution, rate, rate_period, months):
    """Return a balance that grows for ``months`` months.

    Each month adds the yield of the opening balance and then the
    contribution. ``rate`` is a percentage for each month or, with
    ``rate_period`` ``annual``, for each year; an annual rate is converted to
    the monthly rate that compounds to it.
    """
    if not 1 <= months <= MAX_MONTHS:
        raise ValidationError({"months": _("Enter from 1 to 600 months.")})
    if rate <= -100:
        raise ValidationError({"rate": _("Enter a rate above -100%.")})
    rows = []
    balance = money(initial)
    total_yield = ZERO
    with localcontext() as context:
        context.prec = 36
        monthly_rate = rate / 100
        if rate_period == "annual":
            monthly_rate = (1 + monthly_rate) ** (D(1) / 12) - 1
        for index in range(months):
            gain = money(balance * monthly_rate)
            balance = money(balance + gain + contribution)
            if balance > MAX_AMOUNT:
                raise ValidationError(_("The balance exceeds the supported amount."))
            total_yield += gain
            rows.append(
                {
                    "month": index + 1,
                    "gain": gain,
                    "contribution": contribution,
                    "balance": balance,
                }
            )
    contributed = money(initial + contribution * months)
    return {
        "monthly_rate": (monthly_rate * 100).quantize(D("0.0001")),
        "ending": balance,
        "contributed": contributed,
        "total_yield": money(total_yield),
        "rows": rows,
    }
