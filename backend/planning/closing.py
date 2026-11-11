"""The closing of a month: a short review that the owner does once for each month.

The review has three parts:

1. **Balances.** For each account, the owner can type the balance that the
   bank shows at the end of the month. ``banking.reconciliation`` keeps that
   check, gives the difference to the recorded balance and, when the owner
   asks, records one adjustment that removes it.
2. **Result.** The income, the expenses and the limit of the month
   (``planning.limits``), the net worth at its end (``reports.worth``) and
   what the month left open: overdue invoices and months of repeating
   expenses that wait for confirmation.
3. **Next limit.** The limit from the month after, which the owner keeps or
   changes.

Closing records the month with the income and the expenses that the owner
saw (``MonthClosing``). It locks nothing. When those totals change later, the
review says that the month changed since its closing.

A month is checked on its last day, or on today while it is the current
month. Totals are in the currency of totals.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from banking import reconciliation
from banking.models import BalanceCheckpoint, BankAccount
from banking.services import account_balances
from config import clock
from ledger import schedule
from ledger.models import Transaction
from planning import limits
from planning.models import MonthClosing
from reports import home, worth

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
SPENDING_ROWS = 5
OPEN_STATUSES = ("OVERDUE", "AWAITING", "PARTIAL")


def _check_month(month, today):
    if month.day != 1:
        raise ValidationError({"month": _("Choose the first day of a month.")})
    if month > today.replace(day=1):
        raise ValidationError({"month": _("This month has not started.")})


def check_date(month, today):
    """Return the day on which the balances of ``month`` are compared."""
    last = schedule.offset_month(month, 1) - timedelta(days=1)
    return min(last, today)


def _changed(user, closing):
    """Return whether the totals of a closed month differ from the totals that were closed."""
    totals = home.flow_totals(home.occurrences(user, closing.month, closing.month)).get(
        (closing.month, closing.currency), {"INCOME": ZERO, "EXPENSE": ZERO}
    )
    return (closing.income, closing.expenses) != (totals["INCOME"], totals["EXPENSE"])


def pending(user, today):
    """Return what Home asks about the month before the current one, or None.

    ``{"month", "changed"}``: the month is not closed and the owner has an
    entry dated before the current month (``changed`` false), or the month
    is closed and its totals changed since (``changed`` true).
    """
    current = today.replace(day=1)
    previous = schedule.offset_month(today, -1)
    closing = MonthClosing.objects.filter(user=user, month=previous).first()
    if closing is not None:
        return {"month": previous, "changed": True} if _changed(user, closing) else None
    if not Transaction.objects.filter(user=user, date__lt=current).exists():
        return None
    return {"month": previous, "changed": False}


def default_month(user, today):
    """Return the month that the review opens on.

    The month before, while Home asks about it or the owner has no closing
    of it yet; otherwise the current month.
    """
    previous = schedule.offset_month(today, -1)
    closing = MonthClosing.objects.filter(user=user, month=previous).first()
    if closing is None or _changed(user, closing):
        return previous
    return today.replace(day=1)


def _accounts(user, on):
    """Return each account that exists on ``on`` with its recorded and its typed balance."""
    checks = {
        check.account_id: check
        for check in BalanceCheckpoint.objects.filter(user=user, date=on).select_related(
            "account", "adjustment"
        )
    }
    rows = []
    for row in account_balances(user, as_of=on):
        account = row["account"]
        if account.predates_opening(on):
            continue
        check = checks.get(account.pk)
        tracked = row["balance"].quantize(CENTS)
        rows.append(
            {
                "account_id": account.pk,
                "name": f"{account.bank.name} · {account.name}",
                "currency": account.currency,
                "date": on,
                "tracked": tracked,
                "statement": check.statement_balance if check else None,
                "difference": check.statement_balance - tracked if check else None,
                "adjusted": bool(check and check.adjustment_id),
            }
        )
    return sorted(rows, key=lambda row: row["name"].casefold())


def _open_items(user, today, on):
    rows = home.due_through(user, today, on)
    return [row for row in rows if row["status"] in OPEN_STATUSES and row["due_date"] <= on]


def review(user, month, today):
    """Return the closing review of ``month``."""
    _check_month(month, today)
    on = check_date(month, today)
    plan = limits.month_plan(user, month, today)
    closing = MonthClosing.objects.filter(user=user, month=month).first()
    sources = worth.Sources(user)
    at_end = worth.net_worth(sources, on)
    before = worth.net_worth(sources, month - timedelta(days=1))
    following = schedule.offset_month(month, 1)
    spending = [
        row for row in home.spending_by_category(user, month) if row["currency"] == plan["currency"]
    ]
    return {
        "month": month,
        "currency": plan["currency"],
        "is_closed": closing is not None,
        "closed_on": clock.local_date(closing.closed_at) if closing else None,
        "changed_since": bool(
            closing and (closing.income, closing.expenses) != (plan["income"], plan["expenses"])
        ),
        "accounts": _accounts(user, on),
        "open_items": _open_items(user, today, on),
        "result": {
            "income": plan["income"],
            "expenses": plan["expenses"],
            "result": plan["income"] - plan["expenses"],
            "limit": plan["limit"],
            "left": plan["left"],
        },
        "spending": spending[:SPENDING_ROWS],
        "worth": {
            "net_worth": at_end["net_worth"],
            "change": at_end["net_worth"] - before["net_worth"],
            "complete": at_end["complete"] and before["complete"],
        },
        "next_limit": {"month": following, "amount": limits.effective(user, following).get(None)},
    }


def _check(user, account, on):
    return BalanceCheckpoint.objects.filter(user=user, account=account, date=on).first()


@transaction.atomic
def set_balance(user, month, account, balance, today):
    """Record the balance that the bank shows for ``account``. None removes the check."""
    _check_month(month, today)
    on = check_date(month, today)
    check = _check(user, account, on)
    if balance is None:
        if check:
            reconciliation.delete_checkpoint(user=user, checkpoint_id=check.pk)
        return
    # A check with an adjustment keeps its balance: the adjustment was made for it.
    if check and check.adjustment_id and check.statement_balance != balance:
        reconciliation.remove_adjustment(user=user, checkpoint_id=check.pk)
        check.refresh_from_db()
    reconciliation.save_checkpoint(
        user=user, account=account, checkpoint=check, date=on, statement_balance=balance
    )


@transaction.atomic
def adjust(user, month, account, difference, today):
    """Record the adjustment that makes the recorded balance equal to the typed one.

    ``difference`` is the difference that the owner saw. Another difference
    is refused, so the owner never confirms an amount that was not shown.
    """
    _check_month(month, today)
    check = _check(user, account, check_date(month, today))
    stale = ValidationError({"difference": _("The difference changed. Read the balances again.")})
    if check is None:
        raise stale
    try:
        reconciliation.record_adjustment(
            user=user, checkpoint_id=check.pk, expected_difference=difference
        )
    except reconciliation.AlreadyAdjusted:
        return
    except (reconciliation.NoDifference, reconciliation.StaleDifference):
        raise stale from None


@transaction.atomic
def remove_adjustment(user, month, account, today):
    _check_month(month, today)
    check = _check(user, account, check_date(month, today))
    if check is not None:
        reconciliation.remove_adjustment(user=user, checkpoint_id=check.pk)


@transaction.atomic
def close(user, month, today, *, next_limit=None):
    """Record ``month`` as closed with the totals of now. ``next_limit`` sets the limit after it."""
    _check_month(month, today)
    if next_limit is not None:
        if next_limit <= ZERO:
            raise ValidationError({"next_limit": _("Enter an amount greater than zero.")})
        limits.set_limit(user, schedule.offset_month(month, 1), next_limit)
    plan = limits.month_plan(user, month, today)
    MonthClosing.objects.update_or_create(
        user=user,
        month=month,
        defaults={
            "income": plan["income"],
            "expenses": plan["expenses"],
            "currency": plan["currency"],
        },
    )


def reopen(user, month):
    MonthClosing.objects.filter(user=user, month=month).delete()


def owned_account(user, account_id):
    """Return the owned account of a request, or an error on ``account_id``."""
    account = BankAccount.objects.filter(user=user, pk=account_id).select_related("bank").first()
    if account is None:
        raise ValidationError({"account_id": _("Choose one of your own records.")})
    return account
