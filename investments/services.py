"""Investment ledger synchronization and portfolio aggregation."""

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import BankMovement, LoyaltyEntry, LoyaltyProgram
from banking.services import MissingExchangeRate, convert, create_movement
from investments.models import Investment


ZERO = Decimal('0.00')
CENTS = Decimal('0.01')
TIMESERIES_MONTHS = 12


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
    if (
        operation.kind == Investment.Kind.WITHDRAWAL
        and available_quantity(operation) < operation.quantity
    ):
        from django.core.exceptions import ValidationError

        raise ValidationError(
            {'quantity': _('Withdrawal exceeds the available position on this date.')}
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


def available_quantity(operation):
    """Quantity available in the product/asset immediately before this operation."""
    queryset = Investment.objects.filter(
        user=operation.user,
        product=operation.product,
        asset=operation.asset,
        date__lte=operation.date,
    )
    if operation.pk:
        queryset = queryset.exclude(pk=operation.pk)
    total = ZERO
    for item in queryset.select_for_update():
        total += item.signed_quantity
    return total


def get_portfolio_groups(user):
    """Group positions without adding quantities or values across assets."""
    operations = Investment.objects.filter(user=user).select_related(
        'product__bank', 'asset'
    )
    banks = {}
    for operation in operations:
        bank = operation.product.bank
        bank_bucket = banks.setdefault(bank.pk, {'id': bank.pk, 'name': bank.name, 'products': {}})
        product = bank_bucket['products'].setdefault(
            operation.product_id,
            {
                'id': operation.product_id,
                'name': operation.product.name,
                'yield_mode': operation.product.yield_mode,
                'assets': {},
            },
        )
        asset = product['assets'].setdefault(
            operation.asset_id,
            {
                'id': operation.asset_id,
                'name': operation.asset.name,
                'code': operation.asset.code,
                'currency': operation.asset.currency,
                'quantity': ZERO,
                'deposits': ZERO,
                'withdrawals': ZERO,
                'yields': ZERO,
            },
        )
        asset['quantity'] += operation.signed_quantity
        key = {
            Investment.Kind.DEPOSIT: 'deposits',
            Investment.Kind.WITHDRAWAL: 'withdrawals',
            Investment.Kind.YIELD: 'yields',
        }[operation.kind]
        asset[key] += operation.gross_value
    result = []
    for bank in banks.values():
        bank['products'] = list(bank['products'].values())
        for product in bank['products']:
            product['assets'] = list(product['assets'].values())
        result.append(bank)
    return result


def get_asset_positions(user):
    positions = {}
    for operation in Investment.objects.filter(user=user).select_related('asset'):
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


def _converted(user, operation, base_currency, on_date=None):
    try:
        return convert(
            user,
            operation.gross_value,
            operation.asset.currency,
            base_currency,
            as_of=on_date or operation.date,
        )
    except MissingExchangeRate:
        return None


def get_total_in_base_timeseries(user, base_currency, currencies=None, months=12, offset=0):
    operations = list(Investment.objects.filter(user=user).select_related('asset'))
    missing = set()
    rows = []
    running = ZERO
    window = _months_window(months, offset)
    start = date(*window[0], 1)
    for operation in operations:
        if operation.date < start:
            value = _converted(user, operation, base_currency)
            if value is None:
                missing.add(operation.asset.currency)
            else:
                running += value if operation.kind != Investment.Kind.WITHDRAWAL else -value
    for year, month in window:
        for operation in operations:
            if (operation.date.year, operation.date.month) != (year, month):
                continue
            value = _converted(user, operation, base_currency)
            if value is None:
                missing.add(operation.asset.currency)
            else:
                running += value if operation.kind != Investment.Kind.WITHDRAWAL else -value
        rows.append({'date': date(year, month, 1), 'year': year, 'month': month, 'total': running.quantize(CENTS)})
    return rows, sorted(missing)


def get_monthly_flow_in_base(user, base_currency, currencies=None, months=12, offset=0):
    operations = list(Investment.objects.filter(user=user).select_related('asset'))
    missing = set()
    rows = []
    for year, month in _months_window(months, offset):
        totals = {'deposits': ZERO, 'withdrawals': ZERO, 'yields': ZERO}
        for operation in operations:
            if (operation.date.year, operation.date.month) != (year, month):
                continue
            value = _converted(user, operation, base_currency)
            if value is None:
                missing.add(operation.asset.currency)
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
