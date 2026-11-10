"""Report operations of the API: the reads behind the Home blocks."""

import datetime as dt
from decimal import Decimal
from typing import Literal

from ninja import Router, Schema

from config import clock
from ledger.consultation import requested_billed_month
from reports import home

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
    invoice_id: int
    title: str
    due_date: dt.date
    amount: Decimal
    currency: str
    status: Literal["SCHEDULED", "PARTIAL", "OVERDUE", "PAID"]
    confirm_payments: bool


class HomeOut(Schema):
    month: dt.date
    result: list[MonthResult]
    spending: list[CategorySpending]
    due: list[DueRow]


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


def _month(value):
    """Return the first day of the requested month, or of the current month."""
    requested = requested_billed_month(value.strip())
    return dt.date(*requested, 1) if requested else clock.today().replace(day=1)


@router.get("/home", response=HomeOut, summary="Read the Home blocks of the current month")
def read_home(request):
    month = clock.today().replace(day=1)
    return {
        "month": month,
        "result": home.month_result(request.user, month),
        "spending": home.spending_by_category(request.user, month),
        "due": home.due_soon(request.user, clock.today()),
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
