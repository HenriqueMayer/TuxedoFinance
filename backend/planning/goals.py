"""Goals and the balances that back them.

A goal counts money that exists. The owner reserves a part of a balance for
it: of a bank account or of a balance investment. Terms:

- The *backed* amount of a reservation is the part of it that the positive
  balance of its source covers. When the reservations of one source ask for
  more than the balance, each one gets a share in proportion to its amount.
- *Saved* is the backed amount of a goal, in the currency of the goal.
- A reservation of an archived goal claims nothing.
"""

from collections import defaultdict
from decimal import ROUND_UP, Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from banking.models import BankAccount
from banking.services import MissingExchangeRate, account_balances, convert
from investments import portfolio
from investments.models import Asset
from planning.models import FinancialGoal, GoalAllocation

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")


def sources(user):
    """Return ``{key: source}`` for each balance that a goal can reserve, in display order.

    The key is ``account:<id>`` or ``investment:<id>``. An archived
    investment and an investment in units are not sources.
    """
    result = {}
    rows = sorted(
        account_balances(user),
        key=lambda row: (row["account"].bank.name.casefold(), row["account"].name.casefold()),
    )
    for row in rows:
        account = row["account"]
        result[f"account:{account.pk}"] = {
            "key": f"account:{account.pk}",
            "label": f"{account.bank.name} · {account.name}",
            "currency": account.currency,
            "balance": row["balance"],
        }
    for position in portfolio.overview(user)["positions"]:
        if position["valuation_mode"] != Asset.ValuationMode.MONETARY or position["is_archived"]:
            continue
        result[f"investment:{position['id']}"] = {
            "key": f"investment:{position['id']}",
            "label": f"{position['institution_name']} · {position['name']}",
            "currency": position["currency"],
            "balance": position["value"],
        }
    return result


def _active(user):
    return list(GoalAllocation.objects.filter(user=user, goal__is_archived=False).order_by("pk"))


def _backing(allocations, balances):
    """Return ``{allocation id: backed amount}`` for the active ``allocations``."""
    by_source = defaultdict(list)
    for allocation in allocations:
        by_source[allocation.source_key].append(allocation)
    backing = {}
    for key, rows in by_source.items():
        declared = sum((row.amount for row in rows), ZERO)
        balance = balances[key]["balance"] if key in balances else ZERO
        available = min(declared, max(ZERO, balance))
        # Cumulative rounding shares the cents and never claims more than the balance.
        cumulative = shared = ZERO
        for row in rows:
            cumulative += row.amount
            upto = (available * cumulative / declared).quantize(CENTS)
            backing[row.pk] = upto - shared
            shared = upto
    return backing


def _months_through(today, target):
    """Return the count of months from the month of ``today`` through the month of ``target``."""
    return (target.year - today.year) * 12 + target.month - today.month + 1


def read(user, today):
    """Return the goals of ``user`` with their progress, and the sources with what is free.

    A goal has a ``status``: ``reached``; ``overdue`` (its date passed);
    ``dated`` (it has a later date, and ``monthly_needed`` is what each month
    from now through that date must add); or ``open`` (no date).
    """
    balances = sources(user)
    active = _active(user)
    backing = _backing(active, balances)
    rates = {}

    def rate(from_currency, to_currency):
        pair = (from_currency, to_currency)
        if pair not in rates:
            try:
                rates[pair] = convert(user, Decimal("1"), *pair, as_of=today)
            except MissingExchangeRate:
                rates[pair] = None
        return rates[pair]

    goals = []
    for goal in FinancialGoal.objects.filter(user=user).prefetch_related("allocations"):
        saved, missing, reservations = ZERO, set(), []
        for allocation in goal.allocations.all():
            source = balances.get(allocation.source_key)
            if source is None:
                continue  # An archived investment: the reservation waits for it.
            backed = backing.get(allocation.pk, ZERO)
            reservations.append(
                {
                    "source": source["key"],
                    "label": source["label"],
                    "currency": source["currency"],
                    "amount": allocation.amount,
                    "backed": backed,
                }
            )
            factor = rate(source["currency"], goal.currency)
            if factor is None:
                missing.add(source["currency"])
            else:
                saved += backed * factor
        saved = saved.quantize(CENTS)
        remaining = max(ZERO, goal.target_amount - saved)
        monthly = None
        if remaining == ZERO:
            status = "reached"
        elif goal.target_date is None:
            status = "open"
        elif goal.target_date < today:
            status = "overdue"
        else:
            status = "dated"
            months = _months_through(today, goal.target_date)
            monthly = (remaining / months).quantize(CENTS, rounding=ROUND_UP)
        goals.append(
            {
                "id": goal.pk,
                "name": goal.name,
                "target_amount": goal.target_amount,
                "currency": goal.currency,
                "target_date": goal.target_date,
                "is_archived": goal.is_archived,
                "saved": saved,
                "remaining": remaining,
                "percent": min(100, int(saved / goal.target_amount * 100)),
                "status": status,
                "monthly_needed": monthly,
                "complete": not missing,
                "missing_currencies": sorted(missing),
                "reservations": reservations,
            }
        )

    reserved = defaultdict(lambda: ZERO)
    for allocation in active:
        reserved[allocation.source_key] += allocation.amount
    return {
        "goals": goals,
        "sources": [
            {**source, "free": max(ZERO, source["balance"] - reserved[key])}
            for key, source in balances.items()
        ],
    }


def _lock(user):
    """Serialize the reservations of one owner, so two goals cannot claim the same balance."""
    get_user_model().objects.select_for_update().get(pk=user.pk)


def _clean_name(name):
    name = name.strip()
    if not name:
        raise ValidationError({"name": _("Enter a name.")})
    return name


def create_goal(user, *, name, target_amount, currency, target_date=None):
    goal = FinancialGoal(
        user=user,
        name=_clean_name(name),
        target_amount=target_amount,
        currency=currency,
        target_date=target_date,
    )
    goal.full_clean()
    goal.save()
    return goal


def change_goal(goal, *, name, target_amount, target_date, is_archived):
    """Change a goal. Its currency stays: the saved amount is counted in it."""
    goal.name = _clean_name(name)
    goal.target_amount = target_amount
    goal.target_date = target_date
    goal.is_archived = is_archived
    goal.full_clean()
    goal.save()
    return goal


def _source_record(user, key):
    """Return ``(field, record)`` of the source that ``key`` names, or a field error."""
    kind, _separator, pk = key.partition(":")
    record = None
    if pk.isdecimal() and kind == "account":
        record = BankAccount.objects.filter(user=user, pk=pk).first()
    elif pk.isdecimal() and kind == "investment":
        record = Asset.objects.filter(
            user=user, pk=pk, valuation_mode=Asset.ValuationMode.MONETARY, is_archived=False
        ).first()
    if record is None:
        raise ValidationError({"source": _("Choose one of your accounts or balance investments.")})
    return ("bank_account" if kind == "account" else "asset"), record


@transaction.atomic
def set_reservation(goal, key, amount):
    """Reserve ``amount`` of the source ``key`` for ``goal``. Zero removes the reservation.

    A goal has one reservation for each source, so a second amount replaces
    the first. The active goals cannot reserve more than the positive balance.
    """
    user = goal.user
    _lock(user)
    if goal.is_archived:
        raise ValidationError(_("An archived goal cannot reserve a balance."))
    field, record = _source_record(user, key)
    if amount < ZERO:
        raise ValidationError({"amount": _("Enter zero or a positive amount.")})
    existing = GoalAllocation.objects.filter(goal=goal, **{field: record}).first()
    if amount == ZERO:
        if existing:
            existing.delete()
        return
    others = sum(
        (row.amount for row in _active(user) if row.source_key == key and row.goal_id != goal.pk),
        ZERO,
    )
    free = max(ZERO, sources(user)[key]["balance"] - others)
    if amount > free:
        raise ValidationError(
            {
                "amount": _("This balance has %(amount)s free for this goal.")
                % {"amount": f"{free:.2f}"}
            }
        )
    allocation = existing or GoalAllocation(user=user, goal=goal, **{field: record})
    allocation.amount = amount
    allocation.full_clean()
    allocation.save()


def home_goals(user, today):
    """Return the active goals as Home shows them."""
    names = (
        "id",
        "name",
        "currency",
        "target_amount",
        "target_date",
        "saved",
        "remaining",
        "percent",
        "status",
        "monthly_needed",
    )
    return [
        {name: goal[name] for name in names}
        for goal in read(user, today)["goals"]
        if not goal["is_archived"]
    ]
