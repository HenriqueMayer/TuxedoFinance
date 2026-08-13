"""Aggregations shared by the dashboard and reports views."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from banking.models import (
    BankAccount,
    BankMovement,
    CardInvoice,
    LoyaltyEntry,
    RewardRedemption,
)
from banking.services import MissingExchangeRate, convert
from investments.models import Investment
from investments.services import historical_value_in_base
from transactions.models import Transaction
from accounts.models import UserPreference


ZERO = Decimal('0.00')
OUTLOOK_MONTHS = 6
EVOLUTION_MONTHS = 12
EVOLUTION_PAST_MONTHS = 5
TOP_CATEGORIES = 6
TOP_INSTRUMENTS = 8


def add_months(year, month, offset):
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1


def _month_end(year, month):
    return date(year, month, monthrange(year, month)[1])


def _window(year, month, months):
    return [add_months(year, month, offset) for offset in range(months)]


def _transactions(user):
    return list(
        Transaction.objects.filter(user=user)
        .select_related(
            'category',
            'bank_account__bank',
            'debit_card__account__bank',
            'credit_card__account__bank',
        )
    )


def _convert_or_missing(user, amount, currency, as_of, missing):
    try:
        return convert(user, amount, currency, UserPreference.for_user(user).base_currency, as_of=as_of)
    except MissingExchangeRate:
        missing.add(currency)
        return None


def get_ledger_snapshot(user, as_of):
    """Return native account balances and the safely converted consolidation."""
    accounts = BankAccount.objects.filter(user=user).select_related('bank')
    rows = []
    total = ZERO
    missing = set()
    for account in accounts:
        native = account.opening_balance
        movements = BankMovement.objects.filter(
            user=user, account=account, effective_date__lte=as_of
        ).only('direction', 'amount', 'source_key')
        for movement in movements:
            native += movement.signed_amount
        converted = _convert_or_missing(
            user, native, account.currency, as_of, missing
        )
        if converted is not None:
            total += converted
        rows.append(
            {
                'account': account,
                'label': f'{account.bank.name} > {account.name}',
                'currency': account.currency,
                'native_balance': native,
                'converted_balance': converted,
            }
        )
    return {
        'as_of': as_of,
        'total': total,
        'accounts': rows,
        'missing_currencies': sorted(missing),
    }


def _investment_value(user, operation, base_currency, missing):
    value = historical_value_in_base(
        user, operation, base_currency,
        on_date=operation.date,
    )
    if value is None:
        missing.add(operation.asset.currency)
    return value


def _investment_totals(user, window):
    wanted = set(window)
    total = ZERO
    missing = set()
    base_currency = UserPreference.for_user(user).base_currency
    operations = Investment.objects.filter(
        user=user, kind=Investment.Kind.DEPOSIT
    ).select_related('asset', 'source_account')
    for operation in operations:
        if (operation.date.year, operation.date.month) not in wanted:
            continue
        value = _investment_value(user, operation, base_currency, missing)
        if value is not None:
            total += value
    return total, sorted(missing)


def _transaction_value(user, transaction, year, month, missing):
    amount = transaction.amount_for_month(year, month)
    if not amount:
        return ZERO
    account = transaction.payment_account
    if account is None:
        return amount
    converted = _convert_or_missing(
        user, amount, account.currency, _month_end(year, month), missing
    )
    return converted


def _monthly_totals(user, transactions, year, month):
    income = ZERO
    expenses = ZERO
    missing = set()
    for item in transactions:
        value = _transaction_value(user, item, year, month, missing)
        if value is None:
            continue
        if item.transaction_type == Transaction.TransactionType.INCOME:
            income += value
        elif item.transaction_type == Transaction.TransactionType.EXPENSE:
            expenses += value
    banking_expenses, banking_missing = _banking_expenses_for_month(
        user, year, month
    )
    expenses += banking_expenses
    missing.update(banking_missing)
    investments, investment_missing = _investment_totals(user, [(year, month)])
    missing.update(investment_missing)
    return {
        'income': income,
        'expenses': expenses,
        'investments': investments,
        'balance': income - expenses - investments,
        'missing_currencies': sorted(missing),
    }


def _banking_expenses_for_month(user, year, month):
    """Return points purchases and reward IOF without duplicating transactions."""
    total = ZERO
    missing = set()
    purchases = LoyaltyEntry.objects.filter(
        user=user,
        kind=LoyaltyEntry.Kind.PURCHASE,
        direction=LoyaltyEntry.Direction.CREDIT,
        cash_amount__isnull=False,
    ).select_related('funding_account', 'funding_credit_card__account')
    for entry in purchases:
        account = entry.funding_account or entry.funding_credit_card.account
        expense_month = (
            entry.funding_credit_card.statement_month(entry.date)
            if entry.funding_credit_card_id
            else entry.date.replace(day=1)
        )
        if (expense_month.year, expense_month.month) != (year, month):
            continue
        value = _convert_or_missing(
            user, entry.cash_amount, account.currency, _month_end(year, month), missing
        )
        if value is not None:
            total += value

    redemptions = RewardRedemption.objects.filter(
        user=user, iof_amount__gt=ZERO
    ).select_related('iof_account', 'iof_credit_card__account')
    for redemption in redemptions:
        account = redemption.iof_account or redemption.iof_credit_card.account
        expense_month = (
            redemption.iof_credit_card.statement_month(redemption.date)
            if redemption.iof_credit_card_id
            else redemption.date.replace(day=1)
        )
        if (expense_month.year, expense_month.month) != (year, month):
            continue
        value = _convert_or_missing(
            user, redemption.iof_amount, account.currency, _month_end(year, month), missing
        )
        if value is not None:
            total += value
    return total, sorted(missing)


def get_dashboard_summary(user, year=None, month=None):
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month
    transactions = _transactions(user)
    selected = _monthly_totals(user, transactions, year, month)
    current = get_ledger_snapshot(user, today)
    projected = get_ledger_snapshot(user, _month_end(year, month))

    outlook = []
    missing = set(current['missing_currencies']) | set(projected['missing_currencies'])
    for offset in range(OUTLOOK_MONTHS):
        row_year, row_month = add_months(year, month, offset)
        totals = _monthly_totals(user, transactions, row_year, row_month)
        snapshot = get_ledger_snapshot(user, _month_end(row_year, row_month))
        missing.update(totals['missing_currencies'])
        missing.update(snapshot['missing_currencies'])
        outlook.append(
            {
                'year': row_year,
                'month': row_month,
                'date': date(row_year, row_month, 1),
                'is_current_month': (row_year, row_month) == (today.year, today.month),
                'is_selected_month': offset == 0,
                **totals,
                'projected_balance': snapshot['total'],
            }
        )

    invoices = list(
        CardInvoice.objects.filter(user=user, status=CardInvoice.Status.SCHEDULED)
        .select_related('card__account__bank')
        .order_by('due_date', 'card__name')
    )
    return {
        'selected_year': year,
        'selected_month': month,
        'selected_month_date': date(year, month, 1),
        'is_current_month': (year, month) == (today.year, today.month),
        'is_future_month': (year, month) > (today.year, today.month),
        'current_balance': current['total'],
        'projected_balance': projected['total'],
        'account_balances': current['accounts'],
        'open_invoices': invoices,
        'next_invoice': invoices[0] if invoices else None,
        'income_month': selected['income'],
        'expense_month': selected['expenses'],
        'investment_month': selected['investments'],
        'balance_month': selected['balance'],
        'missing_currencies': sorted(missing | set(selected['missing_currencies'])),
        'outlook': outlook,
    }


def _category_rows(totals):
    if not totals:
        return []
    ranked = sorted(totals.values(), key=lambda row: row['total'], reverse=True)
    largest = ranked[0]['total']
    overall = sum((row['total'] for row in ranked), ZERO)
    for row in ranked[:TOP_CATEGORIES]:
        row['bar_width'] = round(float(row['total'] / largest) * 100, 2)
        row['share'] = round(float(row['total'] / overall) * 100, 1)
    return ranked[:TOP_CATEGORIES]


def _expenses_by_category(user, transactions, year, month, months):
    targets = _window(year, month, months)
    totals = {}
    missing = set()
    for item in transactions:
        if item.transaction_type != Transaction.TransactionType.EXPENSE:
            continue
        value = sum(
            (
                _transaction_value(user, item, y, m, missing) or ZERO
                for y, m in targets
            ),
            ZERO,
        )
        if value:
            row = totals.setdefault(
                item.category_id,
                {'id': item.category_id, 'name': item.category.name, 'total': ZERO},
            )
            row['total'] += value
    return _category_rows(totals), sorted(missing)


def _instrument(item, income=False):
    if income:
        account = item.bank_account
        return (
            f'account:{account.pk}',
            f'{account.bank.name} > {account.name}',
        )
    if item.credit_card_id:
        card = item.credit_card
        return (
            f'cc:{card.pk}',
            f'{card.account.bank.name} > {card.account.name} / {card.name}',
        )
    if item.debit_card_id:
        card = item.debit_card
        return (
            f'dc:{card.pk}',
            f'{card.account.bank.name} > {card.account.name} / {card.name}',
        )
    account = item.bank_account
    return (
        f'account:{account.pk}',
        f'{account.bank.name} > {account.name}',
    )


def _instrument_breakdown(user, transaction_type, year=None, month=None, months=1):
    transactions = _transactions(user)
    if year is None or month is None:
        today = timezone.localdate()
        targets = [add_months(today.year, today.month, -step) for step in range(months)]
    else:
        targets = [(year, month)]
    rows = {}
    missing = set()
    for item in transactions:
        if item.transaction_type != transaction_type:
            continue
        value = sum(
            (_transaction_value(user, item, y, m, missing) or ZERO for y, m in targets),
            ZERO,
        )
        if not value:
            continue
        key, label = _instrument(
            item, income=transaction_type == Transaction.TransactionType.INCOME
        )
        row = rows.setdefault(key, {'key': key, 'label': label, 'total': ZERO})
        row['total'] += value
    overall = sum((row['total'] for row in rows.values()), ZERO)
    ranked = sorted(rows.values(), key=lambda row: row['total'], reverse=True)
    shown = ranked[:TOP_INSTRUMENTS]
    for row in shown:
        row['share'] = round(float(row['total'] / overall) * 100, 1) if overall else 0
    return {
        'total': overall,
        'instruments': shown,
        'shown': len(shown),
        'used': len(ranked),
        'missing_currencies': sorted(missing),
    }


def get_expenses_by_instrument(user, year=None, month=None, months=1):
    return _instrument_breakdown(
        user, Transaction.TransactionType.EXPENSE, year, month, months
    )


def get_income_by_account(user, year=None, month=None, months=1):
    return _instrument_breakdown(
        user, Transaction.TransactionType.INCOME, year, month, months
    )


def _categories_for_instrument(
    user, instrument_key, transaction_type, year, month
):
    totals = {}
    missing = set()
    for item in _transactions(user):
        if item.transaction_type != transaction_type:
            continue
        key, _ = _instrument(
            item, income=transaction_type == Transaction.TransactionType.INCOME
        )
        if key != instrument_key:
            continue
        value = _transaction_value(user, item, year, month, missing)
        if not value:
            continue
        row = totals.setdefault(
            item.category_id,
            {'id': item.category_id, 'name': item.category.name, 'total': ZERO},
        )
        row['total'] += value
    return _category_rows(totals)


def get_expenses_by_category_for_instrument(user, key, year, month):
    return _categories_for_instrument(
        user, key, Transaction.TransactionType.EXPENSE, year, month
    )


def get_income_by_category_for_account(user, key, year, month):
    return _categories_for_instrument(
        user, key, Transaction.TransactionType.INCOME, year, month
    )


def get_account_evolution(user, offset=0):
    today = timezone.localdate()
    anchor_year, anchor_month = add_months(today.year, today.month, offset)
    start_year, start_month = add_months(
        anchor_year, anchor_month, -EVOLUTION_PAST_MONTHS
    )
    transactions = _transactions(user)
    months = []
    missing = set()
    for step in range(EVOLUTION_MONTHS):
        year, month = add_months(start_year, start_month, step)
        totals = _monthly_totals(user, transactions, year, month)
        snapshot = get_ledger_snapshot(user, _month_end(year, month))
        missing.update(totals['missing_currencies'])
        missing.update(snapshot['missing_currencies'])
        months.append(
            {
                'year': year,
                'month': month,
                'date': date(year, month, 1),
                'is_current_month': (year, month) == (anchor_year, anchor_month),
                'is_future': (year, month) > (today.year, today.month),
                **totals,
                'closing_balance': snapshot['total'],
            }
        )
    opening_date = _month_end(*add_months(start_year, start_month, -1))
    opening = get_ledger_snapshot(user, opening_date)
    missing.update(opening['missing_currencies'])
    current = next(row for row in months if row['is_current_month'])
    category_rows, category_missing = _expenses_by_category(
        user, transactions, start_year, start_month, EVOLUTION_MONTHS
    )
    missing.update(category_missing)
    balance_today = get_ledger_snapshot(user, today)
    missing.update(balance_today['missing_currencies'])
    return {
        'months': months,
        'current_month': current,
        'anchor_year': anchor_year,
        'anchor_month': anchor_month,
        'anchor_date': date(anchor_year, anchor_month, 1),
        'is_anchored_today': offset == 0,
        'balance_today': balance_today['total'],
        'opening_balance': opening['total'],
        'closing_balance': months[-1]['closing_balance'],
        'net_change': months[-1]['closing_balance'] - opening['total'],
        'best_month': max(months, key=lambda row: row['balance']),
        'worst_month': min(months, key=lambda row: row['balance']),
        'expenses_by_category': category_rows,
        'missing_currencies': sorted(missing),
    }


def get_card_comparison(user, months):
    transactions = _transactions(user)
    missing = set()
    totals = {}
    values = {}
    for item in transactions:
        if (
            item.transaction_type != Transaction.TransactionType.EXPENSE
            or not item.credit_card_id
        ):
            continue
        label = (
            f'{item.credit_card.account.bank.name} > '
            f'{item.credit_card.account.name} / {item.credit_card.name}'
        )
        key = item.credit_card_id
        row = values.setdefault(key, {'name': label, 'values': [ZERO] * len(months)})
        for index, target in enumerate(months):
            value = _transaction_value(
                user, item, target['year'], target['month'], missing
            )
            if value:
                row['values'][index] += value
                totals[key] = totals.get(key, ZERO) + value
    selected = sorted(totals, key=totals.get, reverse=True)[:TOP_INSTRUMENTS]
    return [values[key] for key in selected], sorted(missing)


def get_expenses_by_recurrence(user, year=None, month=None, months=1):
    transactions = _transactions(user)
    if year is None or month is None:
        today = timezone.localdate()
        targets = [add_months(today.year, today.month, -step) for step in range(months)]
    else:
        targets = [(year, month)]
    buckets = {'installment': ZERO, 'fixed': ZERO, 'one_off': ZERO}
    missing = set()
    for item in transactions:
        if item.transaction_type != Transaction.TransactionType.EXPENSE:
            continue
        value = sum(
            (_transaction_value(user, item, y, m, missing) or ZERO for y, m in targets),
            ZERO,
        )
        if item.is_installment_plan:
            buckets['installment'] += value
        elif item.is_fixed:
            buckets['fixed'] += value
        else:
            buckets['one_off'] += value
    overall = sum(buckets.values(), ZERO)
    order = (
        ('installment', _('Installments')),
        ('fixed', _('Fixed')),
        ('one_off', _('One-off')),
    )
    slices = []
    for key, name in order:
        share = round(float(buckets[key] / overall) * 100, 1) if overall else 0
        slices.append(
            {
                'name': name,
                'tone': key,
                'value': buckets[key],
                'share': share,
                'draw': bool(buckets[key]),
            }
        )
    drawn = [row for row in slices if row['draw']]
    if drawn:
        drawn[-1]['share'] += round(100 - sum(row['share'] for row in drawn), 1)
    return {
        'total': overall,
        'slices': slices,
        'missing_currencies': sorted(missing),
    }
