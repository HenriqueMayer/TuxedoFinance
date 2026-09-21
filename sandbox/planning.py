"""Read-only commitment snapshots and deterministic hypothetical yield."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import LoyaltyEntry, RewardRedemption
from banking.services import MissingExchangeRate, convert
from sandbox.services import money
from transactions.models import Transaction


ZERO = Decimal('0')
MAX_MONEY = Decimal('999999999999.99')
MAX_COMMITMENTS = 2000


def _check_snapshot_capacity(rows):
    if len(rows) >= MAX_COMMITMENTS:
        raise ValidationError(_('A snapshot supports at most %(limit)s commitments. Your previous snapshot has been kept.') % {'limit': MAX_COMMITMENTS})


def add_months(month, offset):
    year, index = divmod(month.year * 12 + month.month - 1 + offset, 12)
    return date(year, index + 1, 1)


def commitment_snapshot(user, start_month):
    """Expand economic sources once, by payment date; never synchronize a ledger.

    Amounts are a BRL planning snapshot at capture time. Missing FX is explicit;
    invoices are not added because their individual economic sources are here.
    """
    end = add_months(start_month, 12)
    captured = timezone.localdate()
    rows = []
    rates = {}

    def append(key, label, amount, currency, due, reference, instrument, kind, installment=''):
        if not start_month <= due < end:
            return
        _check_snapshot_capacity(rows)
        if currency not in rates:
            try:
                rates[currency] = convert(user, Decimal('1'), currency, 'BRL', as_of=captured)
            except MissingExchangeRate:
                rates[currency] = None
        converted = money(amount * rates[currency]) if rates[currency] is not None else None
        rows.append({
            'key': key, 'label': label, 'native_amount': str(amount), 'currency': currency,
            'amount': str(converted) if converted is not None else None,
            'payment_date': due.isoformat(), 'reference_month': reference.strftime('%Y-%m'),
            'instrument': instrument, 'kind': kind, 'installment': installment,
            'included': True, 'override': '',
        })

    transactions = Transaction.objects.filter(user=user, transaction_type='EXPENSE').select_related(
        'bank_account__bank', 'debit_card__account__bank', 'credit_card__account__bank',
    )
    for item in transactions:
        for offset in range(-1, 12):
            reference = add_months(start_month, offset)
            amount = item.amount_for_month(reference.year, reference.month)
            if not amount:
                continue
            if item.is_credit_card:
                due = item.credit_card.due_date_for(reference)
            elif item.is_fixed:
                due = reference.replace(day=min(item.date.day, monthrange(reference.year, reference.month)[1]))
            else:
                due = item.date
            installment = (
                f'{item.months_from_start(reference.year, reference.month) + 1}/{item.installments}'
                if item.is_installment_plan else ''
            )
            if item.is_installment_plan:
                identity = f'installment:{item.months_from_start(reference.year, reference.month) + 1}'
            elif item.is_fixed:
                occurrence = add_months(reference, -item.billing_offset)
                identity = f'recurring:{occurrence:%Y-%m}'
            else:
                identity = 'once'
            append(f'transaction:{item.pk}:{identity}', item.title, amount,
                   item.native_currency, due, reference, item.payment_label,
                   'installment' if item.is_installment_plan else 'recurring' if item.is_fixed else 'oneoff', installment)

    purchases = LoyaltyEntry.objects.filter(
        user=user, kind=LoyaltyEntry.Kind.PURCHASE, direction=LoyaltyEntry.Direction.CREDIT,
        cash_amount__gt=0,
    ).select_related('funding_account', 'funding_credit_card__account', 'program')
    for item in purchases:
        card = item.funding_credit_card
        account = item.funding_account or card.account
        reference = card.statement_month(item.date) if card else item.date.replace(day=1)
        due = card.due_date_for(reference) if card else item.date
        append(f'points:{item.pk}', _('Points purchase: %(name)s') % {'name': item.program.name},
               item.cash_amount, account.currency, due, reference, account.name, 'oneoff')
    redemptions = RewardRedemption.objects.filter(user=user, iof_amount__gt=0).select_related(
        'iof_account', 'iof_credit_card__account',
    )
    for item in redemptions:
        card = item.iof_credit_card
        account = item.iof_account or card.account
        reference = card.statement_month(item.date) if card else item.date.replace(day=1)
        due = card.due_date_for(reference) if card else item.date
        append(f'iof:{item.pk}', _('Redemption IOF'), item.iof_amount, account.currency,
               due, reference, account.name, 'oneoff')
    return {'user_id': user.pk, 'start_month': start_month.strftime('%Y-%m'), 'currency': 'BRL',
            'captured_at': timezone.now().isoformat(), 'rows': sorted(rows, key=lambda row: (row['payment_date'], row['key']))}


def merge_snapshot(previous, fresh):
    """Preview refreshed sources while retaining exclusions and manual overrides."""
    old = {row['key']: row for row in (previous or {}).get('rows', [])}
    keys = set()
    for row in fresh['rows']:
        keys.add(row['key'])
        before = old.get(row['key'])
        if before:
            row['included'] = before.get('included', True)
            row['override'] = before.get('override', '')
            row['changed'] = row['amount'] != before['amount'] or row['payment_date'] != before['payment_date']
        else:
            row['new'] = True
    for key, row in old.items():
        if key not in keys:
            _check_snapshot_capacity(fresh['rows'])
            fresh['rows'].append({**row, 'source_removed': True})
    fresh['rows'].sort(key=lambda row: (row['payment_date'], row['key']))
    return fresh


def snapshot_total(snapshot, month):
    total = ZERO
    for row in snapshot.get('rows', []):
        if row.get('included') and row['payment_date'].startswith(month):
            raw = row.get('override') or row['amount']
            if raw is None:
                raise ValidationError(_('A selected commitment has no exchange rate. Enter a BRL scenario amount or exclude it.'))
            try:
                value = Decimal(raw)
            except InvalidOperation:
                raise ValidationError(_('Enter a valid commitment amount.'))
            if not value.is_finite() or not ZERO <= value <= MAX_MONEY or value.as_tuple().exponent < -2:
                raise ValidationError(_('Commitment amounts must be nonnegative, finite amounts with at most two decimal places.'))
            total += value
    return money(total)


def simulate_yield(*, initial, start_month, months, rate, rate_period, contribution, withdrawal, overrides):
    rows = []
    balance = initial
    total_yield = total_contributions = total_withdrawals = ZERO
    with localcontext() as context:
        context.prec = 36
        monthly_rate = rate / 100
        if rate_period == 'annual':
            monthly_rate = (1 + monthly_rate) ** (Decimal(1) / 12) - 1
        for index in range(months):
            amount_in, amount_out = overrides.get(index, (contribution, withdrawal))
            gain = money(balance * monthly_rate)
            closing = money(balance + gain + amount_in - amount_out)
            if closing < ZERO:
                raise ValidationError(_('Month %(month)s: the withdrawal exceeds the available simulated balance.') % {'month': index + 1})
            if closing > MAX_MONEY:
                raise ValidationError(_('Month %(month)s: the simulated balance exceeds the supported amount.') % {'month': index + 1})
            rows.append({'month': add_months(start_month, index), 'opening': balance, 'yield': gain,
                         'contribution': amount_in, 'withdrawal': amount_out, 'closing': closing})
            balance = closing
            total_yield += gain
            total_contributions += amount_in
            total_withdrawals += amount_out
    return {'rows': rows, 'ending': balance, 'yield': total_yield, 'contributions': total_contributions,
            'capital': initial + total_contributions,
            'withdrawals': total_withdrawals, 'monthly_rate': monthly_rate * 100}
