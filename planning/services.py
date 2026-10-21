# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read local evidence, reserve existing balances and explain planning limits."""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import BankMovement
from banking.services import MissingExchangeRate, account_balances, convert
from categories.models import Category
from investments.services import get_monthly_cash_positions
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalDecision, SignalSettings
from transactions.models import Transaction

ZERO = Decimal('0.00')
CENT = Decimal('0.01')


def _category_map(user):
    return dict(Category.objects.filter(user=user).values_list('pk', 'parent_category_id'))


def _descendants(parents, category_id):
    result = {category_id}
    pending = [category_id]
    children = defaultdict(list)
    for child, parent in parents.items():
        children[parent].append(child)
    while pending:
        for child in children[pending.pop()]:
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


def category_family(user, category_id):
    """Categories which would overlap the selected category's budget."""
    parents = _category_map(user)
    result = _descendants(parents, category_id)
    parent = parents.get(category_id)
    while parent and parent not in result:
        result.add(parent)
        parent = parents.get(parent)
    return result


def validate_budget_category_change(category):
    """Reject a category edit which would invalidate existing expense limits.

    Called from Category.clean with the pending parent/type, before saving.
    Unchanged names and new categories do not need to read the budget table.
    """
    if not category.pk or not category.user_id:
        return
    original = Category.objects.filter(pk=category.pk, user_id=category.user_id).values('parent_category_id', 'transaction_type').first()
    if original is None or (original['parent_category_id'] == category.parent_category_id and original['transaction_type'] == category.transaction_type):
        return
    budgets = list(CategoryBudget.objects.filter(user_id=category.user_id).values('category_id', 'month', 'currency'))
    if category.transaction_type == 'INCOME' and any(row['category_id'] == category.pk for row in budgets):
        raise ValidationError({'transaction_type': _('This category has expense budgets. Remove those limits before classifying it as income.')})
    if original['parent_category_id'] == category.parent_category_id:
        return
    parents = _category_map(category.user)
    parents[category.pk] = category.parent_category_id
    groups = defaultdict(list)
    for budget in budgets:
        groups[(budget['month'], budget['currency'])].append(budget['category_id'])
    for ids in groups.values():
        for index, selected in enumerate(ids):
            descendants = _descendants(parents, selected)
            if any(other in descendants for other in ids[index + 1:]) or any(selected in _descendants(parents, other) for other in ids[index + 1:]):
                raise ValidationError({'parent_category': _('This move would overlap existing category budgets in the same month and currency. Review those limits first.')})


def _transactions(user):
    rows = Transaction.objects.filter(user=user).select_related(
        'category', 'bank_account__bank', 'debit_card__account__bank', 'credit_card__account__bank',
    )
    if any(field.name == 'splits' for field in Transaction._meta.get_fields()):
        rows = rows.prefetch_related('splits__category')
    return rows


def _allocations_for_month(operation, year, month):
    amount = operation.amount_for_month(year, month)
    if hasattr(operation, 'category_allocations_for_month'):
        return operation.category_allocations_for_month(year, month)
    if hasattr(operation, 'category_allocations_for'):
        return operation.category_allocations_for(amount)
    return [(operation.category, amount)] if amount else []


def _occurrence_date(operation, month):
    # Credit expenses follow invoice reference months, as on the dashboard.
    # A known instalment is forecast in its invoice month, never realised
    # early merely because the original purchase was already made.
    if operation.is_installment_plan or not operation.is_fixed:
        return operation.date
    offset = (month.year - operation.date.year) * 12 + month.month - operation.date.month
    if operation.is_credit_card:
        offset -= operation.billing_offset
    source_month = operation.date.month - 1 + offset
    year = operation.date.year + source_month // 12
    number = source_month % 12 + 1
    return date(year, number, min(operation.date.day, calendar.monthrange(year, number)[1]))


def budget_progress(user, month, *, as_of=None):
    """Categorised expenses in invoice/reference months, with explicit FX gaps."""
    as_of = as_of or timezone.localdate()
    month = month.replace(day=1)
    month_end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    rate_date = min(month_end, as_of)
    parents = _category_map(user)
    budgets = list(CategoryBudget.objects.filter(user=user, month=month).select_related('category'))
    if not budgets:
        return []
    rows = [{
        'budget': budget, 'categories': _descendants(parents, budget.category_id),
        'actual': ZERO, 'forecast': ZERO, 'missing_currencies': set(), 'rate_date': rate_date,
    } for budget in budgets]
    rates = {}
    from banking.credit_reporting import invoice_credit_occurrences
    operations = list(_transactions(user).filter(transaction_type=Transaction.TransactionType.EXPENSE))
    operations.extend(invoice_credit_occurrences(user))
    for operation in operations:
        portions = _allocations_for_month(operation, month.year, month.month)
        if not portions:
            continue
        actual = month <= as_of.replace(day=1) and _occurrence_date(operation, month) <= as_of
        for category, amount in portions:
            if not amount:
                continue
            for row in rows:
                if category.pk not in row['categories']:
                    continue
                pair = (operation.native_currency, row['budget'].currency)
                if pair not in rates:
                    try:
                        rates[pair] = convert(user, Decimal('1'), *pair, as_of=rate_date)
                    except MissingExchangeRate:
                        rates[pair] = None
                if rates[pair] is None:
                    row['missing_currencies'].add(operation.native_currency)
                    continue
                value = amount * rates[pair]
                row['forecast'] += value
                if actual:
                    row['actual'] += value
    for row in rows:
        row['actual'] = row['actual'].quantize(CENT)
        row['forecast'] = row['forecast'].quantize(CENT)
        row['complete'] = not row['missing_currencies']
        row['missing_currencies'] = sorted(row['missing_currencies'])
        row['remaining'] = row['budget'].amount - row['actual']
        row['actual_percent'] = min(100, max(0, int(row['actual'] / row['budget'].amount * 100)))
        row['over_budget'] = row['actual'] > row['budget'].amount
        row['forecast_over_budget'] = row['forecast'] > row['budget'].amount
    return rows


@transaction.atomic
def copy_previous_budgets(user, month):
    """Add compatible previous limits without overwriting existing budgets."""
    get_user_model().objects.select_for_update().get(pk=user.pk)
    previous = (month.replace(day=1) - timedelta(days=1)).replace(day=1)
    copied = skipped = 0
    for source in CategoryBudget.objects.filter(user=user, month=previous).select_related('category'):
        budget = CategoryBudget(user=user, category=source.category, month=month.replace(day=1), currency=source.currency, amount=source.amount)
        try:
            budget.full_clean()
        except ValidationError:
            skipped += 1
            continue
        budget.save()
        copied += 1
    return copied, skipped


@transaction.atomic
def save_budget(budget):
    get_user_model().objects.select_for_update().get(pk=budget.user_id)
    budget.full_clean()
    budget.save()
    return budget


def reserved_by_source(user, as_of=None):
    """Declared native reserves, keyed by account pk or (product pk, asset pk).

    Allocations are named portions of an existing reserve, not another debit:
    account callers use max(legacy reserve, these totals). Past reads exclude
    allocations created later, but edits are current records, not historical
    reserve snapshots. Consumers must cap backing at real positive balances.
    """
    rows = GoalAllocation.objects.filter(user=user, goal__user=user, goal__is_archived=False)
    if as_of is not None:
        rows = rows.filter(created_at__date__lte=as_of)
    accounts = dict(rows.filter(bank_account__isnull=False).values('bank_account_id').annotate(total=Sum('amount')).values_list('bank_account_id', 'total'))
    pots = {(row['product_id'], row['asset_id']): row['total'] for row in rows.filter(product__isnull=False).values('product_id', 'asset_id').annotate(total=Sum('amount'))}
    return {'accounts': accounts, 'cash_pots': pots}


def goal_sources(user, as_of=None):
    """Known owned cash sources; this function never opens or creates a source."""
    as_of = as_of or timezone.localdate()
    result = {}
    for row in account_balances(user, as_of=as_of):
        account = row['account']
        key = f'account:{account.pk}'
        result[key] = {'key': key, 'account': account, 'product': None, 'asset': None,
                       'label': str(account), 'currency': account.currency, 'balance': row['balance'],
                       'url': reverse('banking:detail', args=[account.bank_id]) + f'#account-row-{account.pk}'}
    for row in get_monthly_cash_positions(user, as_of=as_of):
        product, asset = row['product'], row['asset']
        key = f'pot:{product.pk}:{asset.pk}'
        result[key] = {'key': key, 'account': None, 'product': product, 'asset': asset,
                       'label': f'{product} · {asset}', 'currency': asset.currency, 'balance': row['balance'],
                       'url': reverse('investments:position_detail', args=[product.pk, asset.pk])}
    return result


def _active_allocations(user, as_of=None):
    rows = GoalAllocation.objects.filter(user=user, goal__user=user, goal__is_archived=False).select_related('goal', 'bank_account__bank', 'product__bank', 'asset')
    if as_of is not None:
        rows = rows.filter(created_at__date__lte=as_of)
    return list(rows)


def validate_allocation(allocation, *, sources=None, allocations=None):
    if allocation.goal.is_archived:
        raise ValidationError(_('Archived goals cannot reserve a balance.'))
    sources = sources if sources is not None else goal_sources(allocation.user)
    source = sources.get(allocation.source_key)
    if source is None:
        raise ValidationError(_('This cash source is unavailable. Select an existing bank account or monetary cash pot.'))
    allocations = allocations if allocations is not None else _active_allocations(allocation.user)
    others = sum((row.amount for row in allocations if row.source_key == allocation.source_key and row.pk != allocation.pk), ZERO)
    if allocation.amount + others > max(ZERO, source['balance']):
        raise ValidationError(_('The reservation exceeds the positive balance left after other active goals. Available: %(currency)s %(amount)s.') % {
            'currency': source['currency'], 'amount': max(ZERO, source['balance'] - others).quantize(CENT),
        })


@transaction.atomic
def save_allocation(allocation):
    # Serialize reservations per owner so different goals cannot claim the
    # same last portion of a balance in concurrent submissions.
    get_user_model().objects.select_for_update().get(pk=allocation.user_id)
    allocation.full_clean()
    validate_allocation(allocation)
    allocation.save()
    return allocation


@transaction.atomic
def create_goal(goal, allocation=None):
    """Create a target and its optional real reservation as one operation."""
    get_user_model().objects.select_for_update().get(pk=goal.user_id)
    goal.full_clean()
    goal.save()
    if allocation is not None:
        allocation.goal = goal
        save_allocation(allocation)
    return goal


@transaction.atomic
def set_goal_archived(goal, archived):
    get_user_model().objects.select_for_update().get(pk=goal.user_id)
    if not archived and goal.is_archived:
        sources = goal_sources(goal.user)
        active = _active_allocations(goal.user)
        own = list(goal.allocations.select_related('goal', 'bank_account', 'product', 'asset'))
        goal.is_archived = False
        for allocation in own:
            allocation.goal = goal
            validate_allocation(allocation, sources=sources, allocations=active + own)
    goal.is_archived = archived
    goal.save(update_fields=['is_archived', 'updated_at'])


def goal_progress(user, *, as_of=None, include_archived=False):
    as_of = as_of or timezone.localdate()
    sources = goal_sources(user, as_of)
    active = _active_allocations(user, as_of)
    by_source = defaultdict(list)
    for allocation in active:
        by_source[allocation.source_key].append(allocation)
    backing = {}
    for key, allocations in by_source.items():
        declared = sum((item.amount for item in allocations), ZERO)
        available = min(declared, max(ZERO, sources.get(key, {}).get('balance', ZERO)))
        # Cumulative rounding apportions cents without over-claiming the source.
        cumulative = allocated = ZERO
        for item in sorted(allocations, key=lambda item: item.pk):
            cumulative += item.amount
            upto = (available * cumulative / declared).quantize(CENT)
            backing[item.pk] = upto - allocated
            allocated = upto
    goals = FinancialGoal.objects.filter(user=user).prefetch_related('allocations__bank_account__bank', 'allocations__product__bank', 'allocations__asset')
    if not include_archived:
        goals = goals.filter(is_archived=False)
    result = []
    rates = {}
    for goal in goals:
        row = {'goal': goal, 'progress': ZERO, 'declared': ZERO, 'allocations': [], 'missing_currencies': set(), 'has_shortfall': False}
        for allocation in goal.allocations.all():
            backed = backing.get(allocation.pk, ZERO)
            detail = {'allocation': allocation, 'backed': backed, 'shortfall': allocation.amount - backed,
                      'source': sources.get(allocation.source_key)}
            row['allocations'].append(detail)
            row['has_shortfall'] |= detail['shortfall'] > ZERO and not goal.is_archived
            pair = (allocation.source_currency, goal.currency)
            if pair not in rates:
                try:
                    rates[pair] = convert(user, Decimal('1'), *pair, as_of=as_of)
                except MissingExchangeRate:
                    rates[pair] = None
            if rates[pair] is None:
                row['missing_currencies'].add(pair[0])
            else:
                row['declared'] += allocation.amount * rates[pair]
                row['progress'] += backed * rates[pair]
        row['progress'] = row['progress'].quantize(CENT)
        row['declared'] = row['declared'].quantize(CENT)
        row['complete'] = not row['missing_currencies']
        row['missing_currencies'] = sorted(row['missing_currencies'])
        row['percent'] = min(100, max(0, int(row['progress'] / goal.target_amount * 100)))
        row['remaining'] = max(ZERO, goal.target_amount - row['progress'])
        result.append(row)
    return result


def signal_settings(user):
    # Viewing signals must not write defaults or change the financial ledger.
    return SignalSettings.objects.filter(user=user).first() or SignalSettings(user=user)


def _signal(kind, evidence, title, explanation, sources, **extra):
    digest = sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()
    return {'key': f'{kind}:{digest}', 'kind': kind, 'title': title, 'explanation': explanation,
            'sources': sources, 'decision': None, **extra}


def _transaction_source(operation):
    # Presentation metadata stays outside the evidence fingerprint. Editors
    # receive the consultation origin; dates follow the reader's preference.
    return {'url': reverse('transactions:update', args=[operation.pk]),
            'label': f'{operation.title} · {operation.date.isoformat()}',
            'title': operation.title, 'date': operation.date, 'editable': True}


def _fingerprint(operation):
    return (operation.pk, operation.amount, operation.date, operation.updated_at)


def local_signals(user, *, as_of=None):
    """Deterministic suggestions, based only on recorded local evidence."""
    as_of = as_of or timezone.localdate()
    settings = signal_settings(user)
    signals = []
    notices = []
    if settings.duplicates_enabled or settings.subscriptionincrease_enabled:
        candidates = list(_transactions(user).filter(
            transaction_type='EXPENSE', date__gte=as_of - timedelta(days=90), date__lte=as_of,
            is_fixed=False, reward_redemption__isnull=True,
        ).order_by('-date', '-pk')[:1001])
        if len(candidates) > 1000:
            notices.append(_('Transaction checks use the latest 1,000 expenses in the last 90 days.'))
        candidates = candidates[:1000]
        grouped = defaultdict(list)
        for operation in candidates:
            payment = (operation.payment_channel, operation.bank_account_id, operation.debit_card_id, operation.credit_card_id)
            grouped[(' '.join(operation.title.casefold().split()), operation.native_currency, payment)].append(operation)
        for group in grouped.values():
            for index, latest in enumerate(group):
                if settings.duplicates_enabled:
                    for earlier in group[index + 1:]:
                        days = (latest.date - earlier.date).days
                        if days > settings.duplicate_days:
                            break
                        if latest.amount == earlier.amount and len(signals) < 100:
                            signals.append(_signal('duplicates', [_fingerprint(earlier), _fingerprint(latest), settings.duplicate_days],
                                _('Possible duplicate transaction'),
                                _('Same description, payment instrument, currency and amount within %(days)s days. Review both records before changing anything.') % {'days': settings.duplicate_days},
                                [_transaction_source(earlier), _transaction_source(latest)]))
                            break
                if settings.subscriptionincrease_enabled and index == 0:
                    earlier = next((row for row in group[1:] if 20 <= (latest.date - row.date).days <= 45), None)
                    if earlier and latest.amount > earlier.amount:
                        increase = (latest.amount / earlier.amount - 1) * 100
                        if increase >= settings.subscription_increase_percent and len(signals) < 100:
                            signals.append(_signal('subscriptionincrease', [_fingerprint(earlier), _fingerprint(latest), settings.subscription_increase_percent],
                                _('Possible subscription increase'),
                                _('Two similar expenses, 20–45 days apart, increased by %(percent)s%% (%(currency)s %(before)s → %(after)s). This pattern does not prove a subscription; fixed templates have no price history.') % {
                                    'percent': increase.quantize(CENT), 'currency': latest.native_currency, 'before': earlier.amount, 'after': latest.amount,
                                }, [_transaction_source(earlier), _transaction_source(latest)]))
        if len(signals) >= 100:
            notices.append(_('Transaction checks show up to 100 suggestions. Review these records before requesting more.'))
    if settings.budgetoverspend_enabled:
        for row in budget_progress(user, as_of.replace(day=1), as_of=as_of):
            if row['over_budget'] or row['forecast_over_budget']:
                budget = row['budget']
                label = _('Recorded spending exceeds budget') if row['over_budget'] else _('Forecast spending exceeds budget')
                signals.append(_signal('budgetoverspend', [budget.pk, budget.updated_at, row['actual'], row['forecast'], row['missing_currencies']], label,
                    _('%(category)s: recorded %(currency)s %(actual)s; month forecast %(forecast)s; limit %(limit)s. The forecast includes only known transactions in their reference month.') % {
                        'category': budget.category, 'currency': budget.currency, 'actual': row['actual'], 'forecast': row['forecast'], 'limit': budget.amount,
                    }, [{'url': reverse('planning:budgets') + f'?month={budget.month:%Y-%m}', 'label': str(budget.category)}], partial=not row['complete']))
    if settings.futurecashshortage_enabled:
        from banking.settlements import manual_invoice_obligations
        end = as_of + timedelta(days=settings.forecast_days)
        balances = {row['account'].pk: row for row in account_balances(user, as_of)}
        movements = defaultdict(list)
        for movement in BankMovement.objects.filter(user=user, account__user=user, effective_date__gt=as_of, effective_date__lte=end).order_by('effective_date', 'pk'):
            movements[movement.account_id].append(movement)
        obligations = defaultdict(list)
        for invoice in manual_invoice_obligations(user, as_of):
            # When inspecting a past cutoff, later real payments already
            # appear among future cash movements, possibly on another account.
            # Forecast only the still unconfirmed remainder on the card account.
            later_paid = sum((payment.amount for payment in invoice.payments.all()
                              if as_of < payment.date <= timezone.localdate()), ZERO)
            invoice.forecast_remainder = max(ZERO, invoice.remaining_amount_at_cutoff - later_paid)
            if invoice.forecast_remainder and max(as_of, invoice.due_date) <= end:
                obligations[invoice.card.account_id].append(invoice)
        for account_id, row in balances.items():
            account, balance = row['account'], row['balance']
            by_day = defaultdict(lambda: ZERO)
            evidence = []
            for movement in movements[account_id]:
                by_day[movement.effective_date] += movement.amount if movement.direction == 'CREDIT' else -movement.amount
                evidence.append((movement.pk, movement.updated_at, movement.amount, movement.direction, movement.effective_date))
            for invoice in obligations[account_id]:
                # A confirmed-mode obligation has no fabricated cash debit.
                # Include its unpaid remainder once, on its forecast due date.
                day = max(as_of, invoice.due_date)
                by_day[day] -= invoice.forecast_remainder
                evidence.append(('invoice', invoice.pk, day, invoice.forecast_remainder))
            shortage_date = as_of if balance < ZERO else None
            shortage = balance
            for day in sorted(by_day):
                balance += by_day[day]
                if balance < ZERO and shortage_date is None:
                    shortage_date, shortage = day, balance
            if shortage_date:
                signals.append(_signal('futurecashshortage', [account_id, row['balance'], evidence, as_of, settings.forecast_days],
                    _('Projected bank cash shortage'),
                    _('%(account)s reaches %(currency)s %(balance)s on %(date)s using its current balance, recorded bank movements and unpaid confirmed-mode invoices through %(end)s. Unrecorded income, future cash-pot withdrawals and reserved goals are not assumed.') % {
                        'account': account, 'currency': account.currency, 'balance': shortage.quantize(CENT), 'date': shortage_date, 'end': end,
                    }, [{'url': reverse('banking:detail', args=[account.bank_id]), 'label': str(account)}] + [
                        {'url': reverse('banking:invoice_detail', args=[invoice.pk]), 'label': str(invoice)}
                        for invoice in obligations[account_id]
                    ]))
    decisions = {row.key: row for row in SignalDecision.objects.filter(user=user, key__in=[signal['key'] for signal in signals])}
    for signal in signals:
        signal['decision'] = decisions.get(signal['key'])
    return {'signals': signals, 'notices': notices, 'settings': settings, 'as_of': as_of}
