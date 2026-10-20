"""Investment ledger synchronization and portfolio aggregation."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import BankMovement, LoyaltyEntry, LoyaltyProgram
from banking.services import MissingExchangeRate, convert, create_movement, latest_exchange_rate
from accounts.models import UserPreference
from investments.models import Asset, Investment, InvestmentProduct


ZERO = Decimal('0.00')
CENTS = Decimal('0.01')
TIMESERIES_MONTHS = 12
YIELD_INPUT_ENDING_BALANCE = 'ENDING_BALANCE'
YIELD_INPUT_AMOUNT = 'YIELD_AMOUNT'


@transaction.atomic
def create_guided_investment(user, values):
    """Create owned configuration/opening evidence together, never a cash debit."""
    from django.contrib.auth import get_user_model
    from banking.models import Bank
    from investments.models import PositionPlanningSetting

    get_user_model().objects.select_for_update().get(pk=user.pk)
    if values['new_institution']:
        bank = Bank(user=user, name=values['institution_name'])
        bank.full_clean()
        bank.save()
    else:
        bank = Bank.objects.get(user=user, pk=values['institution'].pk)
    product = InvestmentProduct(user=user, bank=bank, name=values['name'], purpose=values['purpose'])
    product.full_clean()
    product.save()
    asset = Asset(user=user, name=values['name'], code=values['code'] or f'APP-{uuid4().hex[:12].upper()}',
        asset_class=values.get('asset_class') or Asset.AssetClass.OTHER, currency=values['currency'],
        valuation_mode=values['valuation_mode'], opening_product=product,
        opening_balance=values['opening_balance'], opening_quantity=values['opening_quantity'],
        opening_unit_price=values['opening_unit_price'], opening_date=values['opening_date'])
    asset.full_clean()
    asset.save()
    from investments.appearance import DEFAULT_ICON, save_position_appearance
    save_position_appearance(user, product, asset, values.get('icon') or DEFAULT_ICON)
    if product.purpose == InvestmentProduct.Purpose.MONTHLY_CASH:
        setting = PositionPlanningSetting(user=user, product=product, asset=asset,
                                          planning_enabled=values['planning_enabled'])
        setting.full_clean()
        setting.save()
    return product, asset


@dataclass(frozen=True)
class MonetaryYieldCalculation:
    previous_balance: Decimal
    yield_amount: Decimal
    ending_balance: Decimal


def opening_unit_value(asset):
    return asset.opening_quantity * asset.opening_unit_price


def refresh_fx_snapshot(operation):
    """Persist the rate used for an investment's base-currency presentation.

    Native amounts remain untouched. Missing rates are recorded explicitly.
    """
    source = operation.currency
    target = UserPreference.for_user(operation.user).base_currency
    operation.fx_source_currency = source
    operation.fx_target_currency = target
    if source == target:
        operation.fx_rate = Decimal('1')
        operation.fx_effective_date = operation.date
        operation.fx_source_rate = None
        operation.fx_snapshot_status = Investment.FxSnapshotStatus.CAPTURED
    else:
        rate = latest_exchange_rate(operation.user, source, target, operation.date)
        if rate is None:
            inverse = latest_exchange_rate(operation.user, target, source, operation.date)
            if inverse is None:
                operation.fx_rate = None
                operation.fx_effective_date = None
                operation.fx_source_rate = None
                operation.fx_snapshot_status = Investment.FxSnapshotStatus.UNKNOWN
            else:
                operation.fx_rate = (Decimal('1') / inverse.rate).quantize(Decimal('0.00000001'))
                operation.fx_effective_date = inverse.effective_date
                operation.fx_source_rate = inverse
                operation.fx_snapshot_status = Investment.FxSnapshotStatus.CAPTURED
        else:
            operation.fx_rate = rate.rate
            operation.fx_effective_date = rate.effective_date
            operation.fx_source_rate = rate
            operation.fx_snapshot_status = Investment.FxSnapshotStatus.CAPTURED
    operation.save(update_fields=[
        'fx_source_currency', 'fx_target_currency', 'fx_rate',
        'fx_effective_date', 'fx_source_rate', 'fx_snapshot_status',
    ])
    return operation


def _description(operation):
    return _('Investment %(id)s: %(product)s') % {
        'id': operation.pk,
        'product': operation.product.name,
    }


@transaction.atomic
def sync_investment_ledger(operation):
    """Create or replace exactly the banking side owned by an operation."""
    if not operation.pk:
        raise ValueError(_('The investment operation must be saved before synchronization.'))
    operation.full_clean()
    from investments.positions import validate_position_history
    validate_position_history(operation.user, [(operation.product_id, operation.asset_id)])
    available = available_value(operation) if operation.asset.valuation_mode == Asset.ValuationMode.MONETARY else available_quantity(operation)
    requested = operation.gross_value if operation.asset.valuation_mode == Asset.ValuationMode.MONETARY else operation.quantity
    if operation.kind == Investment.Kind.WITHDRAWAL and available < requested:
        from django.core.exceptions import ValidationError

        raise ValidationError(
            {'amount': _('Withdrawal exceeds the available position on this date.')}
        )
    source_key = f'investment:{operation.pk}'
    wants_movement = (
        operation.kind == Investment.Kind.WITHDRAWAL
        or (operation.kind == Investment.Kind.DEPOSIT and operation.source_account_id)
    )
    wants_loyalty = (
        operation.kind == Investment.Kind.DEPOSIT and operation.source_program_id
    )

    if wants_movement:
        movement = operation.bank_movement
        if movement is None:
            movement = BankMovement.objects.filter(
                user=operation.user, source_key=source_key
            ).first()
        account = (
            operation.source_account
            if operation.kind == Investment.Kind.DEPOSIT
            else operation.destination_account
        )
        direction = (
            BankMovement.Direction.DEBIT
            if operation.kind == Investment.Kind.DEPOSIT
            else BankMovement.Direction.CREDIT
        )
        if movement is None:
            movement = create_movement(
                user=operation.user,
                account=account,
                direction=direction,
                kind=BankMovement.Kind.INVESTMENT,
                amount=operation.cash_amount,
                effective_date=operation.date,
                description=_description(operation),
                source_key=source_key,
            )
        else:
            movement.account = account
            movement.direction = direction
            movement.kind = BankMovement.Kind.INVESTMENT
            movement.amount = operation.cash_amount
            movement.effective_date = operation.date
            movement.description = _description(operation)
            movement.source_key = source_key
            movement.full_clean()
            movement.save()
        if operation.bank_movement_id != movement.pk:
            operation.bank_movement = movement
            operation.save(update_fields=['bank_movement'])
    elif operation.bank_movement_id:
        movement = operation.bank_movement
        operation.bank_movement = None
        operation.save(update_fields=['bank_movement'])
        movement.delete()

    if wants_loyalty:
        program = LoyaltyProgram.objects.select_for_update().get(
            pk=operation.source_program_id,
            user=operation.user,
        )
        operation.source_program = program
        entry = operation.loyalty_entry
        available = operation.source_program.balance
        if entry and entry.program_id == operation.source_program_id:
            available += entry.amount
        if available < operation.source_points:
            from django.core.exceptions import ValidationError

            raise ValidationError({'source_points': _('The program does not have enough points.')})
        if entry is None:
            entry = LoyaltyEntry()
        entry.user = operation.user
        entry.program = operation.source_program
        entry.direction = LoyaltyEntry.Direction.DEBIT
        entry.kind = LoyaltyEntry.Kind.REDEMPTION
        entry.amount = operation.source_points
        entry.date = operation.date
        entry.notes = f'[{source_key}] {_description(operation)}'
        entry.full_clean()
        entry.save()
        if operation.loyalty_entry_id != entry.pk:
            operation.loyalty_entry = entry
            operation.save(update_fields=['loyalty_entry'])
    elif operation.loyalty_entry_id:
        entry = operation.loyalty_entry
        operation.loyalty_entry = None
        operation.save(update_fields=['loyalty_entry'])
        entry.delete()
    return operation


@transaction.atomic
def cleanup_investment_ledger(operation):
    movement = operation.bank_movement
    entry = operation.loyalty_entry
    operation.bank_movement = None
    operation.loyalty_entry = None
    if operation.pk:
        operation.save(update_fields=['bank_movement', 'loyalty_entry'])
    if movement:
        movement.delete()
    if entry:
        entry.delete()


def monetary_position_before(*, user, product, asset, operation_date, operation=None, lock=False):
    """Return a monetary position immediately before an operation.

    Existing same-day operations are ordered by their registration timestamp.
    A new operation therefore follows all operations already registered on its
    date; an edited operation keeps its original place in that ordering.
    """
    if asset.valuation_mode != Asset.ValuationMode.MONETARY:
        raise ValueError('A monetary position requires a monetary asset.')

    queryset = Investment.objects.filter(user=user, product=product, asset=asset)
    if operation and operation.pk and operation.created_at:
        queryset = queryset.filter(
            Q(date__lt=operation_date)
            | Q(date=operation_date, created_at__lt=operation.created_at)
        )
    else:
        queryset = queryset.filter(date__lte=operation_date)
    queryset = queryset.order_by('date', 'created_at', 'pk')
    if lock:
        queryset = queryset.select_for_update()

    total = asset.opening_balance if asset.opening_product_id == product.pk and (not asset.opening_date or asset.opening_date <= operation_date) else ZERO
    for item in queryset:
        total += item.signed_value
    return total.quantize(CENTS)


def calculate_monetary_yield(
    *, user, product, asset, operation_date, input_mode, value, operation=None, lock=False
):
    """Calculate a monetary yield from either the final balance or the yield."""
    field = 'ending_balance' if input_mode == YIELD_INPUT_ENDING_BALANCE else 'amount'
    if value is None:
        message = (
            _('Enter the new investment balance.')
            if input_mode == YIELD_INPUT_ENDING_BALANCE
            else _('Enter the yield amount.')
        )
        raise ValidationError({field: message})

    previous_balance = monetary_position_before(
        user=user,
        product=product,
        asset=asset,
        operation_date=operation_date,
        operation=operation,
        lock=lock,
    )
    if input_mode == YIELD_INPUT_ENDING_BALANCE:
        ending_balance = value.quantize(CENTS)
        yield_amount = (ending_balance - previous_balance).quantize(CENTS)
        if yield_amount == ZERO:
            raise ValidationError({
                'ending_balance': _('The new balance must be greater than the previous balance.'),
            })
        if yield_amount < ZERO:
            raise ValidationError({
                'ending_balance': _('The new balance is lower than the previous balance. Record a withdrawal instead.'),
            })
    elif input_mode == YIELD_INPUT_AMOUNT:
        yield_amount = value.quantize(CENTS)
        if yield_amount <= ZERO:
            raise ValidationError({'amount': _('Enter a positive yield amount.')})
        ending_balance = (previous_balance + yield_amount).quantize(CENTS)
    else:
        raise ValidationError({'yield_input_mode': _('Choose how to enter the yield.')})

    return MonetaryYieldCalculation(
        previous_balance=previous_balance,
        yield_amount=yield_amount,
        ending_balance=ending_balance,
    )


def available_value(operation):
    """Position value available immediately before this operation."""
    return monetary_position_before(
        user=operation.user,
        product=operation.product,
        asset=operation.asset,
        operation_date=operation.date,
        operation=operation,
        lock=True,
    )


def available_quantity(operation):
    """Unit position available immediately before this operation."""
    queryset = Investment.objects.filter(
        user=operation.user,
        product=operation.product,
        asset=operation.asset,
    )
    if operation.pk and operation.created_at:
        queryset = queryset.filter(Q(date__lt=operation.date) | Q(date=operation.date, created_at__lt=operation.created_at)
                                   | Q(date=operation.date, created_at=operation.created_at, pk__lt=operation.pk))
    else:
        queryset = queryset.filter(date__lte=operation.date)
    total = (
        operation.asset.opening_quantity
        if operation.asset.opening_product_id == operation.product_id and (not operation.asset.opening_date or operation.asset.opening_date <= operation.date)
        else ZERO
    )
    for item in queryset.select_for_update():
        total += item.signed_quantity
    return total


def get_monthly_cash_positions(user, as_of=None):
    """Native monetary balances by product and asset, including openings once."""
    as_of = as_of or timezone.localdate()
    rows = {}

    def position(product, asset):
        return rows.setdefault((product.pk, asset.pk), {
            'product': product, 'asset': asset, 'currency': asset.currency, 'balance': ZERO,
        })

    for asset in Asset.objects.filter(
        user=user, valuation_mode=Asset.ValuationMode.MONETARY,
        opening_product__purpose=InvestmentProduct.Purpose.MONTHLY_CASH,
        opening_product__user=user,
    ).filter(Q(opening_date__isnull=True) | Q(opening_date__lte=as_of)).select_related('opening_product__bank'):
        position(asset.opening_product, asset)['balance'] += asset.opening_balance
    for operation in Investment.objects.filter(
        user=user, product__purpose=InvestmentProduct.Purpose.MONTHLY_CASH,
        product__user=user, asset__user=user,
        asset__valuation_mode=Asset.ValuationMode.MONETARY, date__lte=as_of,
    ).select_related('product__bank', 'asset'):
        position(operation.product, operation.asset)['balance'] += operation.signed_value
    return sorted(rows.values(), key=lambda row: (
        row['product'].bank.name, row['product'].name, row['asset'].name,
    ))


def get_portfolio_groups(user, as_of=None, purpose=None, *, snapshot=None):
    """Group remaining cost and observed valuation without mixing positions."""
    from investments.positions import get_portfolio_valuation
    snapshot = snapshot if snapshot is not None else get_portfolio_valuation(user, as_of, purpose)
    banks = {}
    for row in snapshot['positions']:
        product, asset = row['product'], row['asset']
        bank = banks.setdefault(product.bank_id, {'id': product.bank_id, 'name': product.bank.name, 'products': {}})
        group = bank['products'].setdefault(product.pk, {'id': product.pk, 'name': product.name, 'purpose': product.purpose, 'yield_mode': product.yield_mode, 'assets': []})
        group['assets'].append({**row, 'id': asset.pk, 'name': asset.name, 'code': asset.code,
                                'currency': asset.currency, 'is_archived': asset.is_archived,
                                'valuation_mode': asset.valuation_mode})
    for bank in banks.values():
        bank['products'] = sorted(bank['products'].values(), key=lambda item: (item['name'].casefold(), item['id']))
        for product in bank['products']:
            product['assets'].sort(key=lambda item: (item['name'].casefold(), item['id']))
    return sorted(banks.values(), key=lambda item: (item['name'].casefold(), item['id']))


def get_asset_positions(user, as_of=None):
    as_of = as_of or timezone.localdate()
    positions = {
        asset.pk: {
            'asset': asset,
            'quantity': asset.opening_quantity,
            'value_flow': asset.opening_balance + opening_unit_value(asset),
        }
        for asset in Asset.objects.filter(user=user)
    }
    for operation in Investment.objects.filter(user=user, date__lte=as_of).select_related('asset'):
        row = positions.setdefault(
            operation.asset_id,
            {
                'asset': operation.asset,
                'quantity': ZERO,
                'value_flow': ZERO,
            },
        )
        row['quantity'] += operation.signed_quantity
        row['value_flow'] += operation.signed_value
    return list(positions.values())


def _add_months(year, month, offset):
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1


def _months_window(months, offset):
    today = timezone.localdate()
    anchor = _add_months(today.year, today.month, offset)
    return [_add_months(*anchor, -(months - 1) + step) for step in range(months)]


def historical_value_in_base(user, operation, base_currency, on_date=None, *, conversion=None):
    # Native values need no conversion, even after changing the reporting
    # currency away from the target retained in an older FX snapshot.
    if operation.currency == base_currency:
        return operation.gross_value
    if operation.fx_snapshot_status in {
        Investment.FxSnapshotStatus.CAPTURED,
        Investment.FxSnapshotStatus.RECONSTRUCTED,
    }:
        if operation.fx_source_currency != operation.currency or not operation.fx_rate:
            return None
        historical = operation.gross_value * operation.fx_rate
        if operation.fx_target_currency == base_currency:
            return historical
        return None
    if (operation.fx_snapshot_status == Investment.FxSnapshotStatus.UNKNOWN
            and operation.fx_source_currency and operation.fx_target_currency):
        return None
    try:
        if conversion is not None:
            return conversion.check_user(user).convert(operation.gross_value, operation.currency, base_currency, on_date or operation.date)
        return convert(user, operation.gross_value, operation.currency, base_currency, as_of=on_date or operation.date)
    except MissingExchangeRate:
        return None


def get_total_in_base_timeseries(user, base_currency, currencies=None, months=12, offset=0, purpose=None, fx_issues=None):
    from investments.positions import get_portfolio_series, get_portfolio_valuation
    window = _months_window(months, offset)
    snapshots = get_portfolio_series(user, base_currency, window, purpose)
    start = date(*window[0], 1)
    prior = start.fromordinal(start.toordinal() - 1) if start > date.min else start
    opening = get_portfolio_valuation(user, prior, purpose, base_currency, historical=True, opening_fallback_date=start)['total']
    rows, missing = [], set()
    for (year, month), snapshot in zip(window, snapshots):
        rows.append({'date': date(year, month, 1), 'year': year, 'month': month,
                     'opening_balance': opening, 'total': snapshot['total'],
                     'cost_total': snapshot['cost_total'], 'realized_total': snapshot['realized_total'],
                     'unrealized_total': snapshot['unrealized_total'], 'snapshot': snapshot})
        opening = snapshot['total']
        missing.update(snapshot['missing_currencies'])
        if fx_issues is not None:
            fx_issues.extend(snapshot['fx_issues'])
    return rows, sorted(missing)


def get_monthly_flow_in_base(user, base_currency, currencies=None, months=12, offset=0, purpose=InvestmentProduct.Purpose.INVESTMENT, fx_issues=None):
    operations_query = Investment.objects.filter(user=user)
    if purpose is not None:
        operations_query = operations_query.filter(product__purpose=purpose)
    operations = list(operations_query.select_related('asset'))
    missing = set()
    rows = []
    for year, month in _months_window(months, offset):
        totals = {'deposits': ZERO, 'withdrawals': ZERO, 'yields': ZERO}
        for operation in operations:
            if (operation.date.year, operation.date.month) != (year, month):
                continue
            value = historical_value_in_base(user, operation, base_currency)
            if value is None:
                missing.add(operation.asset.currency)
                if fx_issues is not None:
                    fx_issues.append({'operation': operation, 'date': operation.date})
                continue
            key = {
                Investment.Kind.DEPOSIT: 'deposits',
                Investment.Kind.WITHDRAWAL: 'withdrawals',
                Investment.Kind.YIELD: 'yields',
            }[operation.kind]
            totals[key] += value
        rows.append({
            'date': date(year, month, 1), 'year': year, 'month': month,
            **{key: value.quantize(CENTS) for key, value in totals.items()},
        })
    return rows, sorted(missing)
