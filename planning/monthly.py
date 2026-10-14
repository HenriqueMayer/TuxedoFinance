# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Monthly cash outlook, separating recorded cash from known commitments."""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.utils import timezone

from banking.services import ConversionContext, MissingExchangeRate, get_planning_availability
from dashboard.services import add_months, get_ledger_snapshot


ZERO = Decimal('0.00')


def monthly_outlook(user, month):
    today = timezone.localdate()
    end = date(month.year, month.month, monthrange(month.year, month.month)[1])
    cutoff = min(today, end)
    conversion = ConversionContext(user)
    recorded = get_planning_availability(user, cutoff, conversion=conversion)
    max_year, max_month = add_months(today.year, today.month, 11)
    supported = (month.year, month.month) <= (max_year, max_month)
    # An undated opening belongs only to its configured product/asset pair.
    unknown_openings = any(
        row['account'].opening_date is None and row['account'].opening_balance
        for row in recorded['account_rows']
    ) or any(
        row['asset'].opening_date is None and row['asset'].opening_balance
        and row['asset'].opening_product_id == row['product'].pk
        for row in recorded['cash_pots']
    )
    result = {'recorded': recorded, 'cutoff': cutoff, 'end': end, 'is_past': end < today,
              'supported': supported, 'base_currency': conversion.base_currency,
              'unknown_openings': unknown_openings}
    if not supported:
        return result
    projected = get_planning_availability(user, end, conversion=conversion)
    ledger = get_ledger_snapshot(user, end, conversion=conversion, projected=end >= today, forecast_from=cutoff)
    missing = set(projected['missing_currencies']) | set(recorded['missing_currencies'])
    accounts = {row['account'].pk: row for row in ledger['accounts']}
    available = sum((row['base_available'] or ZERO for row in projected['cash_pots']), ZERO)
    reserved = sum((row['base_reserved'] or ZERO for row in projected['cash_pots']), ZERO)
    unpaid = ZERO
    for row in projected['account_rows']:
        forecast = accounts[row['account'].pk]
        native = forecast['native_balance']
        # Reserve only real positive cash after obligations. An excluded account
        # still exposes debt; subtracting bills from an already-zero available
        # amount would otherwise invent a deficit backed by its reserved cash.
        reserve = min(row['reserved'], max(native, ZERO))
        row.update(balance=native, reserved=reserve, available=native - reserve)
        try:
            rate = conversion.convert(Decimal('1'), row['account'].currency, as_of=end)
        except MissingExchangeRate:
            missing.add(row['account'].currency)
            row.update(converted_balance=None, converted_available=None, converted_reserved=None)
        else:
            converted_balance = (native * rate).quantize(Decimal('0.01'))
            converted_reserved = (reserve * rate).quantize(Decimal('0.01'))
            # Match recorded availability's cent reconciliation instead of
            # independently rounding the difference into an artificial change.
            row.update(converted_balance=converted_balance, converted_reserved=converted_reserved,
                       converted_available=converted_balance - converted_reserved)
            available += row['converted_available']
            reserved += row['converted_reserved']
            unpaid += sum((item['converted_amount'] or ZERO for item in forecast['invoice_obligations']), ZERO)
    projected.update(available_total=available, reserved_total=reserved,
                     bank_total=sum((row['converted_balance'] or ZERO for row in projected['account_rows']), ZERO))
    # Past periods show recorded cash, not an unpaid-bill forecast. Absence of
    # that metric must not claim there were no historical invoice obligations.
    result.update(projected_available=available, projected_reserved=reserved,
                  unpaid_invoices=None if end < today else unpaid,
                  known_change=available - recorded['available_total'], complete=not missing,
                  missing_currencies=sorted(missing), projected=projected)
    return result
