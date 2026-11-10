"""Plan operations of the API: the limit of a month, the category budgets and the goals.

An operation reads a schema and calls ``planning.limits`` or
``planning.goals``. The amounts that it returns are calculated there.
"""

import datetime as dt
from decimal import Decimal
from typing import Literal

from django.core.exceptions import ValidationError
from ninja import Router, Schema

from accounts.models import UserPreference
from config import clock
from config.currencies import CURRENCIES
from config.ownership import owned, owned_choice
from config.validation import renamed
from ledger.categories import Category
from ledger.consultation import requested_billed_month
from planning import goals, limits
from planning.models import FinancialGoal

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
