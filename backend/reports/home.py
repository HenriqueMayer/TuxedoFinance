"""Reads for the Home blocks: the result of a month, spending by category and what is due.

Each read expands the owner's transactions with the occurrence engine
(``ledger.schedule``) for the months it needs. So a month uses the same rule
as the Transactions list: the billed month, which is the statement month of a
credit-card purchase and the occurrence month otherwise. An installment plan
counts one installment in each month.

Amounts are added by currency and never converted. A second currency is a
second row.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from banking.models import CardInvoice
from banking.settlements import attach_invoice_states
from config import clock
from ledger import commitments, schedule
from ledger.categories import Category
from ledger.models import Transaction, attach_schedule_rows

ZERO = Decimal("0.00")
TREND_MONTHS = 6
DUE_WINDOW_DAYS = 45
# How far back a month that waits for confirmation is still listed.
AWAITING_MONTHS = 12


def occurrences(user, first, last):
    """Return the occurrences of ``user`` with a reference month from ``first`` through ``last``."""
    items = attach_schedule_rows(
        Transaction.objects.filter(user=user)
        .select_related("bank_account", "debit_card__account", "credit_card__account")
        .prefetch_related("splits")
        .with_schedule_flags()
        .order_by("pk")
    )
    sources = tuple(item.schedule_source(splits=True) for item in items)
    return schedule.expand(sources, schedule.Window.months(first, last), allocations=True)


def flow_totals(items):
    """Return ``{(month, currency): {"INCOME": total, "EXPENSE": total}}`` for occurrences."""
    totals = defaultdict(lambda: {"INCOME": ZERO, "EXPENSE": ZERO})
    for occurrence in items:
        totals[occurrence.reference_month, occurrence.currency][occurrence.flow] += (
            occurrence.amount
        )
    return totals


def month_result(user, month):
    """Return the income, the expenses and their difference for ``month``, by currency.

    ``previous_expenses`` is the expense total of the month before, for comparison.
    """
    previous = schedule.offset_month(month, -1)
    flows = flow_totals(occurrences(user, previous, month))
    currencies = sorted({currency for (when, currency) in flows if when == month})
    return [
        {
            "currency": currency,
            "income": flows[month, currency]["INCOME"],
            "expenses": flows[month, currency]["EXPENSE"],
            "left": flows[month, currency]["INCOME"] - flows[month, currency]["EXPENSE"],
            "previous_expenses": flows[previous, currency]["EXPENSE"]
            if (previous, currency) in flows
            else ZERO,
        }
        for currency in currencies
    ]


def trend(user, month, months=TREND_MONTHS):
    """Return the income and the expenses of the ``months`` months that end with ``month``."""
    first = schedule.offset_month(month, -(months - 1))
    flows = flow_totals(occurrences(user, first, month))
    currencies = sorted({currency for (_when, currency) in flows})
    rows = []
    for offset in range(months):
        when = schedule.offset_month(first, offset)
        for currency in currencies:
            values = flows.get((when, currency), {"INCOME": ZERO, "EXPENSE": ZERO})
            rows.append(
                {
                    "month": when,
                    "currency": currency,
                    "income": values["INCOME"],
                    "expenses": values["EXPENSE"],
                }
            )
    return rows


def spending_by_category(user, month):
    """Return the expenses of ``month`` by top-level category, largest first.

    A subcategory counts in its top-level category and is listed under it.
    A split transaction counts in each of its categories.
    """
    categories = {
        row["id"]: row
        for row in Category.objects.filter(user=user).values("id", "name", "parent_category_id")
    }

    def top_of(category_id):
        seen = set()
        while category_id in categories and categories[category_id]["parent_category_id"]:
            if category_id in seen:  # A legacy cycle: stop instead of looping.
                break
            seen.add(category_id)
            category_id = categories[category_id]["parent_category_id"]
        return category_id

    totals = defaultdict(lambda: defaultdict(lambda: ZERO))
    for occurrence in occurrences(user, month, month):
        if occurrence.flow != "EXPENSE":
            continue
        for category_id, amount in occurrence.allocations:
            totals[occurrence.currency, top_of(category_id)][category_id] += amount

    rows = []
    for (currency, top_id), parts in totals.items():
        rows.append(
            {
                "currency": currency,
                "category_id": top_id,
                "name": categories.get(top_id, {}).get("name", ""),
                "amount": sum(parts.values(), ZERO),
                "children": sorted(
                    (
                        {
                            "category_id": category_id,
                            "name": categories.get(category_id, {}).get("name", ""),
                            "amount": amount,
                        }
                        for category_id, amount in parts.items()
                        if category_id != top_id
                    ),
                    key=lambda child: (-child["amount"], child["name"]),
                ),
            }
        )
    return sorted(rows, key=lambda row: (row["currency"], -row["amount"], row["name"]))


def _due_invoices(user, today, limit):
    """Invoices with an amount to pay that are overdue or due on or before ``limit``.

    An invoice that settles from its account on the due date is listed until
    that date, because the money leaves the account then.
    """
    invoices = attach_invoice_states(
        CardInvoice.objects.filter(user=user, due_date__lte=limit, amount__gt=0)
        .select_related("card__account")
        .prefetch_related("payments")
        .order_by("due_date", "pk")
    )
    rows = []
    for invoice in invoices:
        state = invoice.current_state
        if state.remaining_amount <= ZERO:
            continue
        rows.append(
            {
                "kind": "invoice",
                "invoice_id": invoice.pk,
                "transaction_id": None,
                "month": invoice.reference_month,
                "title": invoice.card.name,
                "due_date": invoice.due_date,
                "amount": state.remaining_amount,
                "currency": invoice.card.account.currency,
                "status": state.status,
            }
        )
    return rows


def _due_bills(user, today, limit):
    """Months of repeating expenses that wait for confirmation or fall on or before ``limit``.

    A repeating expense on a credit card is not listed: it is part of an
    invoice. A month that needs no confirmation is listed until its date.
    """
    items = attach_schedule_rows(
        Transaction.objects.filter(
            user=user,
            transaction_type="EXPENSE",
            is_fixed=True,
            installments=1,
            reward_redemption__isnull=True,
        )
        .exclude(payment_channel="CREDIT_CARD")
        .select_related("bank_account", "debit_card__account")
        .with_schedule_flags()
        .order_by("pk")
    )
    first = schedule.offset_month(today, -AWAITING_MONTHS)
    rows = []
    for item in items:
        for month in commitments.schedule_months(item, first, limit, today=today):
            upcoming = (
                month.status in (schedule.SCHEDULED, schedule.ADJUSTED, schedule.EXPECTED)
                and month.cash_date is not None
                and today <= month.cash_date <= limit
            )
            if not (month.awaiting or upcoming):
                continue
            rows.append(
                {
                    "kind": "bill",
                    "invoice_id": None,
                    "transaction_id": item.pk,
                    "month": month.month,
                    "title": item.title,
                    "due_date": month.cash_date,
                    "amount": month.amount,
                    "currency": item.native_currency,
                    "status": "AWAITING" if month.awaiting else "SCHEDULED",
                }
            )
    return rows


def due_soon(user, today, days=DUE_WINDOW_DAYS):
    """Return what the owner must pay soon, by date: invoices and months of repeating expenses."""
    limit = today + timedelta(days=days)
    rows = _due_invoices(user, today, limit) + _due_bills(user, today, limit)
    return sorted(rows, key=lambda row: (row["due_date"], row["title"]))


def days_since_last_entry(user, today):
    """Return how many days ago the owner last recorded an entry, or None without entries.

    The day is the day of recording in the financial time zone, not the date
    written on the entry: an entry recorded today for last week counts as today.
    """
    recorded = (
        Transaction.objects.filter(user=user, reward_redemption__isnull=True)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if recorded is None:
        return None
    return max(0, (today - clock.local_date(recorded)).days)
