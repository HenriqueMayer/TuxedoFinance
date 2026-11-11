"""The analysis of a period of months: flows, categories, cards, net worth and investments.

A period is a run of whole months that ends at the current month or before
it. Each figure comes with the same figure of the period before, which has
the same length and ends where the period starts.

The flows use the rule of the Home blocks (``reports.home``): the billed
month of each occurrence, added by currency and never converted. The net
worth uses ``reports.worth``: the month end of each month, or today for the
current month, in the base currency.

The cards use the same billed month: the statement of a month is the card
expenses that the month bills. What the cards owe and their later statements
follow today, not the period.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Min

from banking.models import CreditCard
from investments.models import Asset, Investment
from ledger import schedule
from ledger.consultation import requested_billed_month
from ledger.models import Transaction
from reports import home, worth

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
DEFAULT_MONTHS = 6
# A longer period costs one net worth calculation for each month.
MAX_MONTHS = 60
# How many statements after the current month the cards show.
UPCOMING_MONTHS = 12


def _percent(part, whole):
    """Return ``part`` as a percentage of ``whole`` with one decimal, or None without a whole."""
    if whole <= ZERO:
        return None
    return (part * 100 / whole).quantize(Decimal("0.1"))


def _requested(text):
    """Return the first day of the month that ``text`` names ("YYYY-MM"), or None."""
    requested = requested_billed_month((text or "").strip())
    return schedule.offset_month(_date(*requested), 0) if requested else None


def _date(year, month):
    return schedule.day_in_month(year * 12 + month - 1, 1)


def period(start, end, today):
    """Return the months of the requested period, oldest first.

    The period ends at the current month at the latest, starts at its end at
    the latest and has at most ``MAX_MONTHS`` months. Without a valid end it
    ends at the current month; without a valid start it has six months.
    """
    current = today.replace(day=1)
    last = min(_requested(end) or current, current)
    first = _requested(start) or schedule.offset_month(last, -(DEFAULT_MONTHS - 1))
    first = max(min(first, last), schedule.offset_month(last, -(MAX_MONTHS - 1)))
    count = schedule.months_between(first, last.year, last.month) + 1
    return [schedule.offset_month(first, offset) for offset in range(count)]


def first_month(user, today):
    """Return the month of the oldest record of ``user``, or the current month."""
    dates = [
        Transaction.objects.filter(user=user).aggregate(first=Min("date"))["first"],
        Asset.objects.filter(user=user).aggregate(first=Min("opening_date"))["first"],
        Investment.objects.filter(user=user).aggregate(first=Min("date"))["first"],
        today,
    ]
    return min(value for value in dates if value).replace(day=1)


def flows(user, months):
    """Return the income, the expenses and the categories of ``months``, by currency.

    Each row has the totals of the period, the totals of the period before,
    one row for each month and the top-level expense categories. A category
    has its amount in the period, in the period before and in each month. A
    category with an amount in the period before alone is listed with zero.
    """
    before = [schedule.offset_month(months[0], offset) for offset in range(-len(months), 0)]
    names, top_of = home.category_tops(user)
    totals = defaultdict(lambda: defaultdict(lambda: {"INCOME": ZERO, "EXPENSE": ZERO}))
    categories = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: ZERO)))
    for occurrence in home.occurrences(user, before[0], months[-1]):
        month, currency = occurrence.reference_month, occurrence.currency
        totals[currency][month][occurrence.flow] += occurrence.amount
        if occurrence.flow == "EXPENSE":
            for category_id, amount in occurrence.allocations:
                categories[currency][top_of(category_id)][month] += amount

    def total(by_month, span, flow):
        return sum((by_month[month][flow] for month in span if month in by_month), ZERO)

    rows = []
    for currency in sorted(totals):
        by_month = totals[currency]
        income, expenses = total(by_month, months, "INCOME"), total(by_month, months, "EXPENSE")
        previous_income = total(by_month, before, "INCOME")
        previous_expenses = total(by_month, before, "EXPENSE")
        if not any((income, expenses, previous_income, previous_expenses)):
            continue
        parts = []
        for category_id, amounts in categories[currency].items():
            amount = sum((amounts[month] for month in months), ZERO)
            previous = sum((amounts[month] for month in before), ZERO)
            parts.append(
                {
                    "category_id": category_id,
                    "name": names.get(category_id, ""),
                    "amount": amount,
                    "previous": previous,
                    "change": amount - previous,
                    "share": _percent(amount, expenses),
                    "average": (amount / len(months)).quantize(CENTS),
                    "months": [amounts[month] for month in months],
                }
            )
        rows.append(
            {
                "currency": currency,
                "income": income,
                "expenses": expenses,
                "result": income - expenses,
                "previous_income": previous_income,
                "previous_expenses": previous_expenses,
                "previous_result": previous_income - previous_expenses,
                "income_change": income - previous_income,
                "expenses_change": expenses - previous_expenses,
                "result_change": (income - expenses) - (previous_income - previous_expenses),
                "income_change_percent": _percent(income - previous_income, previous_income),
                "expenses_change_percent": _percent(
                    expenses - previous_expenses, previous_expenses
                ),
                "average_income": (income / len(months)).quantize(CENTS),
                "average_expenses": (expenses / len(months)).quantize(CENTS),
                "months": [
                    {
                        "month": month,
                        "income": by_month[month]["INCOME"] if month in by_month else ZERO,
                        "expenses": by_month[month]["EXPENSE"] if month in by_month else ZERO,
                    }
                    for month in months
                ],
                "categories": sorted(
                    (part for part in parts if part["amount"] or part["previous"]),
                    key=lambda part: (-part["amount"], -part["previous"], part["name"]),
                ),
            }
        )
    return rows


def _card_categories(amounts, names, total):
    """Return the categories of card statements, largest first, with their part of ``total``."""
    return sorted(
        (
            {
                "category_id": category_id,
                "name": names.get(category_id, ""),
                "amount": amount,
                "share": _percent(amount, total),
            }
            for category_id, amount in amounts.items()
            if amount
        ),
        key=lambda part: (-part["amount"], part["name"]),
    )


def cards(user, months, today):
    """Return the credit cards in ``months``, by currency of their account.

    Each row has the statements of the period added over the cards, and one
    row for each card. A statement is the card expenses that its month bills,
    with one installment of a plan in each month. The totals come with the
    period before. ``owed`` is what the cards owe today, with the later
    installments. ``upcoming`` has the statements after the current month, up
    to the last one that already has an amount. The categories are the
    top-level categories of the statements of the period. A card without any
    of these amounts is not listed, and a currency without a card has no row.
    """
    before = [schedule.offset_month(months[0], offset) for offset in range(-len(months), 0)]
    current = today.replace(day=1)
    ahead = [schedule.offset_month(current, offset) for offset in range(1, UPCOMING_MONTHS + 1)]
    names, top_of = home.category_tops(user)
    period_months = set(months)
    statements = defaultdict(lambda: defaultdict(lambda: ZERO))
    categories = defaultdict(lambda: defaultdict(lambda: ZERO))
    for occurrence in home.occurrences(user, before[0], ahead[-1]):
        instrument = occurrence.instrument
        if instrument.channel != schedule.CREDIT_CARD or occurrence.flow != "EXPENSE":
            continue
        statements[instrument.instrument_id][occurrence.reference_month] += occurrence.amount
        if occurrence.reference_month in period_months:
            for category_id, amount in occurrence.allocations:
                categories[instrument.instrument_id][top_of(category_id)] += amount
    owed = defaultdict(lambda: ZERO)
    for row in worth.card_debt(worth.Sources(user), today):
        owed[row["card_id"]] += row["amount"]

    by_currency = defaultdict(list)
    for card in CreditCard.objects.filter(user=user).select_related("account").order_by("pk"):
        by_month = statements[card.pk]
        total = sum((by_month[month] for month in months), ZERO)
        previous = sum((by_month[month] for month in before), ZERO)
        upcoming = [by_month[month] for month in ahead]
        debt = owed[card.pk].quantize(CENTS)
        if not (total or previous or debt or any(upcoming)):
            continue
        by_currency[card.account.currency].append(
            {
                "id": card.pk,
                "name": card.name,
                "account_name": card.account.name,
                "months": [by_month[month] for month in months],
                "total": total,
                "previous": previous,
                "change": total - previous,
                "change_percent": _percent(total - previous, previous),
                "average": (total / len(months)).quantize(CENTS),
                "owed": debt,
                "upcoming": upcoming,
                "categories": _card_categories(categories[card.pk], names, total),
            }
        )

    rows = []
    for currency in sorted(by_currency):
        listed = by_currency[currency]
        total = sum((card["total"] for card in listed), ZERO)
        previous = sum((card["previous"] for card in listed), ZERO)
        # The later statements end at the last month with an amount on any card.
        count = max(
            (
                index + 1
                for card in listed
                for index, amount in enumerate(card["upcoming"])
                if amount
            ),
            default=0,
        )
        parts = defaultdict(lambda: ZERO)
        for card in listed:
            card["upcoming"] = card["upcoming"][:count]
            card["upcoming_total"] = sum(card["upcoming"], ZERO)
            card["share"] = _percent(card["total"], total)
            for part in card["categories"]:
                parts[part["category_id"]] += part["amount"]
        upcoming = [
            sum((card["upcoming"][index] for card in listed), ZERO) for index in range(count)
        ]
        rows.append(
            {
                "currency": currency,
                "months": [
                    sum((card["months"][index] for card in listed), ZERO)
                    for index in range(len(months))
                ],
                "total": total,
                "previous": previous,
                "change": total - previous,
                "change_percent": _percent(total - previous, previous),
                "average": (total / len(months)).quantize(CENTS),
                "owed": sum((card["owed"] for card in listed), ZERO),
                "upcoming_months": ahead[:count],
                "upcoming": upcoming,
                "upcoming_total": sum(upcoming, ZERO),
                "categories": _card_categories(parts, names, total),
                "cards": sorted(listed, key=lambda card: (-card["total"], card["name"])),
            }
        )
    return rows


def _as_of(month, today):
    """Return the date that stands for ``month``: its last day, or today for the current month."""
    if month == today.replace(day=1):
        return today
    return schedule.offset_month(month, 1) - timedelta(days=1)


def wealth(user, months, today):
    """Return the net worth of each month and the positions at the end of the period.

    ``before`` is the net worth at the end of the month before the period.
    A position is listed with its value in the base currency, largest first.
    """
    sources = worth.Sources(user)
    points = [worth.net_worth(sources, _as_of(month, today)) for month in months]
    before = worth.net_worth(sources, months[0] - timedelta(days=1))
    positions = worth.positions(sources, _as_of(months[-1], today))
    last = points[-1]
    missing = sorted({code for point in points for code in point["missing_currencies"]})
    return {
        "worth": {
            "currency": sources.conversion.base_currency,
            "before": before["net_worth"],
            "change": last["net_worth"] - before["net_worth"],
            "change_percent": _percent(
                last["net_worth"] - before["net_worth"], before["net_worth"]
            ),
            "investments_before": before["investments"],
            "investments_change": last["investments"] - before["investments"],
            "complete": all(point["complete"] for point in points) and before["complete"],
            "missing_currencies": missing,
            "months": [
                {
                    "month": month,
                    "investments_gain": point["investments"] - point["investments_cost"],
                    **{
                        name: point[name]
                        for name in (
                            "accounts",
                            "investments",
                            "investments_cost",
                            "card_debt",
                            "net_worth",
                            "complete",
                        )
                    },
                }
                for month, point in zip(months, points, strict=True)
            ],
        },
        "positions": positions,
    }


def analysis(user, start, end, today):
    """Return the analysis of the requested period for ``user``."""
    months = period(start, end, today)
    previous_start = schedule.offset_month(months[0], -len(months))
    first = first_month(user, today)
    return {
        "start": months[0],
        "end": months[-1],
        "months": months,
        "previous_start": previous_start,
        # Before the oldest record there is nothing to compare with: the
        # totals of the period before would be too small, and each change too large.
        "comparable": previous_start >= first,
        "first": first,
        "last": today.replace(day=1),
        "flows": flows(user, months),
        "cards": cards(user, months, today),
        **wealth(user, months, today),
    }


def entries(user, month):
    """Return the entries that make the income and the expenses of ``month``.

    One row for each entry and top-level category: a split entry has one row
    for each of its categories. The rows of a flow add up to the amount of
    that flow in the month. Income comes first; each flow is listed from its
    largest amount.
    """
    names, top_of = home.category_tops(user)
    found = [
        occurrence
        for occurrence in home.occurrences(user, month, month)
        if occurrence.source_type == schedule.TRANSACTION
    ]
    titles = dict(
        Transaction.objects.filter(
            user=user, pk__in={occurrence.source_id for occurrence in found}
        ).values_list("pk", "title")
    )
    rows = []
    for occurrence in found:
        parts = defaultdict(lambda: ZERO)
        for category_id, amount in occurrence.allocations:
            parts[top_of(category_id)] += amount
        number, count = occurrence.installment or (None, None)
        for category_id, amount in parts.items():
            rows.append(
                {
                    "transaction_id": occurrence.source_id,
                    "title": titles.get(occurrence.source_id, ""),
                    "date": occurrence.economic_date,
                    "flow": occurrence.flow,
                    "currency": occurrence.currency,
                    "category_id": category_id,
                    "category_name": names.get(category_id, ""),
                    "card_id": (
                        occurrence.instrument.instrument_id
                        if occurrence.instrument.channel == schedule.CREDIT_CARD
                        else None
                    ),
                    "amount": amount,
                    "installment_number": number,
                    "installment_count": count,
                    "split": len(parts) > 1,
                }
            )
    return sorted(
        rows, key=lambda row: (row["flow"] != "INCOME", -row["amount"], row["title"], row["date"])
    )


def operations(user, first, last):
    """Return the investment operations dated from ``first`` to ``last``, oldest first.

    The opening position of an investment is listed on its date, with the
    kind ``OPENING``. Each value is in the currency of its investment.
    """
    rows = [
        {
            "id": None,
            "position_id": asset.pk,
            "name": asset.name,
            "institution_name": asset.opening_product.bank.name,
            "kind": "OPENING",
            "date": asset.opening_date,
            "value": (
                asset.opening_balance + asset.opening_quantity * asset.opening_unit_price
            ).quantize(CENTS),
            "currency": asset.currency,
        }
        for asset in Asset.objects.filter(
            user=user,
            opening_product__isnull=False,
            opening_date__gte=first,
            opening_date__lte=last,
        ).select_related("opening_product__bank")
    ]
    for operation in Investment.objects.filter(
        user=user, date__gte=first, date__lte=last
    ).select_related("asset", "product__bank"):
        rows.append(
            {
                "id": operation.pk,
                "position_id": operation.asset_id,
                "name": operation.asset.name,
                "institution_name": operation.product.bank.name,
                "kind": operation.kind,
                "date": operation.date,
                "value": operation.gross_value.quantize(CENTS),
                "currency": operation.asset.currency,
            }
        )
    return sorted(rows, key=lambda row: (row["date"], row["id"] or 0))


def origin(user, text, today):
    """Return what the figures of one month are made of.

    The month is the requested one, or the current month when the request
    names no month or a later one. The net worth is read on the date that
    stands for the month in the analysis.
    """
    current = today.replace(day=1)
    month = min(_requested(text) or current, current)
    as_of = _as_of(month, today)
    sources = worth.Sources(user)
    return {
        "month": month,
        "entries": entries(user, month),
        "worth": {
            "as_of": as_of,
            "currency": sources.conversion.base_currency,
            **worth.composition(sources, as_of),
        },
        "operations": operations(user, month, as_of),
    }
