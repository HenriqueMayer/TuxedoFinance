# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Review locally, post atomically and undo only unchanged imported sources."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.models import BankAccount, BankMovement, BankTransfer, CardInvoice, InvoicePayment
from banking.services import account_balance, create_transfer
from banking.settlements import delete_invoice_payment, save_invoice_payment
from categories.models import Category
from ingestion.models import ExternalStatementIdentity, ImportBatch, ImportedRow
from ingestion.parsers import MAX_BYTES, MAX_ROWS, inspect_csv, parse_csv, parse_ofx
from transactions.models import Transaction
from transactions.services import sync_user_ledger

ZERO = Decimal('0.00')
DECISION_FIELDS = ('action', 'category_id', 'matched_movement_id', 'invoice_id', 'counterparty_account_id', 'counterparty_amount')


def _account(user, account_id, *, lock=False):
    queryset = BankAccount.objects.filter(user=user)
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=account_id)
    except BankAccount.DoesNotExist:
        raise ValidationError(_('Choose an account that belongs to you.'))


def _baseline(account, day, *, require_known=False):
    if account.opening_date and day < account.opening_date:
        raise ValidationError(_('The statement entry precedes this account opening balance date.'))
    if require_known and account.opening_balance and account.opening_date is None:
        raise ValidationError(_('Review and date the existing opening balance in account settings before confirming this statement. No opening date or balance will be inferred.'))


def _validate_parsed(account, rows):
    if not rows or len(rows) > MAX_ROWS:
        raise ValidationError(_('Import between 1 and 500 entries.'))
    for row in rows:
        if row['currency'] and row['currency'] != account.currency:
            raise ValidationError(_('The statement currency does not match the selected account.'))
        _baseline(account, date.fromisoformat(row['date']))


def _populate(batch, rows):
    _validate_parsed(batch.account, rows)
    batch.rows.all().delete()
    ImportedRow.objects.bulk_create([
        ImportedRow(batch=batch, number=index, date=date.fromisoformat(row['date']), amount=Decimal(row['amount']),
                    description=row['description'], currency=row['currency'] or batch.account.currency,
                    external_id=row['external_id'], raw=row['raw'])
        for index, row in enumerate(rows, 1)
    ])


@transaction.atomic
def stage_statement(user, account_id, blob, file_name, file_format, encoding='utf-8-sig', *, closing_balance=None, closing_date=None):
    """Staging stores bounded evidence; it never creates financial records."""
    account = _account(user, account_id, lock=True)
    if encoding not in ('utf-8-sig', 'cp1252') or file_format not in ('CSV', 'OFX'):
        raise ValidationError(_('Choose CSV or OFX and a supported encoding.'))
    if len(blob) > MAX_BYTES:
        raise ValidationError(_('The statement must be no larger than 2 MiB.'))
    file_hash = sha256(blob).hexdigest()
    existing = ImportBatch.objects.filter(user=user, account=account, file_hash=file_hash).exclude(status='UNDONE').first()
    if existing:
        return existing, False
    parsed = inspect_csv(blob, encoding) if file_format == 'CSV' else parse_ofx(blob, encoding)
    if file_format == 'OFX' and parsed['currency'] != account.currency:
        raise ValidationError(_('The statement currency does not match the selected account.'))
    if bool(closing_balance is not None) != bool(closing_date is not None):
        raise ValidationError(_('Enter both the closing balance and its date.'))
    batch = ImportBatch.objects.create(
        user=user, account=account, file_name=Path(file_name).name[:255], file_hash=file_hash,
        file_format=file_format, encoding=encoding, raw_text=blob.decode(encoding),
        headers=parsed['headers'] if file_format == 'CSV' else [],
        metadata={'account_hint': parsed['account_hint']} if file_format == 'OFX' else {'delimiter': parsed['delimiter']},
        closing_balance=closing_balance if closing_balance is not None else parsed.get('closing_balance'),
        closing_date=closing_date if closing_date is not None else parsed.get('closing_date'),
        status='STAGED' if file_format == 'CSV' else 'READY',
    )
    if file_format == 'OFX':
        _populate(batch, parsed['rows'])
    return batch, True


@transaction.atomic
def map_csv_batch(user, batch_id, mapping):
    batch = ImportBatch.objects.select_for_update().select_related('account').get(pk=batch_id, user=user)
    if batch.file_format != 'CSV' or batch.status not in ('STAGED', 'READY'):
        raise ValidationError(_('Only an unconfirmed CSV statement can change its mapping.'))
    rows = parse_csv(batch.raw_text.encode(batch.encoding), encoding=batch.encoding, **mapping)
    _populate(batch, rows)
    batch.mapping = mapping
    batch.status = 'READY'
    batch.save(update_fields=['mapping', 'status', 'updated_at'])
    return batch


def exact_movement_candidates(row):
    direction = 'CREDIT' if row.amount > ZERO else 'DEBIT'
    return BankMovement.objects.filter(user_id=row.batch.user_id, account_id=row.batch.account_id,
        effective_date=row.date, amount=abs(row.amount), direction=direction).select_related('account')


def row_suggestions(row):
    """A weak description/date/amount resemblance never confirms a duplicate."""
    duplicate = None
    if row.external_id:
        duplicate = ExternalStatementIdentity.objects.filter(user_id=row.batch.user_id,
            account_id=row.batch.account_id, external_id=row.external_id).select_related('row__batch').first()
    candidates = list(exact_movement_candidates(row))
    return {'strong_duplicate': duplicate, 'matches': candidates,
            'weak_duplicate': any(item.description.casefold().strip() == row.description.casefold().strip() for item in candidates)}


def _related(model, user_id, pk, message):
    if not pk:
        raise ValidationError(message)
    try:
        return model.objects.get(user_id=user_id, pk=pk)
    except model.DoesNotExist:
        raise ValidationError(message)


def validate_decision(row):
    account, user_id = row.batch.account, row.batch.user_id
    if row.action not in ImportedRow.Action.values:
        raise ValidationError(_('Choose an action for every entry, including entries to skip.'))
    if row.action == 'SKIP':
        return
    _baseline(account, row.date, require_known=True)
    if row.currency != account.currency:
        raise ValidationError(_('The account currency changed after staging. Upload the statement for the correct account.'))
    if row.date > timezone.localdate():
        raise ValidationError(_('Statement cash entries cannot be dated in the future.'))
    if row.external_id and ExternalStatementIdentity.objects.filter(
        user_id=user_id, account=account, external_id=row.external_id,
    ).exclude(row=row).exists():
        raise ValidationError(_('This bank identifier was already confirmed. Review the previous import and choose Skip for this entry.'))
    if row.action == 'CREATE':
        category = _related(Category, user_id, row.category_id, _('Choose an owned category for the new entry.'))
        kind = 'INCOME' if row.amount > ZERO else 'EXPENSE'
        if category.transaction_type and category.transaction_type != kind:
            raise ValidationError(_('Choose a category compatible with the statement amount direction.'))
        operation = Transaction(user_id=user_id, title=row.description[:150], amount=abs(row.amount),
            transaction_type=kind, category=category, payment_channel='ACCOUNT', bank_account=account,
            date=row.date, notes=row.description)
        operation.full_clean()
    elif row.action == 'MATCH':
        if not exact_movement_candidates(row).filter(pk=row.matched_movement_id).exists():
            raise ValidationError(_('Choose an existing movement with the same account, date, direction and amount.'))
    elif row.action == 'PAY_INVOICE':
        if row.amount >= ZERO:
            raise ValidationError(_('An invoice payment must be a debit.'))
        invoice = _related(CardInvoice, user_id, row.invoice_id, _('Choose an owned manual invoice.'))
        payment = InvoicePayment(user_id=user_id, invoice=invoice, account=account, amount=abs(row.amount), date=row.date, notes=row.description)
        payment.full_clean()
    elif row.action == 'TRANSFER':
        counterparty = _account(row.batch.user, row.counterparty_account_id)
        _baseline(counterparty, row.date, require_known=True)
        if counterparty.pk == account.pk or not row.counterparty_amount or row.counterparty_amount <= ZERO:
            raise ValidationError(_('Choose another owned account and enter its actual positive amount.'))
        source, destination = (account, counterparty) if row.amount < ZERO else (counterparty, account)
        source_amount, destination_amount = (abs(row.amount), row.counterparty_amount) if row.amount < ZERO else (row.counterparty_amount, row.amount)
        BankTransfer(user_id=user_id, source_account=source, destination_account=destination,
            source_amount=source_amount, destination_amount=destination_amount, date=row.date, notes=row.description).full_clean()


def decision_digest(batch):
    values = list(batch.rows.order_by('number').values('pk', 'date', 'amount', 'description', 'currency', 'external_id', *DECISION_FIELDS))
    payload = {'account': batch.account_id, 'mapping': batch.mapping, 'closing_balance': batch.closing_balance, 'closing_date': batch.closing_date, 'rows': values}
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


@transaction.atomic
def save_review(user, batch_id, decisions):
    batch = ImportBatch.objects.select_for_update().select_related('account', 'user').get(user=user, pk=batch_id)
    if batch.status != 'READY':
        raise ValidationError(_('Only an unconfirmed mapped statement can be reviewed.'))
    rows = list(batch.rows.select_for_update())
    if set(decisions) != {row.pk for row in rows}:
        raise ValidationError(_('Review all statement entries.'))
    for row in rows:
        for field in DECISION_FIELDS:
            setattr(row, field, decisions[row.pk].get(field))
        validate_decision(row)
        row.save(update_fields=list(DECISION_FIELDS))
    batch.save(update_fields=['updated_at'])
    return batch


def _json_value(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def source_snapshot(row):
    """All source fields and linked cash evidence, including category splits."""
    if row.action == 'CREATE':
        operation = Transaction.objects.filter(pk=row.created_transaction_id, user_id=row.batch.user_id).values().first()
        if operation is None:
            return None
        return _json_value({'transaction': operation,
            'splits': list(Transaction.objects.get(pk=operation['id']).splits.order_by('pk').values()),
            'movements': list(BankMovement.objects.filter(user_id=row.batch.user_id, source_key__startswith=f"transaction:{operation['id']}:").order_by('pk').values())})
    if row.action == 'PAY_INVOICE':
        payment = InvoicePayment.objects.filter(pk=row.created_payment_id, user_id=row.batch.user_id).values().first()
        if payment is None:
            return None
        return _json_value({'payment': payment, 'movement': BankMovement.objects.filter(pk=payment['movement_id']).values().first()})
    if row.action == 'TRANSFER':
        transfer = BankTransfer.objects.filter(pk=row.created_transfer_id, user_id=row.batch.user_id).values().first()
        if transfer is None:
            return None
        return _json_value({'transfer': transfer,
            'movements': list(BankMovement.objects.filter(transfer_id=transfer['id']).order_by('pk').values())})
    return {}


def reconciliation(batch):
    if batch.closing_balance is None or batch.closing_date is None:
        return None
    actual = account_balance(batch.account, batch.closing_date)
    return {'date': batch.closing_date.isoformat(), 'expected': str(batch.closing_balance),
            'actual': str(actual), 'difference': str(actual - batch.closing_balance)}


@transaction.atomic
def confirm_batch(user, batch_id, expected_digest):
    batch = ImportBatch.objects.select_for_update().select_related('account', 'user').get(pk=batch_id, user=user)
    if batch.status == 'CONFIRMED':
        return batch
    if batch.status != 'READY' or decision_digest(batch) != expected_digest:
        raise ValidationError(_('The review changed. Reload and inspect it before confirming.'))
    batch.account = _account(user, batch.account_id, lock=True)
    rows = list(batch.rows.select_for_update())
    identifiers, matches = set(), set()
    for row in rows:
        row.batch = batch
        validate_decision(row)
        if row.action == 'SKIP':
            continue
        if row.external_id:
            if row.external_id in identifiers:
                raise ValidationError(_('The same bank identifier occurs more than once in this statement. Choose Skip for the duplicate.'))
            identifiers.add(row.external_id)
        if row.action == 'MATCH':
            if row.matched_movement_id in matches:
                raise ValidationError(_('One cash movement cannot represent two entries in the same statement.'))
            matches.add(row.matched_movement_id)
    for row in rows:
        if row.action == 'SKIP':
            continue
        if row.action == 'CREATE':
            row.created_transaction = Transaction.objects.create(user=user, title=row.description[:150],
                amount=abs(row.amount), transaction_type='INCOME' if row.amount > ZERO else 'EXPENSE',
                category_id=row.category_id, payment_channel='ACCOUNT', bank_account=batch.account,
                date=row.date, notes=row.description)
        elif row.action == 'PAY_INVOICE':
            row.created_payment = save_invoice_payment(InvoicePayment(user=user, invoice_id=row.invoice_id,
                account=batch.account, amount=abs(row.amount), date=row.date, notes=row.description))
        elif row.action == 'TRANSFER':
            counterparty = _account(user, row.counterparty_account_id)
            source, destination = (batch.account, counterparty) if row.amount < ZERO else (counterparty, batch.account)
            source_amount, destination_amount = (abs(row.amount), row.counterparty_amount) if row.amount < ZERO else (row.counterparty_amount, row.amount)
            row.created_transfer = create_transfer(user=user, source_account=source, destination_account=destination,
                source_amount=source_amount, destination_amount=destination_amount, date=row.date, notes=row.description)
        if row.external_id:
            ExternalStatementIdentity.objects.create(user=user, account=batch.account, external_id=row.external_id, row=row)
        row.save(update_fields=['created_transaction', 'created_payment', 'created_transfer'])
    # Exactly one reconciliation after all ordinary sources; invoice payments
    # and transfers retain their own captured evidence and neutral semantics.
    sync_user_ledger(user)
    for row in rows:
        row.created_snapshot = source_snapshot(row)
        row.save(update_fields=['created_snapshot'])
    batch.status = 'CONFIRMED'
    batch.confirmed_at = timezone.now()
    batch.reconciliation_at_confirmation = reconciliation(batch) or {}
    batch.save(update_fields=['status', 'confirmed_at', 'reconciliation_at_confirmation', 'updated_at'])
    return batch


@transaction.atomic
def undo_batch(user, batch_id):
    batch = ImportBatch.objects.select_for_update().select_related('user', 'account').get(pk=batch_id, user=user)
    if batch.status == 'UNDONE':
        return batch
    if batch.status != 'CONFIRMED':
        raise ValidationError(_('Only a confirmed import can be undone.'))
    rows = list(batch.rows.select_for_update())
    for row in rows:
        row.batch = batch
        if source_snapshot(row) != row.created_snapshot:
            raise ValidationError(_('An imported source was edited or removed. Undo is refused to preserve those changes.'))
        movement_ids = [value['id'] for value in row.created_snapshot.get('movements', [])]
        if row.created_snapshot.get('movement'):
            movement_ids.append(row.created_snapshot['movement']['id'])
        if ImportedRow.objects.filter(matched_movement_id__in=movement_ids, batch__status='CONFIRMED').exclude(batch=batch).exists():
            raise ValidationError(_('Another confirmed statement uses this cash evidence. Review that import before undoing this one.'))
    for row in rows:
        if row.created_transaction_id:
            Transaction.objects.get(pk=row.created_transaction_id, user=user).delete()
        elif row.created_payment_id:
            delete_invoice_payment(InvoicePayment.objects.get(pk=row.created_payment_id, user=user))
        elif row.created_transfer_id:
            BankMovement.objects.filter(transfer_id=row.created_transfer_id, user=user).delete()
            BankTransfer.objects.get(pk=row.created_transfer_id, user=user).delete()
    sync_user_ledger(user)
    ExternalStatementIdentity.objects.filter(row__batch=batch).delete()
    batch.status = 'UNDONE'
    batch.undone_at = timezone.now()
    batch.save(update_fields=['status', 'undone_at', 'updated_at'])
    return batch
