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
DASHBOARD_PREVIEW_LIMIT = 5
FLOW_KEYS = ('income', 'expenses', 'investments', 'withdrawals', 'balance')


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


def _investment_cash_flows(user, window, cutoff=None):
    wanted = set(window)
    investments = ZERO
    withdrawals = ZERO
    missing = set()
    base_currency = UserPreference.for_user(user).base_currency
    operations = Investment.objects.filter(
        user=user,
        kind__in=(Investment.Kind.DEPOSIT, Investment.Kind.WITHDRAWAL),
    ).select_related('asset', 'source_account', 'destination_account')
    for operation in operations:
        if (operation.date.year, operation.date.month) not in wanted:
            continue
        if cutoff is not None and operation.date > cutoff:
            continue
        if operation.kind == Investment.Kind.DEPOSIT:
            value = _investment_value(user, operation, base_currency, missing)
            if value is not None:
                investments += value
            continue
        if not operation.cash_amount or not operation.destination_account_id:
            continue
        value = _convert_or_missing(
            user,
            operation.cash_amount,
            operation.destination_account.currency,
            operation.date,
            missing,
        )
        if value is not None:
            withdrawals += value
    return investments, withdrawals, sorted(missing)


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


def _transaction_occurrence_date(transaction, year, month):
    """Return the modeled economic date for an amount assigned to a month."""
    if not transaction.amount_for_month(year, month):
        return None
    if transaction.is_installment_plan:
        # Later installments remain known obligations from the original purchase.
        return transaction.date
    if not transaction.is_fixed:
        return transaction.date
    occurrence_year, occurrence_month = add_months(
        year, month, -transaction.billing_offset
    )
    return date(
        occurrence_year,
        occurrence_month,
        min(
            transaction.date.day,
            monthrange(occurrence_year, occurrence_month)[1],
        ),
    )


def _empty_flow():
    return {
        'income': ZERO,
        'expenses': ZERO,
        'investments': ZERO,
        'withdrawals': ZERO,
        'balance': ZERO,
        'missing_currencies': [],
    }


def _remaining_flow(full_month, through_cutoff):
    remaining = {
        key: full_month[key] - through_cutoff[key]
        for key in FLOW_KEYS
    }
    remaining['missing_currencies'] = full_month['missing_currencies']
    return remaining


def _monthly_totals(user, transactions, year, month, cutoff=None):
    income = ZERO
    expenses = ZERO
    missing = set()
    for item in transactions:
        occurrence = _transaction_occurrence_date(item, year, month)
        if occurrence is None or (cutoff is not None and occurrence > cutoff):
            continue
        value = _transaction_value(user, item, year, month, missing)
        if value is None:
            continue
        if item.transaction_type == Transaction.TransactionType.INCOME:
            income += value
        elif item.transaction_type == Transaction.TransactionType.EXPENSE:
            expenses += value
    banking_expenses, banking_missing = _banking_expenses_for_month(
        user, year, month, cutoff=cutoff
    )
    expenses += banking_expenses
    missing.update(banking_missing)
    investments, withdrawals, investment_missing = _investment_cash_flows(
        user, [(year, month)], cutoff=cutoff
    )
    missing.update(investment_missing)
    return {
        'income': income,
        'expenses': expenses,
        'investments': investments,
        'withdrawals': withdrawals,
        'balance': income + withdrawals - expenses - investments,
        'missing_currencies': sorted(missing),
    }


def _banking_expenses_for_month(user, year, month, cutoff=None):
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
        if cutoff is not None and entry.date > cutoff:
            continue
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
        if cutoff is not None and redemption.date > cutoff:
            continue
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
    current_previous_year, current_previous_month = add_months(
        today.year, today.month, -1
    )
    current_period_start = get_ledger_snapshot(
        user, _month_end(current_previous_year, current_previous_month)
    )
    is_current_month = (year, month) == (today.year, today.month)
    is_future_month = (year, month) > (today.year, today.month)

    if is_future_month:
        period_kind = 'future'
        cutoff = None
        through_cutoff = _empty_flow()
    elif is_current_month:
        period_kind = 'current'
        cutoff = today
        through_cutoff = _monthly_totals(
            user, transactions, year, month, cutoff=cutoff
        )
    else:
        period_kind = 'past'
        cutoff = _month_end(year, month)
        through_cutoff = selected
    remaining = _remaining_flow(selected, through_cutoff)

    category_cutoff = cutoff if period_kind != 'future' else None
    expense_categories, category_missing = _expenses_by_category(
        user,
        transactions,
        year,
        month,
        1,
        cutoff=category_cutoff,
    )

    selected_offset = (year - today.year) * 12 + month - today.month
    path_months = max(0, selected_offset) + OUTLOOK_MONTHS
    projected_path = {}
    rolling_projected = current_period_start['total']
    for offset in range(path_months + 1):
        path_year, path_month = add_months(today.year, today.month, offset)
        path_totals = _monthly_totals(user, transactions, path_year, path_month)
        rolling_projected += path_totals['balance']
        projected_path[(path_year, path_month)] = rolling_projected

    previous_year, previous_month = add_months(year, month, -1)
    if selected_offset >= 0:
        period_start_total = (
            current_period_start['total']
            if selected_offset == 0
            else projected_path[(previous_year, previous_month)]
        )
        projected_total = projected_path[(year, month)]
    else:
        period_start = get_ledger_snapshot(
            user, _month_end(previous_year, previous_month)
        )
        period_close = get_ledger_snapshot(user, _month_end(year, month))
        period_start_total = period_start['total']
        projected_total = period_close['total']

    outlook = []
    missing = set(current['missing_currencies'])
    missing.update(current_period_start['missing_currencies'])
    if selected_offset < 0:
        missing.update(period_start['missing_currencies'])
        missing.update(period_close['missing_currencies'])
    missing.update(category_missing)
    for offset in range(OUTLOOK_MONTHS):
        row_year, row_month = add_months(year, month, offset)
        totals = _monthly_totals(user, transactions, row_year, row_month)
        missing.update(totals['missing_currencies'])
        row_offset = (row_year - today.year) * 12 + row_month - today.month
        if row_offset >= 0:
            row_projected = projected_path[(row_year, row_month)]
        else:
            snapshot = get_ledger_snapshot(user, _month_end(row_year, row_month))
            missing.update(snapshot['missing_currencies'])
            row_projected = snapshot['total']
        outlook.append(
            {
                'year': row_year,
                'month': row_month,
                'date': date(row_year, row_month, 1),
                'is_current_month': (row_year, row_month) == (today.year, today.month),
                'is_selected_month': offset == 0,
                **totals,
                'projected_balance': row_projected,
            }
        )

    invoices = list(
        CardInvoice.objects.filter(user=user, status=CardInvoice.Status.SCHEDULED)
        .select_related('card__account__bank')
        .order_by('due_date', 'card__name')
    )
    account_preview = current['accounts'][:DASHBOARD_PREVIEW_LIMIT]
    invoice_preview = invoices[:DASHBOARD_PREVIEW_LIMIT]
    cash_change_through_cutoff = (
        ZERO
        if is_future_month
        else (
            current['total'] - period_start_total
            if is_current_month
            else projected_total - period_start_total
        )
    )
    return {
        'selected_year': year,
        'selected_month': month,
        'selected_month_date': date(year, month, 1),
        'period_kind': period_kind,
        'period_cutoff': cutoff,
        'is_current_month': is_current_month,
        'is_future_month': is_future_month,
        'current_balance': current['total'],
        'period_opening_balance': period_start_total,
        'period_closing_balance': projected_total,
        'cash_change_through_cutoff': cash_change_through_cutoff,
        'balance_change_full_month': projected_total - period_start_total,
        'cash_change_full_month': projected_total - period_start_total,
        'performance': {
            'through_cutoff': through_cutoff,
            'remaining': remaining,
            'full_month': selected,
        },
        'projected_balance': projected_total,
        'account_balances': current['accounts'],
        'account_balances_preview': account_preview,
        'account_balances_hidden': max(
            0, len(current['accounts']) - len(account_preview)
        ),
        'open_invoices': invoices,
        'open_invoices_preview': invoice_preview,
        'open_invoices_hidden': max(0, len(invoices) - len(invoice_preview)),
        'next_invoice': invoices[0] if invoices else None,
        'income_month': selected['income'],
        'expense_month': selected['expenses'],
        'investment_month': selected['investments'],
        'withdrawal_month': selected['withdrawals'],
        # This card must reconcile with the two balance cards. `selected`
        # remains the transaction/reporting flow, where card purchases belong
        # to their statement month; cash closing follows invoice due dates.
        'balance_month': projected_total - period_start_total,
        'expense_categories': expense_categories,
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


def _expenses_by_category(user, transactions, year, month, months, cutoff=None):
    targets = _window(year, month, months)
    totals = {}
    missing = set()
    for item in transactions:
        if item.transaction_type != Transaction.TransactionType.EXPENSE:
            continue
        value = ZERO
        for target_year, target_month in targets:
            occurrence = _transaction_occurrence_date(
                item, target_year, target_month
            )
            if occurrence is None or (
                cutoff is not None and occurrence > cutoff
            ):
                continue
            value += (
                _transaction_value(
                    user, item, target_year, target_month, missing
                )
                or ZERO
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


def _instrument_display(item, income=False):
    """Return compact labels for chart axes while keeping the stable full label."""
    if income:
        account = item.bank_account
        return account.name, account.bank.name
    if item.credit_card_id:
        return item.credit_card.name, item.credit_card.account.bank.name
    if item.debit_card_id:
        return item.debit_card.name, item.debit_card.account.bank.name
    account = item.bank_account
    return account.name, account.bank.name


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


def get_instrument_activity(user, year=None, month=None, months=1):
    """Return the largest accounts/cards ranked by all money moved."""
    transactions = _transactions(user)
    if year is None or month is None:
        today = timezone.localdate()
        targets = [add_months(today.year, today.month, -step) for step in range(months)]
    else:
        targets = [(year, month)]

    rows = {}
    missing = set()
    expense_total = ZERO
    income_total = ZERO
    for item in transactions:
        if item.transaction_type not in (
            Transaction.TransactionType.EXPENSE,
            Transaction.TransactionType.INCOME,
        ):
            continue
        value = sum(
            (_transaction_value(user, item, y, m, missing) or ZERO for y, m in targets),
            ZERO,
        )
        if not value:
            continue
        is_income = item.transaction_type == Transaction.TransactionType.INCOME
        key, label = _instrument(item, income=is_income)
        short_label, bank_label = _instrument_display(item, income=is_income)
        row = rows.setdefault(
            key,
            {
                'key': key,
                'label': label,
                'short_label': short_label,
                'bank_label': bank_label,
                'expense_total': ZERO,
                'income_total': ZERO,
            },
        )
        if is_income:
            row['income_total'] += value
            income_total += value
        else:
            row['expense_total'] += value
            expense_total += value

    ranked = sorted(
        rows.values(),
        key=lambda row: row['expense_total'] + row['income_total'],
        reverse=True,
    )
    shown = ranked[:TOP_INSTRUMENTS]
    for row in shown:
        row['total_moved'] = row['expense_total'] + row['income_total']
    bank_totals = {}
    for row in shown:
        bank_totals[row['bank_label']] = (
            bank_totals.get(row['bank_label'], ZERO) + row['total_moved']
        )
    shown.sort(
        key=lambda row: (
            -bank_totals[row['bank_label']],
            row['bank_label'].casefold(),
            -row['total_moved'],
            row['short_label'].casefold(),
        )
    )
    return {
        'instruments': shown,
        'expense_total': expense_total,
        'income_total': income_total,
        'shown': len(shown),
        'used': len(ranked),
        'missing_currencies': sorted(missing),
    }


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
        correction = round(100 - sum(row['share'] for row in drawn), 1)
        drawn[-1]['share'] = round(drawn[-1]['share'] + correction, 1)
    return {
        'total': overall,
        'slices': slices,
        'missing_currencies': sorted(missing),
    }
