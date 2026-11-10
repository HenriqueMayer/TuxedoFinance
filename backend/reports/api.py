"""Report operations of the API: the reads behind the Home blocks and their windows."""

import datetime as dt
from decimal import Decimal
from typing import Literal

from ninja import Router, Schema

from config import clock
from ledger.consultation import requested_billed_month
from planning import closing, goals, limits
from reports import analysis, home, worth

router = Router()


class MonthResult(Schema):
    currency: str
    income: Decimal
    expenses: Decimal
    left: Decimal
    previous_expenses: Decimal


class CategoryPart(Schema):
    category_id: int | None
    name: str
    amount: Decimal


class CategorySpending(CategoryPart):
    currency: str
    children: list[CategoryPart]


class DueRow(Schema):
    #: An invoice of a credit card, or one month of a repeating expense.
    kind: Literal["invoice", "bill"]
    invoice_id: int | None
    transaction_id: int | None
    month: dt.date
    title: str
    due_date: dt.date
    amount: Decimal
    currency: str
    #: AWAITING: a month of a repeating expense that waits for confirmation.
    status: Literal["SCHEDULED", "PARTIAL", "OVERDUE", "PAID", "AWAITING"]


class WorthSummary(Schema):
    currency: str
    net_worth: Decimal
    #: The net worth at the end of the month before.
    previous: Decimal
    #: The net worth of today minus ``previous``.
    change: Decimal
    #: False when an amount has no exchange rate to the base currency.
    complete: bool


class HomeLimit(Schema):
    """The limit of the month, in the currency of totals."""

    currency: str
    amount: Decimal
    #: The expenses of the month in that currency.
    expenses: Decimal
    income: Decimal
    #: The limit minus the expenses of the month.
    left: Decimal
    #: What is left for each day until the end of the month. Null when nothing is left.
    per_day: Decimal | None


class HomeGoal(Schema):
    id: int
    name: str
    currency: str
    target_amount: Decimal
    target_date: dt.date | None
    saved: Decimal
    remaining: Decimal
    percent: int
    status: Literal["reached", "overdue", "dated", "open"]
    monthly_needed: Decimal | None


class HomeClosing(Schema):
    """The month before the current one, while it waits for the owner."""

    month: dt.date
    #: False: the month is not closed. True: it is closed and its entries changed since.
    changed: bool


class HomeOut(Schema):
    month: dt.date
    #: Null when no month waits for its closing.
    closing: HomeClosing | None
    result: list[MonthResult]
    #: Null when the owner set no limit for the month.
    limit: HomeLimit | None
    goals: list[HomeGoal]
    spending: list[CategorySpending]
    due: list[DueRow]
    worth: WorthSummary
    #: Days since the owner last recorded an entry. Null without entries.
    days_since_last_entry: int | None


class TrendRow(Schema):
    month: dt.date
    currency: str
    income: Decimal
    expenses: Decimal


class MonthOut(Schema):
    month: dt.date
    result: list[MonthResult]
    spending: list[CategorySpending]
    trend: list[TrendRow]


class WorthPoint(Schema):
    as_of: dt.date
    currency: str
    accounts: Decimal
    investments: Decimal
    #: What the card statements owe: every purchase made and not paid yet.
    card_debt: Decimal
    #: What the cards owe to the owner. It counts as an asset.
    card_credits: Decimal
    net_worth: Decimal
    complete: bool
    missing_currencies: list[str]


class WorthMonth(Schema):
    month: dt.date
    accounts: Decimal
    investments: Decimal
    card_debt: Decimal
    net_worth: Decimal
    complete: bool


class WorthOut(Schema):
    today: WorthPoint
    #: Each month end of the last twelve months. The current month is today.
    months: list[WorthMonth]


def _month(value):
    """Return the first day of the requested month, or of the current month."""
    requested = requested_billed_month(value.strip())
    return dt.date(*requested, 1) if requested else clock.today().replace(day=1)


@router.get("/home", response=HomeOut, summary="Read the Home blocks of the current month")
def read_home(request):
    month = clock.today().replace(day=1)
    plan = limits.month_plan(request.user, month, clock.today())
    return {
        "month": month,
        "result": home.month_result(request.user, month),
        "limit": None
        if plan["limit"] is None
        else {
            "amount": plan["limit"],
            **{name: plan[name] for name in ("currency", "expenses", "income", "left", "per_day")},
        },
        "goals": goals.home_goals(request.user, clock.today()),
        "closing": closing.pending(request.user, clock.today()),
        "spending": home.spending_by_category(request.user, month),
        "due": home.due_soon(request.user, clock.today()),
        "worth": worth.summary(request.user, clock.today()),
        "days_since_last_entry": home.days_since_last_entry(request.user, clock.today()),
    }


@router.get("/month", response=MonthOut, summary="Read the analysis of one month")
def read_month(request, month: str = ""):
    first = _month(month)
    return {
        "month": first,
        "result": home.month_result(request.user, first),
        "spending": home.spending_by_category(request.user, first),
        "trend": home.trend(request.user, first),
    }


@router.get(
    "/net-worth", response=WorthOut, summary="Read the net worth and its last twelve months"
)
def read_net_worth(request):
    return worth.series(request.user, clock.today())


class FlowMonth(Schema):
    month: dt.date
    income: Decimal
    expenses: Decimal


class FlowCategory(Schema):
    category_id: int | None
    name: str
    amount: Decimal
    #: The amount in the period before.
    previous: Decimal
    change: Decimal
    #: The part of the expenses of the period, in percent. Null without expenses.
    share: Decimal | None
    #: The amount for each month of the period.
    average: Decimal
    #: The amount in each month of the period, in the order of ``months``.
    months: list[Decimal]


class Flow(Schema):
    currency: str
    income: Decimal
    expenses: Decimal
    result: Decimal
    previous_income: Decimal
    previous_expenses: Decimal
    previous_result: Decimal
    income_change: Decimal
    expenses_change: Decimal
    result_change: Decimal
    #: The change in percent of the period before. Null when that period has nothing.
    income_change_percent: Decimal | None
    expenses_change_percent: Decimal | None
    #: The amount for each month of the period.
    average_income: Decimal
    average_expenses: Decimal
    months: list[FlowMonth]
    #: Top-level expense categories, largest first.
    categories: list[FlowCategory]


class AnalysisWorthMonth(WorthMonth):
    #: What the positions cost. The value less the cost is what they earned.
    investments_cost: Decimal
    investments_gain: Decimal


class AnalysisWorth(Schema):
    currency: str
    #: The net worth at the end of the month before the period.
    before: Decimal
    #: From that month end to the end of the period.
    change: Decimal
    change_percent: Decimal | None
    investments_before: Decimal
    investments_change: Decimal
    complete: bool
    missing_currencies: list[str]
    months: list[AnalysisWorthMonth]


class AnalysisPosition(Schema):
    id: int
    name: str
    institution_name: str
    #: The value at the end of the period, in the base currency.
    value: Decimal
    #: The part of the invested total, in percent.
    share: Decimal | None


class AnalysisOut(Schema):
    start: dt.date
    end: dt.date
    months: list[dt.date]
    #: The first month of the period before, which has the same length.
    previous_start: dt.date
    #: False when the period before starts before the oldest record. Its
    #: totals are then incomplete, and the changes are not shown.
    comparable: bool
    #: The month of the oldest record and the current month: the widest period.
    first: dt.date
    last: dt.date
    #: One row for each currency with an amount. Amounts are not converted.
    flows: list[Flow]
    worth: AnalysisWorth
    positions: list[AnalysisPosition]


@router.get(
    "/analysis",
    response=AnalysisOut,
    summary="Read the analysis of a period of months, with the period before it",
)
def read_analysis(request, start: str = "", end: str = ""):
    return analysis.analysis(request.user, start, end, clock.today())


class OriginEntry(Schema):
    transaction_id: int
    title: str
    date: dt.date
    flow: Literal["INCOME", "EXPENSE"]
    currency: str
    #: The top-level category. A split entry has one row for each category.
    category_id: int | None
    category_name: str
    amount: Decimal
    installment_number: int | None
    installment_count: int | None
    split: bool


class OriginAccount(Schema):
    id: int
    name: str
    bank_name: str
    #: In the base currency. Null without an exchange rate.
    amount: Decimal | None


class OriginCard(Schema):
    card_id: int
    card_name: str
    #: The month of the statement.
    month: dt.date
    #: In the base currency. Negative: a card credit. Null without an exchange rate.
    amount: Decimal | None


class OriginWorth(Schema):
    as_of: dt.date
    currency: str
    accounts: list[OriginAccount]
    positions: list[AnalysisPosition]
    cards: list[OriginCard]


class OriginOperation(Schema):
    #: Null for the opening position of an investment.
    id: int | None
    position_id: int
    name: str
    institution_name: str
    kind: Literal["OPENING", "DEPOSIT", "WITHDRAWAL", "YIELD"]
    date: dt.date
    #: In the currency of the investment.
    value: Decimal
    currency: str


class OriginOut(Schema):
    month: dt.date
    entries: list[OriginEntry]
    worth: OriginWorth
    operations: list[OriginOperation]


@router.get(
    "/analysis/month",
    response=OriginOut,
    summary="Read what the figures of one month of the analysis are made of",
)
def read_analysis_month(request, month: str = ""):
    return analysis.origin(request.user, month, clock.today())
