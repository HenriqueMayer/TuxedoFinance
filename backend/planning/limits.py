"""The limit of a month and the budgets of its categories.

A limit holds from its month on (``planning.models.SpendingLimit``). The read
compares it with the expenses of the month, by the rule of the Home blocks
(``reports.home``): the billed month, with the repeating entries that the
month still expects. Only entries in the currency of totals count.
"""

import calendar
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from accounts.models import UserPreference
from ledger import schedule
from ledger.categories import Category
from planning.models import SpendingLimit
from reports import home

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
AVERAGE_MONTHS = 3


def effective(user, month):
    """Return ``{category_id: amount}`` for ``month``. The key None is the limit of the month."""
    limits = {}
    rows = SpendingLimit.objects.filter(user=user, start_month__lte=month).order_by("start_month")
    for category_id, amount in rows.values_list("category_id", "amount"):
        limits[category_id] = amount
    return {key: amount for key, amount in limits.items() if amount is not None}


@transaction.atomic
def set_limit(user, month, amount, category=None):
    """Set the limit of ``category`` (None: of the month) from ``month`` on.

    An ``amount`` of None ends the limit from ``month`` on. The months before
    ``month`` keep their values. A value that a later month had is replaced.
    """
    if month.day != 1:
        raise ValidationError({"month": _("Choose the first day of a month.")})
    if amount is not None and amount <= ZERO:
        raise ValidationError({"amount": _("Enter an amount greater than zero.")})
    rows = SpendingLimit.objects.filter(user=user, category=category)
    rows.filter(start_month__gte=month).delete()
    before = rows.order_by("-start_month").values_list("amount", flat=True).first()
    if amount == before:
        return  # The earlier row already says this, or there is no limit to end.
    row = SpendingLimit(user=user, category=category, start_month=month, amount=amount)
    row.full_clean()
    row.save()


def _families(user):
    """Return ``{category_id: its top-level category id}`` and the category names."""
    rows = {
        row["id"]: row
        for row in Category.objects.filter(user=user).values(
            "id", "name", "parent_category_id", "transaction_type"
        )
    }

    def chain(category_id):
        seen = []
        while category_id in rows and category_id not in seen:
            seen.append(category_id)
            category_id = rows[category_id]["parent_category_id"]
        return seen

    return rows, {category_id: chain(category_id) for category_id in rows}


def _spent_by_category(occurrences, currency, chains):
    """Return ``{(month, category_id): expenses}``; a category includes its subcategories."""
    spent = defaultdict(lambda: ZERO)
    for occurrence in occurrences:
        if occurrence.flow != "EXPENSE" or occurrence.currency != currency:
            continue
        for category_id, amount in occurrence.allocations:
            for ancestor in chains.get(category_id, ()):
                spent[occurrence.reference_month, ancestor] += amount
    return spent


def month_plan(user, month, today):
    """Return the limit, the budgets and the flows of ``month``, in the currency of totals.

    - ``left``: the limit minus the expenses of the month. None without a limit.
    - ``per_day``: for the current month, ``left`` over the days from today
      through the end of the month. None when nothing is left.
    - ``budgets``: each category with a limit, by name.
    - ``suggestions``: each top-level expense category without a budget that
      has expenses in ``month`` or in the three months before, with the
      average of those three months.
    """
    currency = UserPreference.for_user(user).base_currency
    first = schedule.offset_month(month, -AVERAGE_MONTHS)
    occurrences = home.occurrences(user, first, month)
    categories, chains = _families(user)
    spent = _spent_by_category(occurrences, currency, chains)
    flows = home.flow_totals(occurrences).get((month, currency), {"INCOME": ZERO, "EXPENSE": ZERO})
    limits = effective(user, month)
    limit = limits.pop(None, None)
    left = None if limit is None else limit - flows["EXPENSE"]
    is_current = month == today.replace(day=1)
    per_day = None
    if is_current and left is not None and left > ZERO:
        days = calendar.monthrange(today.year, today.month)[1] - today.day + 1
        per_day = (left / days).quantize(CENTS)

    budgets = [
        {
            "category_id": category_id,
            "name": categories[category_id]["name"],
            "limit": amount,
            "spent": spent[month, category_id],
            "left": amount - spent[month, category_id],
        }
        for category_id, amount in limits.items()
        if category_id in categories
    ]
    before = [schedule.offset_month(month, -offset) for offset in range(1, AVERAGE_MONTHS + 1)]
    suggestions = []
    for category_id, row in categories.items():
        if row["parent_category_id"] or row["transaction_type"] == "INCOME":
            continue
        if category_id in limits:
            continue
        earlier = sum((spent[when, category_id] for when in before), ZERO)
        if spent[month, category_id] or earlier:
            suggestions.append(
                {
                    "category_id": category_id,
                    "name": row["name"],
                    "spent": spent[month, category_id],
                    "average": (earlier / AVERAGE_MONTHS).quantize(CENTS),
                }
            )
    return {
        "month": month,
        "currency": currency,
        "is_current": is_current,
        "income": flows["INCOME"],
        "expenses": flows["EXPENSE"],
        "limit": limit,
        "left": left,
        "per_day": per_day,
        "budgets": sorted(budgets, key=lambda row: row["name"].casefold()),
        "suggestions": sorted(suggestions, key=lambda row: (-row["spent"], row["name"].casefold())),
    }
