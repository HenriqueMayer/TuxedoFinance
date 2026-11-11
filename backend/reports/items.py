"""The analysis of one item of the Wallet: an investment, an account or a card.

Each analysis covers the twelve months that end with the current month. It
gives the item month by month, the totals of the period, and the item beside
every item of its kind: its part of the total.

The amounts of the item are in its own currency. The comparison is in the
base currency, with the rates of today; an item without a rate is left out
of the comparison.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from banking.models import BankMovement, CreditCard
from banking.services import MissingExchangeRate, account_balances
from investments.models import Asset
from investments.positions import replay_positions, value_positions
from ledger import schedule
from reports import home, worth

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
MONTHS = 12


def _months(today):
    """Return the first day of each of the twelve months to the current one."""
    current = today.replace(day=1)
    return [schedule.offset_month(current, offset) for offset in range(-(MONTHS - 1), 1)]


def _as_of(month, today):
    """Return the date that stands for ``month``: its last day, or today for the current month."""
    if month == today.replace(day=1):
        return today
    return schedule.offset_month(month, 1) - timedelta(days=1)


def _percent(part, whole):
    """Return ``part`` as a percentage of ``whole`` with one decimal, or None without a whole."""
    if whole <= ZERO:
        return None
    return (part * 100 / whole).quantize(Decimal("0.1"))


def _share(rows, current):
    """Return the comparison of one item with every item of its kind.

    ``rows`` are ``(id, names, value)`` with ``names`` a dict of the name
    fields of the item and ``value`` in the base currency, or None without an
    exchange rate. The items are listed from the largest value.
    """
    counted = [(pk, names, value) for pk, names, value in rows if value is not None]
    total = sum((value for _pk, _names, value in counted), ZERO)
    mine = next((value for pk, _names, value in counted if pk == current), ZERO)
    return {
        "value": mine.quantize(CENTS),
        "total": total.quantize(CENTS),
        "percent": _percent(mine, total),
        "items": [
            {
                "id": pk,
                **names,
                "value": value.quantize(CENTS),
                "share": _percent(value, total),
                "current": pk == current,
            }
            for pk, names, value in sorted(
                counted, key=lambda row: (-row[2], str(sorted(row[1].items())))
            )
        ],
    }


def investment(asset, today):
    """Return the analysis of one investment.

    Each month has the value at its end and what moved in it: deposits,
    withdrawals and yields. The opening position counts as a deposit of its
    month. ``gain`` is the value less the cost of the units that are held;
    a balance has no unit cost, so its gain is None and its yields say what
    it earned.
    """
    user = asset.user
    sources = worth.Sources(user)
    operations = [item for item in sources.operations if item.asset_id == asset.pk]
    prices = [item for item in sources.prices if item.asset_id == asset.pk]
    base = sources.conversion.base_currency

    def valued(as_of):
        rows = replay_positions([asset], operations, as_of)
        return value_positions(
            user, rows, prices, base, as_of, historical=True, conversion=sources.conversion
        )["positions"]

    moved = defaultdict(lambda: defaultdict(lambda: ZERO))
    if asset.has_opening_position and asset.opening_date:
        moved[asset.opening_date.replace(day=1)]["DEPOSIT"] += (
            asset.opening_balance + asset.opening_quantity * asset.opening_unit_price
        )
    for operation in operations:
        if operation.date <= today:
            moved[operation.date.replace(day=1)][operation.kind] += operation.gross_value

    months = []
    for month in _months(today):
        rows = valued(_as_of(month, today))
        months.append(
            {
                "month": month,
                "value": sum((row["valuation"] for row in rows), ZERO).quantize(CENTS),
                "deposits": moved[month]["DEPOSIT"].quantize(CENTS),
                "withdrawals": moved[month]["WITHDRAWAL"].quantize(CENTS),
                "yields": moved[month]["YIELD"].quantize(CENTS),
            }
        )
    now = valued(today)
    units = asset.valuation_mode == Asset.ValuationMode.UNITS
    gains = [row["unrealized_gain"] for row in now if row["unrealized_gain"] is not None]
    positions = worth.positions(sources, today)
    return {
        "id": asset.pk,
        "name": asset.name,
        "institution_name": asset.opening_product.bank.name,
        "currency": asset.currency,
        "base_currency": base,
        "months": months,
        "value": months[-1]["value"],
        "gain": sum(gains, ZERO).quantize(CENTS) if units and gains else None,
        "deposits": sum((row["deposits"] for row in months), ZERO),
        "withdrawals": sum((row["withdrawals"] for row in months), ZERO),
        "yields": sum((row["yields"] for row in months), ZERO),
        "share": _share(
            [
                (
                    row["id"],
                    {"name": row["name"], "detail": row["institution_name"]},
                    row["value"],
                )
                for row in positions
            ],
            asset.pk,
        ),
    }


def account(item, today):
    """Return the analysis of one account.

    Each month has the balance at its end and what entered and left the
    account in it, with transfers and invoice payments. ``change`` is the
    balance of today less the balance at the end of the month before the
    period.
    """
    user = item.user
    sources = worth.Sources(user)
    months = _months(today)

    def balance(as_of):
        return next(
            (
                row["balance"]
                for row in account_balances(user, as_of)
                if row["account"].pk == item.pk
            ),
            ZERO,
        )

    moved = defaultdict(lambda: defaultdict(lambda: ZERO))
    for movement in BankMovement.objects.filter(
        user=user, account=item, effective_date__gte=months[0], effective_date__lte=today
    ):
        moved[movement.effective_date.replace(day=1)][movement.direction] += movement.amount
    rows = [
        {
            "month": month,
            "balance": balance(_as_of(month, today)),
            "inflow": moved[month][BankMovement.Direction.CREDIT].quantize(CENTS),
            "outflow": moved[month][BankMovement.Direction.DEBIT].quantize(CENTS),
        }
        for month in months
    ]
    before = balance(months[0] - timedelta(days=1))
    listed = worth.composition(sources, today)["accounts"]
    return {
        "id": item.pk,
        "name": item.name,
        "bank_name": item.bank.name,
        "currency": item.currency,
        "base_currency": sources.conversion.base_currency,
        "months": rows,
        "balance": rows[-1]["balance"],
        "change": rows[-1]["balance"] - before,
        "inflow": sum((row["inflow"] for row in rows), ZERO),
        "outflow": sum((row["outflow"] for row in rows), ZERO),
        "share": _share(
            [
                (row["id"], {"name": row["name"], "detail": row["bank_name"]}, row["amount"])
                for row in listed
            ],
            item.pk,
        ),
    }


def card(item, today):
    """Return the analysis of one credit card.

    Each month has its statement: the purchases that the month bills, with one
    installment of a plan in each month. ``owed`` is what the card owes
    today, with the later installments. The categories are the top-level
    categories of the twelve statements.
    """
    user = item.user
    sources = worth.Sources(user)
    months = _months(today)
    names, top_of = home.category_tops(user)
    by_card = defaultdict(lambda: defaultdict(lambda: ZERO))
    categories = defaultdict(lambda: ZERO)
    for occurrence in home.occurrences(user, months[0], months[-1]):
        instrument = occurrence.instrument
        if instrument.channel != schedule.CREDIT_CARD or occurrence.flow != "EXPENSE":
            continue
        by_card[instrument.instrument_id][occurrence.reference_month] += occurrence.amount
        if instrument.instrument_id == item.pk:
            for category_id, amount in occurrence.allocations:
                categories[top_of(category_id)] += amount
    rows = [{"month": month, "amount": by_card[item.pk][month]} for month in months]
    total = sum((row["amount"] for row in rows), ZERO)

    def in_base(amount, currency):
        try:
            return sources.conversion.convert(amount, currency, as_of=today)
        except MissingExchangeRate:
            return None

    cards = CreditCard.objects.filter(user=user).select_related("account")
    return {
        "id": item.pk,
        "name": item.name,
        "account_name": item.account.name,
        "currency": item.account.currency,
        "base_currency": sources.conversion.base_currency,
        "months": rows,
        "total": total,
        "average": (total / MONTHS).quantize(CENTS),
        "owed": sum(
            (row["amount"] for row in worth.card_debt(sources, today) if row["card_id"] == item.pk),
            ZERO,
        ).quantize(CENTS),
        "categories": sorted(
            (
                {
                    "category_id": category_id,
                    "name": names.get(category_id, ""),
                    "amount": amount,
                    "share": _percent(amount, total),
                }
                for category_id, amount in categories.items()
                if amount
            ),
            key=lambda row: (-row["amount"], row["name"]),
        ),
        "share": _share(
            [
                (
                    other.pk,
                    {"name": other.name, "detail": other.account.name},
                    in_base(sum(by_card[other.pk].values(), ZERO), other.account.currency),
                )
                for other in cards
                if other.pk == item.pk or sum(by_card[other.pk].values(), ZERO)
            ],
            item.pk,
        ),
    }


def investment_of(user, pk):
    """Return the investment ``pk`` of ``user`` with its institution, or None."""
    return (
        Asset.objects.filter(user=user, pk=pk, opening_product__isnull=False)
        .select_related("opening_product__bank")
        .first()
    )
