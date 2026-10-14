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


def _opening_balance_as_of(account, as_of):
    # Undated legacy openings retain their established behavior; a newly dated
    # baseline must not appear in periods before its effective date.
    return account.opening_balance if account.opening_date is None or account.opening_date <= as_of else ZERO


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
    return _opening_balance_as_of(account, as_of) + movement_total


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
        {'account': account, 'balance': _opening_balance_as_of(account, as_of) + totals.get(account.pk, ZERO)}
        for account in BankAccount.objects.filter(user=user).select_related('bank')
    ]


def get_planning_availability(user, as_of=None, *, conversion=None):
    """Cash usable for planning, without changing balances or hiding deficits.

    Row amounts are native currency; aggregate amounts are in the user's base
    currency. Missing conversions remain None in rows and are flagged explicitly.
    The caller owns ledger synchronization; this calculation never writes it.
    """
    from accounts.models import UserPreference
    from investments.models import PositionPlanningSetting
    from investments.services import get_monthly_cash_positions
    from planning.services import reserved_by_source

    as_of = as_of or timezone.localdate()
    if conversion is None:
        # This read service also works before a preference row is initialized.
        base = UserPreference.objects.filter(user=user).values_list('base_currency', flat=True).first() or 'BRL'
        conversion = ConversionContext(user, base_currency=base)
    else:
        conversion.check_user(user)
        base = conversion.base_currency
    named_reserves = reserved_by_source(user, as_of)
    missing = set()
    rates = {}

    def in_base(amount, currency):
        if currency not in rates:
            try:
                rates[currency] = conversion.convert(Decimal('1'), currency, as_of=as_of)
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
        named = named_reserves['accounts'].get(account.pk, ZERO)
        # Named goals label the existing reserve rather than reserving it twice.
        requested = max(account.reserved_amount, named)
        reserved = min(requested, positive) if account.planning_enabled else positive
        shortfall = max(requested - positive, ZERO) if account.planning_enabled else ZERO
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
    position_settings = {
        (setting.product_id, setting.asset_id): setting.planning_enabled
        for setting in PositionPlanningSetting.objects.filter(
            user=user, product__user=user, asset__user=user)
    }
    for row in get_monthly_cash_positions(user, as_of):
        row['planning_enabled'] = position_settings.get((row['product'].pk, row['asset'].pk), True)
        requested = named_reserves['cash_pots'].get((row['product'].pk, row['asset'].pk), ZERO)
        positive = max(row['balance'], ZERO)
        row['reserved'] = min(requested, positive) if row['planning_enabled'] else positive
        row['available'] = row['balance'] - row['reserved']
        row['shortfall'] = max(requested - positive, ZERO) if row['planning_enabled'] else ZERO
        row['base_balance'] = in_base(row['balance'], row['currency'])
        row['base_reserved'] = in_base(row['reserved'], row['currency'])
        row['base_shortfall'] = in_base(row['shortfall'], row['currency'])
        row['base_available'] = (
            None if row['base_balance'] is None
            else row['base_balance'] - row['base_reserved']
        )
        if row['base_balance'] is not None:
            result['pot_total'] += row['base_balance']
            result['reserved_total'] += row['base_reserved']
            result['reserve_shortfall'] += row['base_shortfall']
            result['available_total'] += row['base_available']
        result['cash_pots'].append(row)
    result['included_account_rows'] = [row for row in result['account_rows'] if row['account'].planning_enabled]
    result['reserved_account_rows'] = [row for row in result['account_rows'] if not row['account'].planning_enabled]
    result['included_cash_pots'] = [row for row in result['cash_pots'] if row['planning_enabled']]
    result['reserved_cash_pots'] = [row for row in result['cash_pots'] if not row['planning_enabled']]
    result['missing_currencies'] = sorted(missing)
    return result


@transaction.atomic
def set_position_planning(user, product_id, asset_id, enabled):
    """Set aside a known owned cash position; never post or rewrite money."""
    from django.contrib.auth import get_user_model
    from investments.models import PositionPlanningSetting
    from investments.services import get_monthly_cash_positions

    get_user_model().objects.select_for_update().get(pk=user.pk)
    source = next((row for row in get_monthly_cash_positions(user)
                   if row['product'].pk == product_id and row['asset'].pk == asset_id), None)
    if source is None:
        raise ValidationError(gettext('This cash position is unavailable.'))
    setting = PositionPlanningSetting.objects.filter(user=user, product_id=product_id, asset_id=asset_id).first()
    setting = setting or PositionPlanningSetting(user=user, product=source['product'], asset=source['asset'])
    setting.planning_enabled = enabled
    setting.full_clean()
    setting.save()
    return setting


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
    # Ledger labels are bounded summaries; the transfer keeps the full notes
    # (including imported statement evidence) for review and undo checks.
    movement_description = notes[:BankMovement._meta.get_field('description').max_length]
    create_movement(
        user=user,
        account=transfer.source_account,
        direction=BankMovement.Direction.DEBIT,
        kind=BankMovement.Kind.TRANSFER,
        amount=source_amount,
        effective_date=date,
        description=movement_description,
        transfer=transfer,
    )
    create_movement(
        user=user,
        account=transfer.destination_account,
        direction=BankMovement.Direction.CREDIT,
        kind=BankMovement.Kind.TRANSFER,
        amount=destination_amount,
        effective_date=date,
        description=movement_description,
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


class ConversionContext:
    """Reuse presentation rates only for one user's current request or calculation.

    Posting and captured historical evidence continue to use their existing
    services. Keeping original inverse rates preserves Decimal division exactly.
    """

    def __init__(self, user, base_currency=None):
        from accounts.models import UserPreference

        self.user = user
        self.user_id = user.pk
        self.base_currency = (
            base_currency if base_currency is not None
            else UserPreference.for_user(user).base_currency
        )
        self.today = timezone.localdate()
        self._rates = {}

    def check_user(self, user):
        if user.pk != self.user_id:
            raise ValueError('A conversion context belongs to exactly one user.')
        return self

    def _rate(self, source, target, as_of):
        key = (source, target, as_of)
        if key not in self._rates:
            self._rates[key] = latest_exchange_rate(self.user, source, target, as_of)
        return self._rates[key]

    def convert(self, amount, from_currency, to_currency=None, as_of=None):
        amount = Decimal(amount)
        to_currency = self.base_currency if to_currency is None else to_currency
        if from_currency == to_currency:
            return amount
        as_of = self.today if as_of is None else as_of
        direct = self._rate(from_currency, to_currency, as_of)
        if direct is not None:
            return amount * direct.rate
        inverse = self._rate(to_currency, from_currency, as_of)
        if inverse is not None:
            return amount / inverse.rate
        raise MissingExchangeRate(
            gettext('No %(from_currency)s/%(to_currency)s exchange rate is available as of %(date)s.')
            % {'from_currency': from_currency, 'to_currency': to_currency, 'date': as_of}
        )


def _iof_category(user):
    from categories.models import Category

    # IOF is the same acronym in both locales. Never reclassify an existing
    # income category; reuse a compatible name or its first available suffix.
    index = 1
    while True:
        name = 'IOF' if index == 1 else f'IOF ({index})'
        category, _ = Category.objects.get_or_create(
            user=user, name=name, defaults={'transaction_type': 'EXPENSE'},
        )
        if category.transaction_type != 'INCOME':
            return category
        index += 1


def sync_redemption_iof_transaction(redemption):
    """Maintain one read-only expense for the redemption's current IOF."""
    from transactions.models import Transaction

    item = Transaction.objects.filter(reward_redemption=redemption).first()
    if not redemption.iof_amount:
        if item:
            item.delete()
        return
    if item is None:
        item = Transaction(user=redemption.user, reward_redemption=redemption,
                           category=_iof_category(redemption.user))
    item.title = 'IOF on reward redemption'
    item.amount = redemption.iof_amount
    item.transaction_type = Transaction.TransactionType.EXPENSE
    item.payment_channel = (
        Transaction.PaymentChannel.CREDIT_CARD if redemption.iof_credit_card_id
        else Transaction.PaymentChannel.ACCOUNT
    )
    item.bank_account = redemption.iof_account
    item.credit_card = redemption.iof_credit_card
    item.date = redemption.date
    item.notes = redemption.notes
    item.full_clean()
    item.save()


@transaction.atomic
def _save_reward_redemption(
    *, user, program, points, target_account, target_amount, date,
    iof_amount=ZERO, iof_account=None, iof_credit_card=None, notes='', redemption=None,
):
    original = None
    if redemption is not None:
        original = RewardRedemption.objects.select_for_update().get(pk=redemption.pk, user=user)
    # An edit restores its original points before checking the new debit.
    program = LoyaltyProgram.objects.select_for_update().get(pk=program.pk, user=user)
    available = program.balance
    if original and original.program_id == program.pk and original.loyalty_entry_id:
        available += original.points
    if available < Decimal(points):
        raise ValidationError({'points': gettext('The program does not have enough points.')})
    redemption = original or RewardRedemption(user=user)
    for field, value in {
        'program': program, 'points': points, 'target_account': target_account,
        'target_amount': target_amount, 'date': date, 'iof_amount': iof_amount,
        'iof_account': iof_account, 'iof_credit_card': iof_credit_card, 'notes': notes,
    }.items():
        setattr(redemption, field, value)
    redemption.full_clean()
    redemption.save()
    entry = redemption.loyalty_entry or LoyaltyEntry(user=user)
    for field, value in {
        'program': program, 'direction': LoyaltyEntry.Direction.DEBIT,
        'kind': LoyaltyEntry.Kind.REDEMPTION, 'amount': points, 'date': date, 'notes': notes,
    }.items():
        setattr(entry, field, value)
    entry.full_clean()
    entry.save()
    reward_movement, _ = BankMovement.objects.update_or_create(
        user=user, source_key=f'reward-redemption:{redemption.pk}:reward',
        defaults={'account': target_account, 'direction': BankMovement.Direction.CREDIT,
                  'kind': BankMovement.Kind.REWARD, 'amount': target_amount,
                  'effective_date': date, 'description': notes},
    )
    iof_movement = None
    old_iof_movement = redemption.iof_movement
    if iof_account is not None:
        iof_movement, _ = BankMovement.objects.update_or_create(
            user=user, source_key=f'reward-redemption:{redemption.pk}:iof',
            defaults={'account': iof_account, 'direction': BankMovement.Direction.DEBIT,
                      'kind': BankMovement.Kind.EXPENSE, 'amount': iof_amount,
                      'effective_date': date,
                      'description': gettext('IOF on reward redemption: %(notes)s') % {'notes': notes}},
        )
    redemption.loyalty_entry = entry
    redemption.reward_movement = reward_movement
    redemption.iof_movement = iof_movement
    redemption.save(update_fields=['loyalty_entry', 'reward_movement', 'iof_movement'])
    if old_iof_movement and iof_movement is None:
        old_iof_movement.delete()
    sync_redemption_iof_transaction(redemption)
    return redemption


def create_reward_redemption(**kwargs):
    return _save_reward_redemption(**kwargs)


def update_reward_redemption(*, redemption, **kwargs):
    return _save_reward_redemption(redemption=redemption, **kwargs)
