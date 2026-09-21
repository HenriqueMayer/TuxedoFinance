from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext

from banking.models import (
    BankAccount,
    BankMovement,
    BankTransfer,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)


ZERO = Decimal('0.00')


class MissingExchangeRate(LookupError):
    pass


def account_balance(account, as_of=None):
    as_of = as_of or timezone.localdate()
    queryset = account.movements.filter(effective_date__lte=as_of)
    amount_field = DecimalField(max_digits=16, decimal_places=2)
    movement_total = queryset.aggregate(
        total=Coalesce(
            Sum(
                Case(
                    When(direction=BankMovement.Direction.CREDIT, then=F('amount')),
                    default=-F('amount'),
                    output_field=amount_field,
                )
            ),
            Value(ZERO),
            output_field=amount_field,
        )
    )['total']
    return account.opening_balance + movement_total


def account_balances(user, as_of=None):
    """Read all native balances with one grouped movement query."""
    as_of = as_of or timezone.localdate()
    amount_field = DecimalField(max_digits=20, decimal_places=2)
    movements = BankMovement.objects.filter(user=user, effective_date__lte=as_of)
    totals = dict(movements.order_by().values('account_id').annotate(
        total=Sum(Case(
            When(direction=BankMovement.Direction.CREDIT, then=F('amount')),
            default=-F('amount'), output_field=amount_field,
        ))
    ).values_list('account_id', 'total'))
    return [
        {'account': account, 'balance': account.opening_balance + totals.get(account.pk, ZERO)}
        for account in BankAccount.objects.filter(user=user).select_related('bank')
    ]


def get_planning_availability(user, as_of=None):
    """Cash usable for planning, without changing balances or hiding deficits.

    Row amounts are native currency; aggregate amounts are in the user's base
    currency. Missing conversions remain None in rows and are flagged explicitly.
    The caller owns ledger synchronization; this calculation never writes it.
    """
    from accounts.models import UserPreference
    from investments.services import get_monthly_cash_positions

    as_of = as_of or timezone.localdate()
    base = UserPreference.objects.filter(user=user).values_list('base_currency', flat=True).first() or 'BRL'
    missing = set()
    rates = {}

    def in_base(amount, currency):
        if currency not in rates:
            try:
                rates[currency] = convert(user, Decimal('1'), currency, base, as_of)
            except MissingExchangeRate:
                rates[currency] = None
                missing.add(currency)
        return None if rates[currency] is None else (amount * rates[currency]).quantize(Decimal('0.01'))

    result = {
        'as_of': as_of, 'base_currency': base, 'account_rows': [], 'cash_pots': [],
        'bank_total': ZERO, 'pot_total': ZERO, 'reserved_total': ZERO,
        'available_total': ZERO, 'reserve_shortfall': ZERO,
    }
    for row in account_balances(user, as_of):
        account, balance = row['account'], row['balance']
        positive = max(balance, ZERO)
        reserved = min(account.reserved_amount, positive) if account.planning_enabled else positive
        shortfall = max(account.reserved_amount - positive, ZERO) if account.planning_enabled else ZERO
        row.update(currency=account.currency, reserved=reserved, available=balance-reserved, shortfall=shortfall)
        for key, total_key in (
            ('balance', 'bank_total'), ('reserved', 'reserved_total'),
            ('shortfall', 'reserve_shortfall'),
        ):
            value = in_base(row[key], account.currency)
            row[f'converted_{key}'] = value
            if value is not None:
                result[total_key] += value
        row['converted_available'] = (
            None if row['converted_balance'] is None
            else row['converted_balance'] - row['converted_reserved']
        )
        if row['converted_available'] is not None:
            result['available_total'] += row['converted_available']
        result['account_rows'].append(row)
    for row in get_monthly_cash_positions(user, as_of):
        row['base_balance'] = in_base(row['balance'], row['currency'])
        if row['base_balance'] is not None:
            result['pot_total'] += row['base_balance']
            result['available_total'] += row['base_balance']
        result['cash_pots'].append(row)
    result['missing_currencies'] = sorted(missing)
    return result


def create_movement(
    *, user, account, direction, kind, amount, effective_date,
    description='', source_key='', **links
):
    movement = BankMovement(
        user=user,
        account=account,
        direction=direction,
        kind=kind,
        amount=amount,
        effective_date=effective_date,
        description=description,
        source_key=source_key,
        **links,
    )
    movement.full_clean()
    movement.save()
    return movement


@transaction.atomic
def sync_loyalty_entry_funding(entry):
    """Synchronize the immediate cash side of a points purchase."""
    entry.full_clean()
    wants_movement = (
        entry.kind == LoyaltyEntry.Kind.PURCHASE
        and entry.funding_account_id is not None
    )
    if wants_movement:
        movement, _ = BankMovement.objects.update_or_create(
            user=entry.user,
            source_key=f'loyalty-entry:{entry.pk}',
            defaults={
                'account': entry.funding_account,
                'direction': BankMovement.Direction.DEBIT,
                'kind': BankMovement.Kind.EXPENSE,
                'amount': entry.cash_amount,
                'effective_date': entry.date,
                'description': gettext('Points purchase: %(program)s') % {
                    'program': entry.program.name,
                },
                'invoice': None,
                'transfer': None,
            },
        )
        if entry.funding_movement_id != movement.pk:
            entry.funding_movement = movement
            entry.save(update_fields=['funding_movement'])
    elif entry.funding_movement_id:
        movement = entry.funding_movement
        entry.funding_movement = None
        entry.save(update_fields=['funding_movement'])
        movement.delete()
    return entry


@transaction.atomic
def cleanup_loyalty_entry_funding(entry):
    movement = entry.funding_movement
    if movement:
        entry.funding_movement = None
        entry.save(update_fields=['funding_movement'])
        movement.delete()


@transaction.atomic
def create_transfer(
    *, user, source_account, destination_account, source_amount,
    destination_amount, date, notes=''
):
    account_ids = sorted([source_account.pk, destination_account.pk])
    locked = {
        account.pk: account
        for account in BankAccount.objects.select_for_update().filter(
            user=user, pk__in=account_ids,
        )
    }
    if len(locked) != len(set(account_ids)):
        raise ValidationError(gettext('One or more transfer accounts no longer exist.'))
    transfer = BankTransfer(
        user=user,
        source_account=locked[source_account.pk],
        destination_account=locked[destination_account.pk],
        source_amount=source_amount,
        destination_amount=destination_amount,
        date=date,
        notes=notes,
    )
    transfer.full_clean()
    if transfer.source_account.currency != transfer.destination_account.currency:
        transfer.fx_source_currency = transfer.source_account.currency
        transfer.fx_target_currency = transfer.destination_account.currency
        transfer.fx_rate = (destination_amount / source_amount).quantize(Decimal('0.00000001'))
        transfer.fx_effective_date = date
        transfer.fx_snapshot_status = BankTransfer.FxSnapshotStatus.CAPTURED
    transfer.save()
    create_movement(
        user=user,
        account=transfer.source_account,
        direction=BankMovement.Direction.DEBIT,
        kind=BankMovement.Kind.TRANSFER,
        amount=source_amount,
        effective_date=date,
        description=notes,
        transfer=transfer,
    )
    create_movement(
        user=user,
        account=transfer.destination_account,
        direction=BankMovement.Direction.CREDIT,
        kind=BankMovement.Kind.TRANSFER,
        amount=destination_amount,
        effective_date=date,
        description=notes,
        transfer=transfer,
    )
    return transfer


def latest_exchange_rate(user, from_currency, to_currency, as_of=None):
    if from_currency == to_currency:
        return None
    as_of = as_of or timezone.localdate()
    return (
        ExchangeRate.objects.filter(
            user=user,
            from_currency=from_currency,
            to_currency=to_currency,
            effective_date__lte=as_of,
        )
        .order_by('-effective_date', '-created_at')
        .first()
    )


def convert(user, amount, from_currency, to_currency, as_of=None):
    amount = Decimal(amount)
    if from_currency == to_currency:
        return amount
    direct = latest_exchange_rate(user, from_currency, to_currency, as_of)
    if direct:
        return amount * direct.rate
    inverse = latest_exchange_rate(user, to_currency, from_currency, as_of)
    if inverse:
        return amount / inverse.rate
    raise MissingExchangeRate(
        gettext('No %(from_currency)s/%(to_currency)s exchange rate is available as of %(date)s.')
        % {
            'from_currency': from_currency,
            'to_currency': to_currency,
            'date': as_of or timezone.localdate(),
        }
    )


@transaction.atomic
def create_reward_redemption(
    *, user, program, points, target_account, target_amount, date,
    iof_amount=ZERO, iof_account=None, iof_credit_card=None, notes=''
):
    program = LoyaltyProgram.objects.select_for_update().get(pk=program.pk, user=user)
    if program.balance < Decimal(points):
        raise ValidationError({'points': gettext('The program does not have enough points.')})
    redemption = RewardRedemption(
        user=user,
        program=program,
        points=points,
        target_account=target_account,
        target_amount=target_amount,
        iof_amount=iof_amount,
        iof_account=iof_account,
        iof_credit_card=iof_credit_card,
        date=date,
        notes=notes,
    )
    redemption.full_clean()
    redemption.save()
    entry = LoyaltyEntry(
        user=user,
        program=program,
        direction=LoyaltyEntry.Direction.DEBIT,
        kind=LoyaltyEntry.Kind.REDEMPTION,
        amount=points,
        date=date,
        notes=notes,
    )
    entry.full_clean()
    entry.save()
    reward_movement = create_movement(
        user=user,
        account=target_account,
        direction=BankMovement.Direction.CREDIT,
        kind=BankMovement.Kind.REWARD,
        amount=target_amount,
        effective_date=date,
        description=notes,
        source_key=f'reward-redemption:{redemption.pk}:reward',
    )
    iof_movement = None
    if iof_account is not None:
        iof_movement = create_movement(
            user=user,
            account=iof_account,
            direction=BankMovement.Direction.DEBIT,
            kind=BankMovement.Kind.EXPENSE,
            amount=iof_amount,
            effective_date=date,
            description=(
                gettext('IOF on reward redemption: %(notes)s') % {'notes': notes}
            ).strip(),
            source_key=f'reward-redemption:{redemption.pk}:iof',
        )
    # Credit-card IOF intentionally has no movement yet. The persisted
    # redemption exposes has_pending_credit_card_iof for invoice integration.
    redemption.loyalty_entry = entry
    redemption.reward_movement = reward_movement
    redemption.iof_movement = iof_movement
    redemption.save(
        update_fields=['loyalty_entry', 'reward_movement', 'iof_movement']
    )
    return redemption
