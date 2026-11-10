"""Plan operations of the API: limits, goals, the months ahead and the calculators.

An operation reads a schema and calls ``planning.limits``, ``planning.goals``,
``planning.sheet`` or ``planning.tools``. The amounts that it returns are
calculated there.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from django.core.exceptions import ValidationError
from ninja import Router, Schema
from pydantic import Field

from accounts.models import UserPreference
from config import clock
from config.currencies import CURRENCIES
from config.ownership import owned, owned_choice
from config.validation import renamed
from ledger.categories import Category
from ledger.consultation import requested_billed_month
from ledger.services import ensure_ledger_current
from planning import goals, limits, sheet, tools
from planning.models import FinancialGoal, SavedSheet

router = Router()

CurrencyCode = Literal[tuple(CURRENCIES)]


class Budget(Schema):
    category_id: int
    name: str
    limit: Decimal
    #: The expenses of the category and of its subcategories in the month.
    spent: Decimal
    left: Decimal


class BudgetSuggestion(Schema):
    category_id: int
    name: str
    spent: Decimal
    #: The average expense of the three months before.
    average: Decimal


class MonthPlanOut(Schema):
    month: dt.date
    #: The currency of totals. Entries in another currency do not count.
    currency: str
    is_current: bool
    income: Decimal
    expenses: Decimal
    limit: Decimal | None
    #: The limit minus the expenses. Null without a limit.
    left: Decimal | None
    #: What is left for each day until the end of the current month.
    per_day: Decimal | None
    budgets: list[Budget]
    #: Top-level expense categories with expenses and without a budget.
    suggestions: list[BudgetSuggestion]


class LimitIn(Schema):
    #: The first day of the month from which the limit holds. The current month when omitted.
    month: dt.date | None = None
    #: Null ends the limit from that month on.
    amount: Decimal | None = None
    #: Null: the limit of the month. Otherwise the budget of this category.
    category_id: int | None = None


class Reservation(Schema):
    source: str
    label: str
    currency: str
    amount: Decimal
    #: The part of the amount that the balance of the source covers.
    backed: Decimal


GoalStatus = Literal["reached", "overdue", "dated", "open"]


class GoalOut(Schema):
    id: int
    name: str
    target_amount: Decimal
    currency: str
    target_date: dt.date | None
    is_archived: bool
    #: The backed reservations, in the currency of the goal.
    saved: Decimal
    remaining: Decimal
    percent: int
    status: GoalStatus
    #: For a goal with a later date: what each month through that date must add.
    monthly_needed: Decimal | None
    #: False when a reservation has no exchange rate to the currency of the goal.
    complete: bool
    missing_currencies: list[str]
    reservations: list[Reservation]


class GoalSource(Schema):
    #: ``account:<id>`` or ``investment:<id>``.
    key: str
    label: str
    currency: str
    balance: Decimal
    #: The positive balance that no active goal reserves.
    free: Decimal


class GoalsOut(Schema):
    goals: list[GoalOut]
    sources: list[GoalSource]


class GoalIn(Schema):
    name: str
    target_amount: Decimal
    #: The currency of totals when omitted.
    currency: CurrencyCode | None = None
    target_date: dt.date | None = None


class GoalEdit(Schema):
    name: str
    target_amount: Decimal
    target_date: dt.date | None = None
    is_archived: bool = False


class ReservationIn(Schema):
    source: str
    #: Zero removes the reservation.
    amount: Decimal


class Created(Schema):
    id: int


def _month(value):
    requested = requested_billed_month(value.strip())
    return dt.date(*requested, 1) if requested else clock.today().replace(day=1)


@router.get("/month", response=MonthPlanOut, summary="Read the limit and the budgets of a month")
def read_month(request, month: str = ""):
    return limits.month_plan(request.user, _month(month), clock.today())


@router.put("/limit", response=MonthPlanOut, summary="Set or end a limit from a month on")
def set_limit(request, payload: LimitIn):
    user = request.user
    month = payload.month or clock.today().replace(day=1)
    category = None
    if payload.category_id is not None:
        category = owned_choice(Category, user, payload.category_id, "category_id")
    try:
        limits.set_limit(user, month, payload.amount, category)
    except ValidationError as error:
        raise renamed(error, {"category": "category_id", "start_month": "month"}) from None
    return limits.month_plan(user, month, clock.today())


@router.get("/goals", response=GoalsOut, summary="List the goals and the balances they can reserve")
def list_goals(request):
    return goals.read(request.user, clock.today())


@router.post("/goals", response=Created, summary="Create a goal")
def create_goal(request, payload: GoalIn):
    user = request.user
    goal = goals.create_goal(
        user,
        name=payload.name,
        target_amount=payload.target_amount,
        currency=payload.currency or UserPreference.for_user(user).base_currency,
        target_date=payload.target_date,
    )
    return {"id": goal.pk}


@router.put("/goals/{goal_id}", response=Created, summary="Change or archive a goal")
def update_goal(request, goal_id: int, payload: GoalEdit):
    goal = owned(FinancialGoal, request.user, goal_id)
    goals.change_goal(
        goal,
        name=payload.name,
        target_amount=payload.target_amount,
        target_date=payload.target_date,
        is_archived=payload.is_archived,
    )
    return {"id": goal.pk}


@router.delete("/goals/{goal_id}", response={204: None}, summary="Delete a goal")
def delete_goal(request, goal_id: int):
    owned(FinancialGoal, request.user, goal_id).delete()
    return 204, None


@router.put(
    "/goals/{goal_id}/reservations",
    response=Created,
    summary="Reserve a part of a balance for a goal",
)
def set_reservation(request, goal_id: int, payload: ReservationIn):
    goal = owned(FinancialGoal, request.user, goal_id)
    goals.set_reservation(goal, payload.source, payload.amount)
    return {"id": goal.pk}


# The months ahead and the sheet

Amount = Annotated[Decimal, Field(ge=0, le=sheet.MAX_AMOUNT)]
MonthKey = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
RowKey = Annotated[str, Field(min_length=1, max_length=100)]


class ManualRow(Schema):
    id: Annotated[str, Field(pattern=r"^[a-z0-9]{1,16}$")]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    section: Literal["income", "expense"]
    #: The amount of each month. A changed cell replaces it in its month.
    amount: Amount | None = None


class SheetChanges(Schema):
    #: ``{row key: {"YYYY-MM": amount}}``: a value that replaces the recorded one.
    cells: dict[RowKey, dict[MonthKey, Amount]] = {}
    manual: Annotated[list[ManualRow], Field(max_length=sheet.MAX_MANUAL)] = []


class SheetIn(Schema):
    months: Literal[6, 12] = 6
    changes: SheetChanges = SheetChanges()


class SheetCell(Schema):
    month: dt.date
    #: What the records expect.
    live: Decimal
    #: What the sheet counts: the changed value, or the recorded one.
    value: Decimal
    changed: bool


class SheetRow(Schema):
    #: ``transaction:<id>``, ``card:<id>``, ``other:<section>`` or ``manual:<id>``.
    key: str
    #: Empty for the ``other`` rows; the client names them.
    label: str
    section: Literal["income", "expense"]
    manual: bool
    cells: list[SheetCell]


class SheetTotal(Schema):
    month: dt.date
    income: Decimal
    expenses: Decimal
    result: Decimal
    #: The balance of the accounts at the end of the month.
    balance: Decimal
    #: The same balance without the changes of the sheet.
    live_balance: Decimal


class ForecastOut(Schema):
    today: dt.date
    currency: str
    #: The balances of the accounts today.
    opening_balance: Decimal
    months: list[SheetTotal]
    complete: bool
    missing_currencies: list[str]


class SheetOut(Schema):
    today: dt.date
    currency: str
    opening_balance: Decimal
    rows: list[SheetRow]
    totals: list[SheetTotal]
    complete: bool
    missing_currencies: list[str]


class SavedSheetIn(Schema):
    name: str
    months: Literal[6, 12] = 6
    changes: SheetChanges = SheetChanges()


class SavedSheetBrief(Schema):
    id: int
    name: str
    updated_at: dt.datetime


class SavedSheetOut(Schema):
    id: int
    name: str
    months: int
    changes: SheetChanges


@router.get("/forecast", response=ForecastOut, summary="Read the cash of the months ahead")
def read_forecast(request):
    ensure_ledger_current(request.user)
    composed = sheet.compose(request.user, clock.today())
    return {**composed, "months": composed["totals"]}


@router.post("/sheet", response=SheetOut, summary="Calculate the sheet with a set of changes")
def compose_sheet(request, payload: SheetIn):
    ensure_ledger_current(request.user)
    return sheet.compose(request.user, clock.today(), payload.months, payload.changes.model_dump())


@router.get("/sheets", response=list[SavedSheetBrief], summary="List the saved sheets")
def list_sheets(request):
    return SavedSheet.objects.filter(user=request.user)


@router.post("/sheets", response=Created, summary="Save a sheet")
def create_sheet(request, payload: SavedSheetIn):
    saved = sheet.save_sheet(
        request.user,
        name=payload.name,
        months=payload.months,
        changes=payload.changes.model_dump(),
    )
    return {"id": saved.pk}


@router.get("/sheets/{sheet_id}", response=SavedSheetOut, summary="Read a saved sheet")
def read_sheet(request, sheet_id: int):
    return owned(SavedSheet, request.user, sheet_id)


@router.put("/sheets/{sheet_id}", response=Created, summary="Replace a saved sheet")
def update_sheet(request, sheet_id: int, payload: SavedSheetIn):
    saved = owned(SavedSheet, request.user, sheet_id)
    sheet.save_sheet(
        request.user,
        name=payload.name,
        months=payload.months,
        changes=payload.changes.model_dump(),
        sheet=saved,
    )
    return {"id": saved.pk}


@router.delete("/sheets/{sheet_id}", response={204: None}, summary="Delete a saved sheet")
def delete_sheet(request, sheet_id: int):
    owned(SavedSheet, request.user, sheet_id).delete()
    return 204, None


# Calculators

Money = Annotated[Decimal, Field(ge=0, le=tools.MAX_AMOUNT)]


class SalaryIn(Schema):
    gross: Annotated[Decimal, Field(gt=0, le=tools.MAX_AMOUNT)]
    dependents: Annotated[int, Field(ge=0, le=30)] = 0
    #: A private pension contribution. It lowers the income-tax base.
    pension: Money = Decimal("0")
    #: The cost of the transport benefit. The employee pays up to 6% of the gross salary.
    transport: Money = Decimal("0")
    food: Money = Decimal("0")
    health: Money = Decimal("0")
    other: Money = Decimal("0")


class PayPeriod(Schema):
    gross: Decimal
    inss: Decimal
    irrf: Decimal
    deductions: Decimal
    net: Decimal


class SalaryOut(Schema):
    #: The year of the tax tables.
    year: int
    #: True when the current year has no table and the latest one was used.
    assumed: bool
    month: PayPeriod
    thirteenth: PayPeriod
    vacation: PayPeriod
    annual_net: Decimal
    annual_fgts: Decimal
    monthly_average_net: Decimal


class GrowthIn(Schema):
    initial: Money = Decimal("0")
    contribution: Money = Decimal("0")
    #: A percentage for each month or for each year.
    rate: Annotated[Decimal, Field(ge=-100, le=1000)]
    rate_period: Literal["monthly", "annual"] = "monthly"
    months: int


class GrowthRow(Schema):
    month: int
    #: The yield of the month.
    gain: Decimal
    contribution: Decimal
    balance: Decimal


class GrowthOut(Schema):
    #: The percentage for each month that the calculation used.
    monthly_rate: Decimal
    ending: Decimal
    #: The initial amount plus the contributions.
    contributed: Decimal
    total_yield: Decimal
    rows: list[GrowthRow]


@router.post("/tools/salary", response=SalaryOut, summary="Calculate the net pay of a CLT salary")
def calculate_salary(request, payload: SalaryIn):
    values = payload.model_dump()
    return tools.salary(values.pop("gross"), clock.today().year, **values)


@router.post("/tools/growth", response=GrowthOut, summary="Calculate a balance that grows")
def calculate_growth(request, payload: GrowthIn):
    return tools.growth(**payload.model_dump())
