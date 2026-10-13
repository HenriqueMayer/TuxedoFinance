# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Ordered position replay, weighted acquisition cost and local valuations.

Cash settlement belongs to services.py. This module never posts movements or
rewrites historical operations, FX evidence, opening positions or fee metadata.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal, localcontext

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import UserPreference
from banking.services import ConversionContext, MissingExchangeRate
from investments.models import Asset, Investment, PriceObservation

ZERO = Decimal('0')
CENTS = Decimal('.01')


def replay_positions(assets, operations, as_of=None, *, strict=False):
    """Return independent product/asset positions in date/registration order.

    Unit yields retain their declared entry value. Fee currency is deliberately
    opt-in: old fees remain metadata, and cash_amount is never inferred.
    """
    as_of = as_of or timezone.localdate()
    positions = {}

    def position(product, asset):
        return positions.setdefault((product.pk, asset.pk), {
            'product': product, 'asset': asset, 'quantity': ZERO,
            'remaining_cost': ZERO, 'balance': ZERO, 'realized_gain': ZERO,
            'deposits': ZERO, 'withdrawals': ZERO, 'yields': ZERO,
            'fees': ZERO, 'unapplied_fees': ZERO, 'cost_components': [],
            'realized_components': [], 'yield_components': [],
            'baseline_unknown': False, 'history_errors': [],
        })

    def invalid(row, operation):
        message = _('Operation %(id)s exceeds the available position on %(date)s.') % {'id': operation.pk or '—', 'date': operation.date}
        if strict:
            raise ValidationError({'date': message})
        row['history_errors'].append(str(message))

    with localcontext() as context:
        context.prec = 40
        for asset in assets:
            if not asset.opening_product_id or not asset.has_opening_position:
                continue
            if asset.opening_date and asset.opening_date > as_of:
                continue
            row = position(asset.opening_product, asset)
            value = asset.opening_balance + asset.opening_quantity * asset.opening_unit_price
            row.update(quantity=asset.opening_quantity, remaining_cost=value, balance=value,
                       baseline_unknown=asset.opening_date is None)
            row['cost_components'].append({'asset': asset, 'operation': None, 'amount': value})
        for operation in sorted(operations, key=lambda item: (item.date, item.created_at or timezone.now(), item.pk or float('inf'))):
            if operation.date > as_of:
                continue
            asset = operation.asset
            row = position(operation.product, asset)
            if (asset.opening_product_id == operation.product_id and asset.has_opening_position
                    and asset.opening_date and operation.date < asset.opening_date):
                invalid(row, operation)
            gross = operation.gross_value
            row[{'DEPOSIT': 'deposits', 'WITHDRAWAL': 'withdrawals', 'YIELD': 'yields'}[operation.kind]] += gross
            row['fees'] += operation.fees
            applied_fee = operation.fees if operation.fees_in_asset_currency else ZERO
            if not operation.fees_in_asset_currency:
                row['unapplied_fees'] += operation.fees
            if operation.kind == Investment.Kind.YIELD:
                row['yield_components'].append({'operation': operation, 'amount': gross})
            if asset.valuation_mode == Asset.ValuationMode.MONETARY:
                row['balance'] += operation.signed_value
                row['remaining_cost'] = row['balance']
                if row['balance'] < ZERO:
                    invalid(row, operation)
                # Monetary balance observations remain amounts, not unit cost.
                row['cost_components'].append({'asset': asset, 'operation': operation, 'amount': operation.signed_value})
                continue
            if operation.kind != Investment.Kind.WITHDRAWAL:
                acquired_cost = gross + applied_fee
                row['quantity'] += operation.quantity
                row['remaining_cost'] += acquired_cost
                row['cost_components'].append({'asset': asset, 'operation': operation, 'amount': acquired_cost})
            else:
                before = row['quantity']
                if before < operation.quantity:
                    invalid(row, operation)
                released = row['remaining_cost'] * operation.quantity / before if before else ZERO
                gain = gross - applied_fee - released
                row['realized_gain'] += gain
                row['realized_components'].append({'operation': operation, 'amount': gain})
                row['quantity'] -= operation.quantity
                row['remaining_cost'] -= released
                ratio = row['quantity'] / before if before else ZERO
                for component in row['cost_components']:
                    component['amount'] *= ratio
                if row['quantity'] == ZERO:
                    # A complete disposal releases the complete remaining cost.
                    row['remaining_cost'] = ZERO
                    row['cost_components'] = []
            row['balance'] = row['remaining_cost']
        for row in positions.values():
            row['average_cost'] = row['remaining_cost'] / row['quantity'] if row['quantity'] else ZERO
    return list(positions.values())


def load_position_sources(user, purpose=None):
    assets = Asset.objects.filter(user=user).select_related('opening_product__bank')
    operations = Investment.objects.filter(user=user).select_related('asset', 'product__bank')
    if purpose:
        assets = assets.filter(opening_product__purpose=purpose)
        operations = operations.filter(product__purpose=purpose)
    prices = PriceObservation.objects.filter(user=user).select_related('asset').order_by('date', 'created_at', 'pk')
    return list(assets), list(operations), list(prices)


def validate_position_history(user, pairs, *, exclude_pk=None, exclude_pks=None):
    """Check the entire affected sequence, including operations after an edit."""
    pairs = set(pairs)
    if not pairs:
        return
    predicate = Q(pk__in=[])
    for product_id, asset_id in pairs:
        predicate |= Q(product_id=product_id, asset_id=asset_id)
    operations = Investment.objects.filter(user=user).filter(predicate).select_related('asset', 'product__bank')
    if exclude_pk:
        operations = operations.exclude(pk=exclude_pk)
    if exclude_pks:
        operations = operations.exclude(pk__in=exclude_pks)
    assets = Asset.objects.filter(user=user, pk__in=[pair[1] for pair in pairs]).select_related('opening_product__bank')
    replay_positions(assets, operations, date.max, strict=True)


def validate_position_candidate(operation):
    """Replay a proposed edit before saving, including its old position."""
    pairs = {(operation.product_id, operation.asset_id)}
    if operation.pk:
        previous = Investment.objects.filter(pk=operation.pk, user=operation.user).values_list('product_id', 'asset_id').first()
        if previous:
            pairs.add(previous)
    predicate = Q(pk__in=[])
    for product_id, asset_id in pairs:
        predicate |= Q(product_id=product_id, asset_id=asset_id)
    operations = list(Investment.objects.filter(user=operation.user).filter(predicate).exclude(pk=operation.pk).select_related('asset', 'product__bank'))
    operations.append(operation)
    assets = Asset.objects.filter(user=operation.user, pk__in=[pair[1] for pair in pairs]).select_related('opening_product__bank')
    replay_positions(assets, operations, date.max, strict=True)


def _historical_component(user, component, base, fallback_date, conversion):
    from investments.services import historical_value_in_base
    amount = component['amount']
    if not amount:
        return ZERO
    operation = component.get('operation')
    if operation:
        converted = historical_value_in_base(user, operation, base, conversion=conversion)
        return None if converted is None else amount * converted / operation.gross_value
    asset = component['asset']
    try:
        return conversion.convert(amount, asset.currency, base, asset.opening_date or fallback_date)
    except MissingExchangeRate:
        return None


def value_positions(user, rows, prices, base, as_of, *, historical=False, opening_fallback_date=None, conversion=None):
    """Value one replay with the last declared price, exposing cost fallbacks."""
    conversion = ConversionContext(user, base) if conversion is None else conversion.check_user(user)
    selected_prices = {}
    for observation in prices:
        if observation.date <= as_of:
            selected_prices[observation.asset_id] = observation
    missing_rates, performance_missing, missing_prices, unknown, errors, unapplied_fees = set(), set(), [], [], [], []
    native_totals, totals = {}, {'total': ZERO, 'cost_total': ZERO, 'realized_total': ZERO,
                               'unrealized_total': ZERO, 'yield_total': ZERO}
    fx_issues = []
    for row in rows:
        asset = row['asset']
        observation = selected_prices.get(asset.pk)
        units = asset.valuation_mode == Asset.ValuationMode.UNITS
        market_available = not units or not row['quantity'] or observation is not None
        value = row['balance']
        if units and observation and row['quantity']:
            value = row['quantity'] * observation.unit_price
        row.update(valuation=value, price_observation=observation if units else None,
                   market_available=market_available,
                   unrealized_gain=(value - row['remaining_cost']) if market_available and units else None)
        if not market_available:
            missing_prices.append(row)
        if row['baseline_unknown']:
            unknown.append(row)
        if row['unapplied_fees']:
            unapplied_fees.append(row)
        errors.extend(row['history_errors'])
        currency = asset.currency
        native_totals[currency] = native_totals.get(currency, ZERO) + value

        def current(amount):
            if amount is None:
                return None
            if not amount:
                return ZERO
            try:
                return conversion.convert(amount, currency, base, as_of)
            except MissingExchangeRate:
                missing_rates.add(currency)
                fx_issues.append({'asset': asset, 'date': as_of})
                return None

        component_issues = []

        def components(items):
            total = ZERO
            for component in items:
                value_in_base = _historical_component(user, component, base, opening_fallback_date or as_of, conversion)
                if value_in_base is None:
                    performance_missing.add(currency)
                    component_issues.append({'operation': component.get('operation'), 'asset': asset,
                                      'date': component['operation'].date if component.get('operation') else (asset.opening_date or opening_fallback_date or as_of)})
                    return None
                total += value_in_base
            return total

        row['base_cost'] = components(row['cost_components']) if historical else current(row['remaining_cost'])
        row['base_value'] = (current(value) if market_available or not historical else row['base_cost'])
        if row['base_value'] is None:
            missing_rates.add(currency)
            fx_issues.extend(component_issues)
        row['base_realized_gain'] = components(row['realized_components'])
        row['base_yields'] = components(row['yield_components'])
        row['base_unrealized_gain'] = (
            row['base_value'] - row['base_cost'] if units and market_available
            and row['base_value'] is not None and row['base_cost'] is not None else None)
        for row_key, total_key in [('base_value', 'total'), ('base_cost', 'cost_total'),
                                   ('base_realized_gain', 'realized_total'), ('base_yields', 'yield_total'),
                                   ('base_unrealized_gain', 'unrealized_total')]:
            if row[row_key] is not None:
                totals[total_key] += row[row_key]
    return {**{key: value.quantize(CENTS) for key, value in totals.items()},
            'positions': rows, 'native_totals': sorted(native_totals.items()),
            'missing_currencies': sorted(missing_rates), 'missing_prices': missing_prices,
            'performance_missing_currencies': sorted(performance_missing),
            'unknown_baselines': unknown, 'history_errors': errors, 'fx_issues': fx_issues,
            'unapplied_fee_positions': unapplied_fees,
            'as_of': as_of, 'base_currency': base,
            'complete': not missing_rates and not missing_prices and not errors,
            'performance_complete': not missing_rates and not performance_missing and not missing_prices and not unknown and not errors and not unapplied_fees}


def get_portfolio_valuation(user, as_of=None, purpose=None, base_currency=None, *, historical=False, opening_fallback_date=None, conversion=None):
    """Public wealth snapshot, including archived positions and explicit gaps."""
    as_of = as_of or timezone.localdate()
    base = base_currency or UserPreference.for_user(user).base_currency
    assets, operations, prices = load_position_sources(user, purpose)
    rows = replay_positions(assets, operations, as_of)
    return value_positions(user, rows, prices, base, as_of, historical=historical, opening_fallback_date=opening_fallback_date, conversion=conversion)


def get_portfolio_series(user, base_currency, periods, purpose=None, *, conversion=None):
    """Public month-end wealth/results series; gaps are carried with each row."""
    periods = list(periods)
    conversion = ConversionContext(user, base_currency) if conversion is None else conversion.check_user(user)
    assets, operations, prices = load_position_sources(user, purpose)
    snapshots = []
    for year, month in periods:
        day = date(year, month, monthrange(year, month)[1])
        snapshots.append(value_positions(user, replay_positions(assets, operations, day), prices,
                                        base_currency, day, historical=True,
                                        opening_fallback_date=date(*periods[0], 1), conversion=conversion))
    return snapshots
