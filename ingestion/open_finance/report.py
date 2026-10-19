# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Minimized provider observations, deliberately separate from the local ledger."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from uuid import UUID

from .client import PilotError


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise PilotError('invalid_identifier') from None


def instant(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except ValueError:
        return None


def calendar_date(value):
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except ValueError:
        return None


def amount(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise PilotError('invalid_amount')
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise PilotError('invalid_amount') from None
    if (not number.is_finite() or len(str(value)) > 80
            or not -16 <= number.as_tuple().exponent <= 16
            or number.copy_abs() > Decimal('1e16')):
        raise PilotError('invalid_amount')
    # Retain reported precision. This probe must not round or recompute finances.
    return format(number, 'f')


def text(value, limit=240):
    if value is None:
        return None
    if not isinstance(value, str):
        raise PilotError('invalid_payload')
    return ''.join(character for character in value if character.isprintable())[:limit]


def currency(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch('[A-Z]{3}', value):
        raise PilotError('invalid_currency')
    return value


def installment_count(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1200:
        raise PilotError('invalid_installment')
    return value


def check_item(item, item_id, now):
    if not isinstance(item, dict) or identifier(item.get('id')) != identifier(item_id):
        raise PilotError('foreign_item')
    connector = item.get('connector')
    if not isinstance(connector, dict) or connector.get('id') != 200 or connector.get('name') != 'MeuPluggy':
        raise PilotError('not_personal_proxy')
    # The proxy's connector is NOT Inter 823. Its original bank is not documented
    # here, so provenance remains the operator's explicit Dashboard attestation.
    expiry = instant(item.get('consentExpiresAt'))
    if expiry is None:
        raise PilotError('authorization_expiry_unknown')
    if expiry <= now:
        raise PilotError('authorization_expired')
    if item.get('status') != 'UPDATED' or item.get('error'):
        raise PilotError('item_not_ready')


def closed_bills(bills, today):
    result = []
    for bill in bills:
        identifier(bill.get('id'))
        closing = calendar_date(bill.get('billClosingDate'))
        due = calendar_date(bill.get('dueDate'))
        if closing is not None and due is not None and closing <= today and closing <= due:
            result.append(bill)
    return sorted(result, key=lambda row: (calendar_date(row['billClosingDate']), identifier(row['id'])), reverse=True)


def rows(value):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 200 or any(not isinstance(row, dict) for row in value):
        raise PilotError('invalid_payload')
    return value


def build_report(*, item, account, bill, transactions, now, today, mode, window=None,
                 requested_card_id=None, requested_bill_id=None):
    item_id = identifier(item['id'])
    card_id = identifier(account['id'])
    bill_id = identifier(bill['id'])
    if identifier(account.get('itemId')) != item_id or account.get('type') != 'CREDIT' or account.get('subtype') != 'CREDIT_CARD':
        raise PilotError('foreign_account')
    if bill_id not in {identifier(row['id']) for row in closed_bills([bill], today)}:
        raise PilotError('closed_bill_unavailable')
    warnings = ['inter_origin_operator_attested', 'bank_resource_collection_time_unverified',
                'reported_payments_do_not_establish_bill_paid', 'no_ledger_changes',
                'not_an_official_pdf', 'bill_completeness_requires_statement_comparison']
    if item.get('executionStatus') != 'SUCCESS':
        warnings.append('provider_partial_or_unknown_execution')
    updated = instant(item.get('lastUpdatedAt'))
    if updated is None or now - updated > timedelta(hours=24) or updated > now:
        warnings.append('proxy_update_missing_stale_or_future')
    total = amount(bill.get('totalAmount'))
    native_currency = currency(bill.get('totalAmountCurrencyCode'))
    if total is None or native_currency is None:
        warnings.append('bill_total_or_currency_missing')
    charges = rows(bill.get('financeCharges'))
    payments = rows(bill.get('payments'))
    if charges is None or payments is None:
        warnings.append('charges_or_payments_missing')
    included = []
    unlinked = 0
    if transactions is None:
        warnings.append('transactions_not_requested')
    else:
        warnings.append('bounded_transaction_window_not_complete_history')
        for transaction in transactions:
            if identifier(transaction.get('accountId')) != card_id:
                raise PilotError('foreign_account')
            metadata = transaction.get('creditCardMetadata') or {}
            if not isinstance(metadata, dict):
                raise PilotError('invalid_payload')
            associated = metadata.get('billId')
            if not associated:
                unlinked += 1
                continue
            if identifier(associated) != bill_id:
                continue
            included.append({
                'id': identifier(transaction['id']), 'date': text(transaction.get('date'), 40),
                'description': text(transaction.get('description')),
                'amount': amount(transaction.get('amount')),
                'currency': currency(transaction.get('currencyCode')),
                'status': text(transaction.get('status'), 30),
                'installment_number': installment_count(metadata.get('installmentNumber')),
                'total_installments': installment_count(metadata.get('totalInstallments')),
                'bill_id': bill_id,
            })
        if unlinked:
            warnings.append('unassigned_transactions_not_guessed')
    return {
        'schema': 'tuxedo-inter-bill-pilot-v1', 'mode': mode,
        'retrieved_at': now.astimezone(timezone.utc).isoformat(), 'financial_cutoff': today.isoformat(),
        'provider': 'meu_pluggy', 'item_id': item_id, 'account_id': card_id,
        'request_selection': {
            'card_id': identifier(requested_card_id) if requested_card_id else None,
            'bill_id': identifier(requested_bill_id) if requested_bill_id else None,
        },
        'source': {'bank': 'Inter PF Open Finance', 'verified_by': 'operator_attestation',
                   'proxy_connector_id': 200},
        'provider_cadence_hours': 24,
        'proxy_item_updated_at': updated.isoformat() if updated else None,
        'bank_resource_collected_at': None,
        'authorization_expires_at': item['consentExpiresAt'],
        'execution_status': text(item.get('executionStatus'), 40),
        'bill': {
            'id': bill_id, 'closing_date': calendar_date(bill['billClosingDate']).isoformat(),
            'due_date': calendar_date(bill['dueDate']).isoformat(),
            'total': total, 'currency': native_currency,
            'minimum_payment': amount(bill.get('minimumPaymentAmount')),
            'charges': None if charges is None else [
                {'type': text(row.get('type'), 60), 'amount': amount(row.get('amount')),
                 'currency': currency(row.get('currencyCode'))} for row in charges],
            # Payments can be recorded in a following cycle. Do not assign them
            # to a local invoice or derive PAID from this observation.
            'payments_reported_on_bill': None if payments is None else [
                {'value_type': text(row.get('valueType'), 60), 'date': text(row.get('paymentDate'), 40),
                 'mode': text(row.get('paymentMode'), 40), 'amount': amount(row.get('amount')),
                 'currency': currency(row.get('currencyCode'))} for row in payments],
        },
        'transaction_window': window, 'linked_transactions': included,
        'unassigned_transactions_in_window': unlinked,
        'warnings': warnings, 'financial_writes': False,
    }


def reusable(report, *, mode, item_id, card_id=None, bill_id=None, include_transactions=False, lookback_days=90, now):
    if not isinstance(report, dict) or report.get('schema') != 'tuxedo-inter-bill-pilot-v1' or report.get('mode') != mode:
        return False
    bill = report.get('bill')
    if (not isinstance(bill, dict)
            or not isinstance(report.get('linked_transactions'), list)
            or not isinstance(report.get('warnings'), list)
            or report.get('financial_writes') is not False):
        return False
    # Private files can still be incomplete or manually edited. A fresh timestamp
    # alone must never turn missing source/bill identity into a valid observation.
    if report.get('provider') != 'meu_pluggy' or report.get('source') != {
        'bank': 'Inter PF Open Finance', 'verified_by': 'operator_attestation',
        'proxy_connector_id': 200,
    }:
        return False
    try:
        if (identifier(report.get('account_id')) != report.get('account_id')
                or identifier(bill.get('id')) != bill.get('id')):
            return False
    except PilotError:
        return False
    closing = calendar_date(bill.get('closing_date'))
    due = calendar_date(bill.get('due_date'))
    cutoff = calendar_date(report.get('financial_cutoff'))
    if not (closing and due and cutoff and closing <= cutoff <= now.date() + timedelta(days=1) and closing <= due):
        return False
    if report.get('item_id') != item_id or (card_id and report.get('account_id') != card_id):
        return False
    # Automatic selection must not silently reuse an earlier explicit old bill
    # or bypass the need to choose among several cards, even for the same item.
    if report.get('request_selection') != {'card_id': card_id, 'bill_id': bill_id}:
        return False
    if bill_id and bill.get('id') != bill_id:
        return False
    window = report.get('transaction_window')
    if window is not None and not isinstance(window, dict):
        return False
    if bool(window) != include_transactions or (window and window.get('lookback_days') != lookback_days):
        return False
    if window and (calendar_date(window.get('to')) != cutoff
                   or calendar_date(window.get('from')) != cutoff - timedelta(days=lookback_days)):
        return False
    retrieved = instant(report.get('retrieved_at'))
    expiry = instant(report.get('authorization_expires_at'))
    return bool(retrieved and expiry and retrieved <= now < retrieved + timedelta(hours=24) and now < expiry)
