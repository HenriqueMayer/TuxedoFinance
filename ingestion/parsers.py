# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bounded local statement parsing. Mapping and numeric conventions are explicit."""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape
import io
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 500
CENT = Decimal('0.01')


def _text(blob, encoding='utf-8-sig'):
    if len(blob) > MAX_BYTES:
        raise ValidationError(_('The statement must be no larger than 2 MiB.'))
    try:
        value = blob.decode(encoding)
    except (UnicodeError, LookupError):
        raise ValidationError(_('The file encoding is invalid. Choose UTF-8 or Windows-1252.'))
    if '\x00' in value:
        raise ValidationError(_('The file contains invalid null characters.'))
    return value


def inspect_csv(blob, encoding='utf-8-sig'):
    value = _text(blob, encoding)
    try:
        dialect = csv.Sniffer().sniff(value[:8192], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    try:
        reader = csv.reader(io.StringIO(value), dialect)
        headers = next(reader)
        if not headers or len(headers) > 40 or any(not header.strip() for header in headers) or len(set(headers)) != len(headers):
            raise ValidationError(_('Use unique, nonempty CSV column names (at most 40).'))
        # A billed-month report contains occurrences, not bank-statement cash.
        # Rejecting it prevents duplicate purchases and installment expansion.
        if {'billed_month', 'total_amount', 'payment_channel'}.issubset(headers):
            raise ValidationError(_('This is a Tuxedo transaction report, not a bank statement. Import a statement with signed cash amounts instead.'))
        rows = []
        for index, cells in enumerate(reader, 2):
            if not cells or not any(cells):
                continue
            if len(cells) != len(headers):
                raise ValidationError(_('CSV row %(row)s has a different number of columns.') % {'row': index})
            if len(rows) >= MAX_ROWS:
                raise ValidationError(_('Import at most 500 entries per statement.'))
            rows.append(dict(zip(headers, cells)))
    except (csv.Error, StopIteration):
        raise ValidationError(_('The CSV file is empty or malformed.'))
    if not rows:
        raise ValidationError(_('The statement contains no entries.'))
    return {'headers': headers, 'rows': rows, 'delimiter': dialect.delimiter}


def _amount(raw, decimal_mark):
    raw = str(raw).strip()
    if not raw:
        return Decimal('0.00')
    if len(raw) > 40:
        raise ValidationError(_('The numeric amount is too long.'))
    thousands = ',' if decimal_mark == '.' else '.'
    if decimal_mark not in {'.', ','}:
        raise ValidationError(_('Choose the decimal convention explicitly.'))
    pattern = r'[+-]?(?:\d+|\d{1,3}(?:' + re.escape(thousands) + r'\d{3})+)(?:' + re.escape(decimal_mark) + r'\d+)?'
    if not re.fullmatch(pattern, raw):
        raise ValidationError(_('Invalid numeric amount. Currency symbols and ambiguous separators are not accepted.'))
    try:
        value = Decimal(raw.replace(thousands, '').replace(decimal_mark, '.'))
    except InvalidOperation:
        raise ValidationError(_('Invalid numeric amount.'))
    if not value.is_finite() or abs(value) >= Decimal('100000000000000') or value.quantize(CENT) != value:
        raise ValidationError(_('Use a finite cash amount with at most two decimal places.'))
    return value.quantize(CENT)


def parse_csv(blob, *, date_column, description_column, amount_column='', debit_column='', credit_column='', id_column='', currency_column='', date_format='%Y-%m-%d', decimal_mark='.', encoding='utf-8-sig'):
    inspected = inspect_csv(blob, encoding)
    headers = inspected['headers']
    selected = [date_column, description_column] + ([amount_column] if amount_column else [debit_column, credit_column])
    selected += [column for column in (id_column, currency_column) if column]
    if any(column not in headers for column in selected):
        raise ValidationError(_('Select valid date, description and amount columns.'))
    if date_format not in {'%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'}:
        raise ValidationError(_('Choose a supported date format.'))
    result = []
    for index, raw in enumerate(inspected['rows'], 2):
        try:
            day = datetime.strptime(raw[date_column].strip(), date_format).date()
            if amount_column:
                amount = _amount(raw[amount_column], decimal_mark)
            else:
                debit = _amount(raw[debit_column], decimal_mark)
                credit = _amount(raw[credit_column], decimal_mark)
                if debit < 0 or credit < 0 or (debit and credit):
                    raise ValidationError(_('Separate debit and credit columns must be nonnegative, with only one filled per row.'))
                amount = credit - debit
            if not amount:
                raise ValidationError(_('A cash entry must have a nonzero amount.'))
            external_id = raw[id_column].strip() if id_column else ''
            description = raw[description_column].strip()
            if len(external_id) > 255 or not description or len(description) > 1000:
                raise ValidationError(_('Use a description up to 1000 characters and an identifier up to 255.'))
            result.append({'date': day.isoformat(), 'amount': str(amount), 'description': description,
                           'external_id': external_id, 'currency': raw[currency_column].strip().upper() if currency_column else '', 'raw': raw})
        except (ValueError, ValidationError) as error:
            detail = '; '.join(error.messages) if isinstance(error, ValidationError) else _('Invalid date for the selected format.')
            raise ValidationError(_('CSV row %(row)s: %(detail)s') % {'row': index, 'detail': detail})
    return result


def parse_ofx(blob, encoding='utf-8-sig'):
    value = _text(blob, encoding)
    if re.search(r'<!DOCTYPE|<!ENTITY', value, flags=re.I):
        raise ValidationError(_('OFX entity declarations are not supported.'))
    blocks = re.findall(r'<STMTTRN\s*>(.*?)</STMTTRN\s*>', value, flags=re.I | re.S)
    if not blocks or len(blocks) != len(re.findall(r'<STMTTRN\s*>', value, flags=re.I)):
        raise ValidationError(_('The OFX statement contains no complete transaction records.'))
    if len(blocks) > MAX_ROWS:
        raise ValidationError(_('Import at most 500 entries per statement.'))

    def tag(block, name, required=False):
        matches = re.findall(r'<' + name + r'\s*>\s*([^<\r\n]*)', block, flags=re.I)
        if len(matches) > 1 or (required and not matches):
            raise ValidationError(_('The OFX statement has missing or repeated required fields.'))
        return unescape(matches[0].strip()) if matches else ''

    currency = tag(value, 'CURDEF', required=True).upper()
    result = []
    for index, block in enumerate(blocks, 1):
        try:
            raw_date = tag(block, 'DTPOSTED', required=True)
            day = datetime.strptime(raw_date[:8], '%Y%m%d').date()
            amount = _amount(tag(block, 'TRNAMT', required=True), '.')
            if not amount:
                raise ValidationError(_('A cash entry must have a nonzero amount.'))
            external_id = tag(block, 'FITID', required=True)
            description = tag(block, 'MEMO') or tag(block, 'NAME') or tag(block, 'TRNTYPE', required=True)
            if not external_id or len(external_id) > 255 or len(description) > 1000:
                raise ValidationError(_('The OFX identifier or description is invalid.'))
            result.append({'date': day.isoformat(), 'amount': str(amount), 'description': description,
                           'external_id': external_id, 'currency': currency,
                           'raw': {'DTPOSTED': raw_date, 'TRNAMT': str(amount), 'FITID': external_id, 'description': description}})
        except (ValueError, ValidationError) as error:
            detail = '; '.join(error.messages) if isinstance(error, ValidationError) else _('Invalid OFX posting date.')
            raise ValidationError(_('OFX entry %(row)s: %(detail)s') % {'row': index, 'detail': detail})
    balance_block = re.search(r'<LEDGERBAL\s*>(.*?)</LEDGERBAL\s*>', value, flags=re.I | re.S)
    balance = balance_date = None
    if balance_block:
        balance = str(_amount(tag(balance_block.group(1), 'BALAMT', required=True), '.'))
        try:
            balance_date = datetime.strptime(tag(balance_block.group(1), 'DTASOF', required=True)[:8], '%Y%m%d').date().isoformat()
        except ValueError:
            raise ValidationError(_('The OFX closing balance date is invalid.'))
    return {'rows': result, 'currency': currency, 'account_hint': tag(value, 'ACCTID')[-4:], 'closing_balance': balance, 'closing_date': balance_date}
