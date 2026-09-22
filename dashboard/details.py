# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read-only composition of the exact financial window represented by a chart."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

from accounts.models import UserPreference
from banking.services import convert, MissingExchangeRate
from categories.models import Category
from dashboard.services import (_transactions, _transaction_value, _transaction_occurrence_date,
    _month_end, add_months, _instrument, _banking_expenses_for_month, get_ledger_snapshot)
from investments.models import Investment, Asset, InvestmentProduct
from investments.services import historical_value_in_base, opening_unit_value


def composition(user, query):
    period = query.get('period', 'ALL')
    if period == 'ALL':
        today = timezone.localdate()
        targets = [add_months(today.year, today.month, -step) for step in range(12)]
    else:
        year, month = map(int, period.split('-'))
        targets = [(year, month)]
    last = _month_end(*max(targets))
    missing = set()
    totals = defaultdict(lambda: Decimal('0'))
    base = UserPreference.for_user(user).base_currency
    scope, series = query['scope'], query['series']
    title = _('Categories and subcategories')
    if scope == 'ledger':
        snapshot = get_ledger_snapshot(user, last)
        title = _('Balances by bank and account')
        missing.update(snapshot['missing_currencies'])
        for row in snapshot['accounts']:
            if row['converted_balance'] is not None:
                totals[row['label']] += row['converted_balance']
    elif scope in ('portfolio', 'portfolio-flow') or series in ('investments', 'withdrawals'):
        title = _('Products and assets')
        operations = Investment.objects.filter(user=user).select_related('asset', 'product__bank', 'source_account', 'destination_account')
        if scope == 'cashflow':
            operations = operations.filter(product__purpose=InvestmentProduct.Purpose.INVESTMENT)
        if query.get('purpose'):
            operations = operations.filter(product__purpose=query['purpose'])
        if scope == 'portfolio':
            assets = Asset.objects.filter(user=user).select_related('opening_product__bank')
            if query.get('purpose'):
                assets = assets.filter(opening_product__purpose=query['purpose'])
            for asset in assets:
                value = asset.opening_balance + opening_unit_value(asset)
                if not value or not asset.opening_product_id:
                    continue
                try:
                    # Same opening FX date used by the plotted timeseries.
                    value = convert(user, value, asset.currency, base, as_of=date.fromisoformat(query['opening_date']))
                    totals[f'{asset.opening_product.bank.name} > {asset.opening_product.name} > {asset.name}'] += value
                except MissingExchangeRate:
                    missing.add(asset.currency)
        for operation in operations:
            if scope == 'portfolio':
                if operation.date > last:
                    continue
            elif (operation.date.year, operation.date.month) not in targets:
                continue
            if scope != 'portfolio':
                expected = {'deposits': 'DEPOSIT', 'investments': 'DEPOSIT', 'withdrawals': 'WITHDRAWAL', 'yields': 'YIELD'}[series]
                if operation.kind != expected:
                    continue
            if scope in ('portfolio', 'portfolio-flow'):
                value = historical_value_in_base(user, operation, base)
                if scope == 'portfolio' and operation.kind == 'WITHDRAWAL' and value is not None:
                    value = -value
            else:
                account = operation.source_account if series == 'investments' else operation.destination_account
                if not account or not operation.cash_amount:
                    continue
                try:
                    value = convert(user, operation.cash_amount, account.currency, base, as_of=operation.date)
                except MissingExchangeRate:
                    value = None
            if value is None:
                missing.add(operation.currency)
            else:
                totals[f'{operation.product.bank.name} > {operation.product.name} > {operation.asset.name}'] += value
    else:
        categories = {item.pk: item for item in Category.objects.filter(user=user)}
        def path(category_id):
            names, visited = [], set()
            while category_id in categories and category_id not in visited:
                visited.add(category_id)
                category = categories[category_id]
                names.append(category.name)
                category_id = category.parent_category_id
            return ' > '.join(reversed(names))
        for item in _transactions(user):
            income = series == 'income'
            if item.transaction_type != ('INCOME' if income else 'EXPENSE'):
                continue
            if query.get('instrument') and _instrument(item, income=income)[0] != query['instrument']:
                continue
            if query.get('category') and item.category_id != query['category']:
                continue
            recurrence = 'installment' if item.is_installment_plan else 'fixed' if item.is_fixed else 'one_off'
            if query.get('recurrence') and recurrence != query['recurrence']:
                continue
            for year, month in targets:
                if query.get('cutoff'):
                    occurrence = _transaction_occurrence_date(item, year, month)
                    if occurrence is None or occurrence > date.fromisoformat(query['cutoff']):
                        continue
                value = _transaction_value(user, item, year, month, missing)
                if value is not None:
                    totals[path(item.category_id)] += value
        if scope == 'cashflow' and series == 'expenses':
            for year, month in targets:
                extra, absent = _banking_expenses_for_month(user, year, month)
                totals[str(_('Bank costs'))] += extra
                missing.update(absent)
    return {'title': title, 'rows': [{'label': label, 'cents': str(int(value.quantize(Decimal('.01')) * 100))}
        for label, value in sorted(totals.items()) if value], 'missing': sorted(missing), 'currency': base}


@login_required
@require_GET
@never_cache
def chart_details(request):
    try:
        query = signing.loads(request.GET.get('token', ''), salt='chart-details', max_age=86400)
        if query['user'] != request.user.pk:
            return JsonResponse({'error': 'not_found'}, status=404)
        return JsonResponse(composition(request.user, query))
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'invalid_scope'}, status=400)
