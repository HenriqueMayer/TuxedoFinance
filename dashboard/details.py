# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read-only composition of the exact financial window represented by a chart."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

from accounts.models import UserPreference
from banking.models import LoyaltyEntry
from banking.services import convert, MissingExchangeRate
from categories.models import Category
from dashboard.services import (_transactions, _transaction_value, _transaction_occurrence_date,
    _month_end, add_months, _instrument, _banking_expenses_for_month, get_ledger_snapshot)
from investments.models import Investment, Asset, InvestmentProduct
from investments.services import historical_value_in_base, opening_unit_value


def composition(user, query):
    period = query.get('period', 'ALL')
    if query.get('periods'):
        # Signed explicit months keep composition aligned with a shifted chart,
        # including future periods; do not fall back to today's trailing year.
        targets = [tuple(map(int, value.split('-'))) for value in query['periods']]
    elif period == 'ALL':
        today = timezone.localdate()
        targets = [add_months(today.year, today.month, -step) for step in range(12)]
    else:
        year, month = map(int, period.split('-'))
        targets = [(year, month)]
    last = _month_end(*max(targets))
    missing = set()
    totals = defaultdict(lambda: Decimal('0'))
    sources = defaultdict(dict)
    preference = UserPreference.for_user(user)
    base = preference.base_currency
    date_format = '%m/%d/%Y' if preference.date_format == 'MDY' else '%d/%m/%Y'

    def dated(label, event_date):
        return f'{label} · {event_date.strftime(date_format)}'

    def add(label, value, key, name, url, action):
        if not value:
            return
        totals[label] += value
        # Recurring/installment events can contribute in several months, but
        # link once to their original operation with the full scoped amount.
        source = sources[label].setdefault(key, {
            'label': name, 'url': url, 'action': str(action), 'value': Decimal('0'),
        })
        source['value'] += value

    scope, series = query['scope'], query['series']
    title = _('Categories and subcategories')
    if scope == 'ledger':
        snapshot = get_ledger_snapshot(user, last)
        title = _('Balances by bank and account')
        missing.update(snapshot['missing_currencies'])
        for row in snapshot['accounts']:
            if row['converted_balance'] is not None:
                account = row['account']
                add(row['label'], row['converted_balance'], f'account:{account.pk}',
                    account.name, reverse('banking:detail', args=[account.bank_id]) + f'#account-row-{account.pk}', _('Open account'))
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
                    add(f'{asset.opening_product.bank.name} > {asset.opening_product.name} > {asset.name}',
                        value, f'opening:{asset.pk}', _('Opening position'),
                        reverse('investments:update_asset', args=[asset.pk]), _('Open opening position'))
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
                add(f'{operation.product.bank.name} > {operation.product.name} > {operation.asset.name}',
                    value, f'investment:{operation.pk}', dated(operation.get_kind_display(), operation.date),
                    reverse('investments:update', args=[operation.pk]), _('Open investment operation'))
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
            if item.reward_redemption_id:
                url = reverse('banking:redemption_update', args=[item.reward_redemption_id])
                action = _('Open reward redemption')
            else:
                url = reverse('transactions:update', args=[item.pk])
                action = _('Open transaction')
            for year, month in targets:
                if query.get('cutoff'):
                    occurrence = _transaction_occurrence_date(item, year, month)
                    if occurrence is None or occurrence > date.fromisoformat(query['cutoff']):
                        continue
                value = _transaction_value(user, item, year, month, missing)
                if value is not None:
                    add(path(item.category_id), value, f'transaction:{item.pk}',
                        dated(item.display_title, item.date), url, action)
        if scope == 'cashflow' and series == 'expenses':
            for year, month in targets:
                bank_sources = []
                _total, absent = _banking_expenses_for_month(user, year, month, sources=bank_sources)
                for item, value in bank_sources:
                    if isinstance(item, LoyaltyEntry):
                        name = _('Points purchase: %(name)s') % {'name': item.program.name}
                        url = reverse('banking:entry_update', args=[item.pk])
                        action = _('Open points entry')
                    else:
                        name = _('IOF on reward redemption')
                        url = reverse('banking:redemption_update', args=[item.pk])
                        action = _('Open reward redemption')
                    add(str(_('Bank costs')), value, f'{item._meta.model_name}:{item.pk}',
                        dated(name, item.date), url, action)
                missing.update(absent)

    def cents(value):
        return str(int(value.quantize(Decimal('.01')) * 100))

    rows = []
    for label, value in sorted(totals.items()):
        if value:
            members = list(sources[label].values())
            rounded = [int(cents(source['value'])) for source in members]
            difference = int(cents(value)) - sum(rounded)
            # FX can leave fractional cents. Distribute the rounding residual
            # by remainder so source amounts reconcile without changing totals.
            if difference:
                order = sorted(range(len(members)), key=lambda index:
                               members[index]['value'] * 100 - rounded[index],
                               reverse=difference > 0)
                for index in order[:abs(difference)]:
                    rounded[index] += 1 if difference > 0 else -1
            rows.append({'label': label, 'cents': cents(value), 'sources': [
                {'label': source['label'], 'url': source['url'], 'action': source['action'],
                 'cents': str(amount)}
                for source, amount in zip(members, rounded)
            ]})
    return {'title': title, 'rows': rows, 'missing': sorted(missing), 'currency': base}


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
