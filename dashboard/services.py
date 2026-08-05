"""Dashboard aggregation and projection helpers (PRD §7.1, §8.5).

Every figure on the dashboard is derived from `Transaction.amount_for_month`
/ `amount_through_month`, which decide how much a transaction contributes to
a given month: a fixed transaction repeats every month, an installment plan
spreads over consecutive months, a one-off lands once — and all three start
from the month the *payment* clears, which on a credit card with a billing
cycle is later than the month of the purchase.

That recurrence cannot be expressed as a `Sum(..., filter=Q(...))` over
`transaction_date`, so these helpers fetch the user's transactions **once**
(a single query, only the columns the math needs) and fold them in
Python. It stays one database round-trip per dashboard render; what it gives
up versus the previous pure-SQL aggregation is documented in
`docs/apps/dashboard.md`. Callers MUST always pass the logged-in user
(PRD R3 — never aggregate across users).
"""
from datetime import date
from decimal import Decimal

from django.utils import timezone

from transactions.models import Transaction

ZERO = Decimal('0.00')

# How many months ahead the outlook table projects, including the selected
# month itself. Six keeps the table readable; navigate to see further.
OUTLOOK_MONTHS = 6

# The reports page spans a full year so the trend has shape: this many months
# of history behind the current one, the rest projected ahead of it.
EVOLUTION_MONTHS = 12
EVOLUTION_PAST_MONTHS = 5

# Bars in the "where the money goes" breakdown. Beyond a handful the chart
# stops being a summary and becomes an unreadable second transaction list.
TOP_CATEGORIES = 6

# Bars in the payment-method breakdown. Higher than `TOP_CATEGORIES` because
# these bars are vertical: the limit here is how many axis labels fit side by
# side, not how tall the card grows. Payment methods are no longer seeded
# (FR14), so the cap only bites for someone tracking several cards.
TOP_PAYMENT_METHODS = 8


def add_months(year, month, offset):
    """Return the (year, month) pair `offset` whole months from (year, month)."""
    index = (year * 12 + month - 1) + offset
    return index // 12, index % 12 + 1


def _projection_queryset(user, with_category=False, with_payment_method=False):
    """The user's transactions, with only the columns the projection needs.

    `with_category` / `with_payment_method` add the related **name** for the
    breakdown charts. The payment method itself is always joined, cheaply, for
    the reason in the comment below.
    """
    # Every column `amount_for_month` / `amount_through_month` touches has to
    # be listed: a field left out of `only()` is deferred, and reading it
    # later costs one extra query *per row* — silently turning this single
    # round-trip into an N+1 (NFR10). `fixed_until` is read for every fixed
    # transaction, so it belongs here even though nothing displays it.
    fields = [
        'transaction_type',
        'amount',
        'installments',
        'is_fixed',
        'fixed_until',
        'transaction_date',
        # `months_from_start` now asks the card which month it is paid in, so
        # the first two are read for *every* transaction on *every* page — the
        # join is unconditional for the same reason the columns above are.
        # Losing it does not break the numbers, it quietly multiplies the
        # queries by the size of the transaction list. `due_day` moves no money
        # but rides along for free, and the transaction list renders it.
        'payment_method__method_type',
        'payment_method__best_purchase_day',
        'payment_method__due_day',
    ]
    queryset = Transaction.objects.filter(user=user).select_related('payment_method')

    if with_category:
        queryset = queryset.select_related('category')
        fields.append('category__name')

    if with_payment_method:
        fields.append('payment_method__name')

    return queryset.only(*fields)


def _totals(transactions, year, month, cumulative=False):
    """Fold transactions into per-type totals for one month, or through it."""
    types = Transaction.TransactionType
    totals = {types.INCOME: ZERO, types.EXPENSE: ZERO, types.INVESTMENT: ZERO}

    for txn in transactions:
        contribution = (
            txn.amount_through_month(year, month)
            if cumulative
            else txn.amount_for_month(year, month)
        )
        if contribution:
            totals[txn.transaction_type] += contribution

    income = totals[types.INCOME]
    expenses = totals[types.EXPENSE]
    investments = totals[types.INVESTMENT]

    return {
        'income': income,
        'expenses': expenses,
        'investments': investments,
        # PRD §8.5: Investment is a cash outflow, subtracted from the balance
        # but never merged into the Expenses indicator.
        'balance': income - expenses - investments,
    }


def get_dashboard_summary(user, year=None, month=None):
    """Return the dashboard indicators for `user`, scoped to their own data.

    `year`/`month` select which month the "(month)" cards describe; they
    default to the current month and may point into the future, which is what
    makes the dashboard a forecast rather than a report (FR15).

    Figures (PRD §8.5, decision 2026-07-24 — Investment is a cash outflow
    subtracted from every balance but kept distinct from Expenses):
      - Current Balance   = everything realized through *today's* month.
      - Income/Expenses/Investments (month), Balance (month) = the selected
        month alone, including recurrences of fixed and installment rows.
      - Projected Balance = Current Balance rolled forward to the end of the
        selected month (equal to Current Balance when viewing this month).
      - Outlook           = the next `OUTLOOK_MONTHS` months from the selected
        one, each with its own net and running projected balance.
    """
    today = timezone.localdate()
    if year is None or month is None:
        year, month = today.year, today.month

    # One query; every figure below is folded from this list in memory.
    transactions = list(_projection_queryset(user))

    selected = _totals(transactions, year, month)
    current_balance = _totals(transactions, today.year, today.month, cumulative=True)[
        'balance'
    ]
    projected_balance = _totals(transactions, year, month, cumulative=True)['balance']

    # Running balance, rolled forward month by month from the selected one.
    # Starting point is the balance at the *end of the previous* month, so the
    # first row lands exactly on `projected_balance` — no repeated cumulative
    # folds over the transaction list.
    outlook = []
    running_balance = projected_balance - selected['balance']
    for offset in range(OUTLOOK_MONTHS):
        outlook_year, outlook_month = add_months(year, month, offset)
        month_totals = _totals(transactions, outlook_year, outlook_month)
        running_balance += month_totals['balance']
        outlook.append(
            {
                'year': outlook_year,
                'month': outlook_month,
                'date': date(outlook_year, outlook_month, 1),
                'is_current_month': (outlook_year, outlook_month)
                == (today.year, today.month),
                'is_selected_month': offset == 0,
                **month_totals,
                'projected_balance': running_balance,
            }
        )

    return {
        'selected_year': year,
        'selected_month': month,
        'selected_month_date': date(year, month, 1),
        'is_current_month': (year, month) == (today.year, today.month),
        'is_future_month': (year, month) > (today.year, today.month),
        'current_balance': current_balance,
        'projected_balance': projected_balance,
        'income_month': selected['income'],
        'expense_month': selected['expenses'],
        'investment_month': selected['investments'],
        'balance_month': selected['balance'],
        'outlook': outlook,
    }


def _expenses_by_category(transactions, year, month, months):
    """Rank category names by total expense over a window of `months` months.

    Expenses only: Income has no category worth breaking down here, and
    Investment is deliberately kept out so this answers "where does my
    spending go", not "where does my money go" (PRD §8.5 keeps the two
    outflows distinct everywhere else too).
    """
    window = [add_months(year, month, offset) for offset in range(months)]
    totals = {}

    for txn in transactions:
        if txn.transaction_type != Transaction.TransactionType.EXPENSE:
            continue
        total = sum(
            (txn.amount_for_month(*target) for target in window), start=ZERO
        )
        if total:
            name = txn.category.name
            totals[name] = totals.get(name, ZERO) + total

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return []

    largest = ranked[0][1]
    overall = sum(totals.values(), start=ZERO)

    return [
        {
            'name': name,
            'total': total,
            # Bar width is relative to the biggest category (so the chart
            # always fills its width); the printed share is of all spending.
            'bar_width': round(float(total / largest) * 100, 2),
            'share': round(float(total / overall) * 100, 1),
        }
        for name, total in ranked[:TOP_CATEGORIES]
    ]


def get_expenses_by_payment_method(user, year=None, month=None, months=1):
    """Split expenses across the methods that paid for them (FR16).

    Two scopes, picked by the caller:
      - the default (`year`/`month` set, `months=1`) answers "July went on
        which card?" — a single-month question the rest of the page averages
        out and the user is then left unable to read. Recurrences count on
        the same rules as every other figure here: a fixed subscription and
        the current slice of an installment plan both land on the month they
        are actually paid, not on the month they were first recorded.
      - `year=None, month=None, months=N` aggregates the last N months
        anchored on today, so the "All time" option on the filter can answer
        "where does my spending go, in aggregate?" without losing the
        per-method resolution.

    Expenses only, like `_expenses_by_category` — income arrives independently
    of how anything is paid, and Investment stays a distinct outflow (§8.5).
    """
    transactions = _projection_queryset(user, with_payment_method=True)

    if year is not None and month is not None:
        window = [(year, month)]
    else:
        today = timezone.localdate()
        window = [add_months(today.year, today.month, -step) for step in range(months)]

    totals = {}
    for txn in transactions:
        if txn.transaction_type != Transaction.TransactionType.EXPENSE:
            continue
        contribution = sum(
            (txn.amount_for_month(*target) for target in window), start=ZERO
        )
        if contribution:
            name = txn.payment_method.name
            totals[name] = totals.get(name, ZERO) + contribution

    overall = sum(totals.values(), start=ZERO)
    if not overall:
        return {'total': ZERO, 'methods': [], 'shown': 0, 'used': 0}

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    methods = [
        {
            'name': name,
            'total': total,
            'share': round(float(total / overall) * 100, 1),
        }
        for name, total in ranked[:TOP_PAYMENT_METHODS]
    ]

    return {
        # Every method's spending, including any trimmed off by the cap — so the
        # printed shares stay shares of the period, not of what is drawn.
        'total': overall,
        'methods': methods,
        # `shown` < `used` means the cap trimmed something, and the drawn shares
        # therefore stop short of 100%. The template says so rather than leaving
        # the reader to notice the bars do not add up to the total above them.
        'shown': len(methods),
        'used': len(ranked),
    }


def get_expenses_by_category_for_method(
    user, method_name, year=None, month=None, months=1
):
    """Top categories paid with a single method, over a window of `months`.

    Companion to the "Spending by payment method" chart: clicking a bar
    filters the page to a single method, and this answers the next
    question — "what did I buy on that card, and in which categories?".

    Same rules as every other breakdown on the page:
      - Expenses only (income / investment are out by §8.5).
      - Recurrences count via `amount_for_month`, so a fixed subscription
        on a credit card shows under every month it charges — exactly the
        shape the dashboard and reports use everywhere else.
      - The window is a single month when `year`/`month` are set, or the
        last `months` months from today when they are `None` (the
        `?payment_month=ALL` case).

    Returns an empty list when the method had no expenses in the window,
    or when `method_name` is not one of the user's methods — the view
    treats both as "no data to show" without differentiating.
    """
    transactions = _projection_queryset(
        user, with_category=True, with_payment_method=True
    )

    if year is not None and month is not None:
        window = [(year, month)]
    else:
        today = timezone.localdate()
        window = [add_months(today.year, today.month, -step) for step in range(months)]

    totals = {}
    for txn in transactions:
        if txn.transaction_type != Transaction.TransactionType.EXPENSE:
            continue
        if txn.payment_method.name != method_name:
            continue
        contribution = sum(
            (txn.amount_for_month(*target) for target in window), start=ZERO
        )
        if contribution:
            name = txn.category.name
            totals[name] = totals.get(name, ZERO) + contribution

    if not totals:
        return []

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    largest = ranked[0][1]
    overall = sum(totals.values(), start=ZERO)

    return [
        {
            'name': name,
            'total': total,
            # Same dual-percent convention as `_expenses_by_category`:
            # `bar_width` is relative to the biggest (so the top bar always
            # fills the track), `share` is of all spending on this method.
            'bar_width': round(float(total / largest) * 100, 2),
            'share': round(float(total / overall) * 100, 1),
        }
        for name, total in ranked[:TOP_CATEGORIES]
    ]


def get_income_by_payment_method(user, year=None, month=None, months=1):
    """Split income across the methods that received it (FR16).

    Mirror of `get_expenses_by_payment_method` for the new "Income by
    payment method" chart on the reports page — the same two scopes, the
    same drill-down, the same `?payment_month=ALL|YYYY-MM` filter, only
    filtering on `INCOME` rows. Salary hits a bank account, dividends
    land on a brokerage, transfers arrive on a card: the bar chart is
    the mirror image of the spending one and answers "where did the
    money come in on?".

    Two scopes, picked by the caller:
      - the default (`year`/`month` set, `months=1`) answers "July's income
        landed where?" — a single-month question. Recurrences count on the
        same rules as every other figure: a fixed paycheck and the current
        slice of an installment plan both land on the month they actually
        pay in.
      - `year=None, month=None, months=N` aggregates the last N months
        anchored on today, so the "All time" option on the filter answers
        "where does my income go, in aggregate?" without losing the
        per-method resolution.

    Income only, like the expense version. Investment is a cash outflow
    on the spending side (§8.5) and is not income on this side either —
    a buy is not a receipt.
    """
    transactions = _projection_queryset(user, with_payment_method=True)

    if year is not None and month is not None:
        window = [(year, month)]
    else:
        today = timezone.localdate()
        window = [add_months(today.year, today.month, -step) for step in range(months)]

    totals = {}
    for txn in transactions:
        if txn.transaction_type != Transaction.TransactionType.INCOME:
            continue
        contribution = sum(
            (txn.amount_for_month(*target) for target in window), start=ZERO
        )
        if contribution:
            name = txn.payment_method.name
            totals[name] = totals.get(name, ZERO) + contribution

    overall = sum(totals.values(), start=ZERO)
    if not overall:
        return {'total': ZERO, 'methods': [], 'shown': 0, 'used': 0}

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    methods = [
        {
            'name': name,
            'total': total,
            'share': round(float(total / overall) * 100, 1),
        }
        for name, total in ranked[:TOP_PAYMENT_METHODS]
    ]

    return {
        # Every method's income, including any trimmed off by the cap — so
        # the printed shares stay shares of the period, not of what is drawn.
        'total': overall,
        'methods': methods,
        # `shown` < `used` means the cap trimmed something, and the drawn
        # shares therefore stop short of 100%. The template says so rather
        # than leaving the reader to notice the bars do not add up.
        'shown': len(methods),
        'used': len(ranked),
    }


def get_income_by_category_for_method(
    user, method_name, year=None, month=None, months=1
):
    """Top categories of income received on a single method, over a window.

    Companion to the "Income by payment method" chart: clicking a bar
    filters the page to a single method, and this answers the next
    question — "what kinds of income did I receive there?". A salary
    account might show "Salary" + "Reimbursements"; a brokerage might
    show "Dividends" + "Asset sales".

    Same rules as every other breakdown on the page:
      - Income only (expenses / investment are out by §8.5).
      - Recurrences count via `amount_for_month`, so a fixed monthly
        paycheck shows under every month it pays in — the same shape the
        dashboard and reports use everywhere else.
      - The window is a single month when `year`/`month` are set, or the
        last `months` months from today when they are `None` (the
        `?payment_month=ALL` case).

    Returns an empty list when the method had no income in the window,
    or when `method_name` is not one of the user's methods — the view
    treats both as "no data to show" without differentiating.
    """
    transactions = _projection_queryset(
        user, with_category=True, with_payment_method=True
    )

    if year is not None and month is not None:
        window = [(year, month)]
    else:
        today = timezone.localdate()
        window = [add_months(today.year, today.month, -step) for step in range(months)]

    totals = {}
    for txn in transactions:
        if txn.transaction_type != Transaction.TransactionType.INCOME:
            continue
        if txn.payment_method.name != method_name:
            continue
        contribution = sum(
            (txn.amount_for_month(*target) for target in window), start=ZERO
        )
        if contribution:
            name = txn.category.name
            totals[name] = totals.get(name, ZERO) + contribution

    if not totals:
        return []

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    largest = ranked[0][1]
    overall = sum(totals.values(), start=ZERO)

    return [
        {
            'name': name,
            'total': total,
            # Same dual-percent convention as `_expenses_by_category`:
            # `bar_width` is relative to the biggest (so the top bar
            # always fills the track), `share` is of all income on this
            # method.
            'bar_width': round(float(total / largest) * 100, 2),
            'share': round(float(total / overall) * 100, 1),
        }
        for name, total in ranked[:TOP_CATEGORIES]
    ]


def get_account_evolution(user, offset=0):
    """Month-by-month series for the reports page (FR16).

    Returns `EVOLUTION_MONTHS` consecutive months anchored on today — or on
    today shifted by `offset` whole months, which is how the page's prev/next
    arrows slide the 12-month window through time. `EVOLUTION_PAST_MONTHS` of
    history, the (shifted) "current" month, and the rest projected forward
    on exactly the same recurrence rules as the dashboard outlook.

    History and forecast share one series on purpose. The charts are about
    the *shape* of the account over time, and a seam between "real" and
    "projected" months would only be visual noise — the template marks which
    is which instead. `is_current_month` follows the shifted anchor so the
    label always sits on the month the user is currently looking at, and
    `is_future` keeps the dimmer stroke on the projected half of the window.
    """
    today = timezone.localdate()
    anchor_year, anchor_month = add_months(today.year, today.month, offset)

    # One query, folded in memory below — see the module docstring.
    transactions = list(_projection_queryset(user, with_category=True))

    start_year, start_month = add_months(
        anchor_year, anchor_month, -EVOLUTION_PAST_MONTHS
    )

    # Where the account stood the month *before* the window opens, so the
    # running balance below starts from the right place after a single
    # cumulative fold instead of one per rendered month.
    opening_year, opening_month = add_months(start_year, start_month, -1)
    opening_balance = _totals(
        transactions, opening_year, opening_month, cumulative=True
    )['balance']

    months = []
    running_balance = opening_balance
    for step in range(EVOLUTION_MONTHS):
        month_year, month_month = add_months(start_year, start_month, step)
        month_totals = _totals(transactions, month_year, month_month)
        running_balance += month_totals['balance']
        months.append(
            {
                'year': month_year,
                'month': month_month,
                'date': date(month_year, month_month, 1),
                'is_current_month': (month_year, month_month)
                == (anchor_year, anchor_month),
                'is_future': (month_year, month_month) > (anchor_year, anchor_month),
                **month_totals,
                'closing_balance': running_balance,
            }
        )

    # Always present: the window is built around the (shifted) anchor by
    # construction, so the marker for "what we're looking at" lives in the
    # series, not in a parallel lookup the view would otherwise have to do.
    current = next(row for row in months if row['is_current_month'])

    return {
        'months': months,
        'current_month': current,
        'anchor_year': anchor_year,
        'anchor_month': anchor_month,
        'anchor_date': date(anchor_year, anchor_month, 1),
        'is_anchored_today': offset == 0,
        'opening_balance': opening_balance,
        'closing_balance': running_balance,
        # Net movement across the whole window — the single number that says
        # whether the account is growing or shrinking over the year.
        'net_change': running_balance - opening_balance,
        'best_month': max(months, key=lambda row: row['balance']),
        'worst_month': min(months, key=lambda row: row['balance']),
        'expenses_by_category': _expenses_by_category(
            transactions, start_year, start_month, EVOLUTION_MONTHS
        ),
    }
