# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Local evidence, deliberate posting and whole-batch undo safety."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, BankTransfer, CardInvoice, CreditCard, InvoicePayment
from banking.services import account_balance
from categories.models import Category
from ingestion.models import ExternalStatementIdentity, ImportBatch, ImportedRow
from ingestion.services import confirm_batch, decision_digest, map_csv_batch, reconciliation, row_suggestions, save_review, stage_statement, undo_batch
from transactions.models import Transaction, TransactionSplit
from transactions.services import sync_user_ledger

MAPPING = {'date_column':'Date', 'description_column':'Text', 'amount_column':'Amount', 'debit_column':'', 'credit_column':'', 'id_column':'Id', 'currency_column':'', 'date_format':'%Y-%m-%d', 'decimal_mark':'.'}


# Exercise dormant workflows explicitly; default gates are tested in pages.
@override_settings(REVIEWED_FEATURES={'imports'})
class StatementImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('statement-owner')
        self.other = get_user_model().objects.create_user('statement-other')
        self.bank = Bank.objects.create(user=self.user, name='Statement bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Statement account', currency='BRL', opening_balance=Decimal('1000'), opening_date=date(2026, 1, 1))
        self.category = Category.objects.create(user=self.user, name='Statement expenses', transaction_type='EXPENSE')
        self.income = Category.objects.create(user=self.user, name='Statement income', transaction_type='INCOME')
        self.client.force_login(self.user)

    def staged(self, lines='2026-09-01,Coffee,-25.00,entry1\n', **kwargs):
        blob = ('Date,Text,Amount,Id\n' + lines).encode()
        batch, _ = stage_statement(self.user, self.account.pk, blob, 'local.csv', 'CSV', **kwargs)
        map_csv_batch(self.user, batch.pk, MAPPING)
        batch.refresh_from_db()
        return batch

    def decisions(self, batch, action='CREATE', **overrides):
        return {row.pk: {'action':action, 'category_id':self.income.pk if row.amount > 0 else self.category.pk,
            'matched_movement_id':None, 'invoice_id':None, 'counterparty_account_id':None, 'counterparty_amount':None, **overrides}
            for row in batch.rows.all()}

    def confirm(self, batch, decisions=None):
        save_review(self.user, batch.pk, decisions or self.decisions(batch))
        batch.refresh_from_db()
        return confirm_batch(self.user, batch.pk, decision_digest(batch))

    def ofx(self, amount='-25', fitid='ofx1', currency='BRL'):
        return f'<OFX><CURDEF>{currency}\n<ACCTID>12345\n<STMTTRN><DTPOSTED>20260901\n<TRNAMT>{amount}\n<FITID>{fitid}\n<MEMO>Coffee\n</STMTTRN></OFX>'.encode()

    def test_stage_map_preserve_raw_hash_and_do_not_post(self):
        blob = b'Date,Text,Amount,Id\n2026-09-01,Coffee,-25.00,entry1\n'
        batch, created = stage_statement(self.user, self.account.pk, blob, 'local.csv', 'CSV')
        self.assertTrue(created)
        self.assertEqual(batch.file_hash, sha256(blob).hexdigest())
        self.assertEqual(batch.raw_text, blob.decode())
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (0,0))
        map_csv_batch(self.user, batch.pk, MAPPING)
        self.assertEqual(batch.rows.get().raw['Amount'], '-25.00')
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (0,0))
        repeated, created = stage_statement(self.user, self.account.pk, blob, 'renamed.csv', 'CSV')
        self.assertFalse(created)
        self.assertEqual(repeated.pk, batch.pk)

    def test_confirm_once_reconcile_and_retry_do_not_create_adjustment(self):
        batch = self.staged(closing_balance=Decimal('970'), closing_date=date(2026,9,1))
        save_review(self.user, batch.pk, self.decisions(batch))
        digest = decision_digest(batch)
        with patch('ingestion.services.sync_user_ledger', wraps=sync_user_ledger) as sync:
            confirm_batch(self.user, batch.pk, digest)
            confirm_batch(self.user, batch.pk, digest)
        self.assertEqual(sync.call_count, 1)
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (1,1))
        batch.refresh_from_db()
        self.assertEqual(reconciliation(batch), {'date':'2026-09-01','expected':'970.00','actual':'975.00','difference':'5.00'})
        self.assertEqual(BankMovement.objects.get().kind, 'EXPENSE')

    def test_match_keeps_original_sources_and_weak_duplicates_are_only_suggestions(self):
        original = Transaction.objects.create(user=self.user, title='Coffee', amount=Decimal('25'), transaction_type='EXPENSE', category=self.category, payment_channel='ACCOUNT', bank_account=self.account, date=date(2026,9,1))
        sync_user_ledger(self.user)
        movement = BankMovement.objects.get()
        source_values = Transaction.objects.filter(pk=original.pk).values().get()
        movement_values = BankMovement.objects.filter(pk=movement.pk).values().get()
        batch = self.staged()
        self.assertTrue(row_suggestions(batch.rows.get())['weak_duplicate'])
        self.assertEqual(batch.rows.get().action, '')
        self.confirm(batch, self.decisions(batch, action='MATCH', category_id=None, matched_movement_id=movement.pk))
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (1,1))
        undo_batch(self.user, batch.pk)
        self.assertEqual(Transaction.objects.filter(pk=original.pk).values().get(), source_values)
        self.assertEqual(BankMovement.objects.filter(pk=movement.pk).values().get(), movement_values)

    def test_strong_identifier_blocks_new_file_and_is_released_on_undo(self):
        first = self.staged()
        self.confirm(first)
        second = self.staged('2026-09-01,Coffee copy,-25.00,entry1\n')
        with self.assertRaises(ValidationError):
            self.confirm(second)
        self.confirm(second, self.decisions(second, action='SKIP', category_id=None))
        self.assertEqual(Transaction.objects.count(), 1)
        undo_batch(self.user, first.pk)
        self.assertFalse(ExternalStatementIdentity.objects.exists())
        third = self.staged()
        self.assertNotEqual(first.pk, third.pk)
        self.confirm(third)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_duplicate_identifier_within_batch_is_atomic_and_requires_explicit_skip(self):
        batch = self.staged('2026-09-01,Coffee,-25.00,same\n2026-09-02,Other,-30.00,same\n')
        save_review(self.user, batch.pk, self.decisions(batch))
        with self.assertRaises(ValidationError):
            confirm_batch(self.user, batch.pk, decision_digest(batch))
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), (0,0))
        decisions = self.decisions(batch)
        decisions[batch.rows.last().pk].update(action='SKIP',category_id=None)
        self.confirm(batch, decisions)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_manual_invoice_payment_preserves_expense_and_undo_payment_only(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual', closing_day=31,due_day=28,manual_settlement_from=date(2026,1,1))
        purchase = Transaction.objects.create(user=self.user, title='Card purchase',amount=Decimal('100'),transaction_type='EXPENSE',category=self.category,payment_channel='CREDIT_CARD',credit_card=card,date=date(2026,9,1))
        sync_user_ledger(self.user)
        invoice = CardInvoice.objects.get(card=card)
        batch = self.staged()
        self.confirm(batch, self.decisions(batch,action='PAY_INVOICE',category_id=None,invoice_id=invoice.pk))
        self.assertEqual(Transaction.objects.count(),1)
        self.assertEqual(InvoicePayment.objects.get().amount,Decimal('25'))
        self.assertEqual(account_balance(self.account,date(2026,9,1)),Decimal('975'))
        undo_batch(self.user,batch.pk)
        self.assertTrue(Transaction.objects.filter(pk=purchase.pk).exists())
        self.assertEqual((InvoicePayment.objects.count(),BankMovement.objects.count()),(0,0))

    def test_transfer_uses_actual_other_amount_and_stays_neutral(self):
        other = BankAccount.objects.create(user=self.user,bank=self.bank,name='USD',currency='USD',opening_date=date(2026,1,1))
        batch = self.staged()
        self.confirm(batch,self.decisions(batch,action='TRANSFER',category_id=None,counterparty_account_id=other.pk,counterparty_amount=Decimal('5')))
        transfer=BankTransfer.objects.get()
        self.assertEqual((transfer.source_amount,transfer.destination_amount,transfer.fx_rate),(Decimal('25'),Decimal('5'),Decimal('0.2')))
        self.assertEqual(Transaction.objects.count(),0)
        self.assertEqual(account_balance(other,date(2026,9,1)),Decimal('5'))
        self.assertEqual(BankMovement.objects.count(),2)
        undo_batch(self.user,batch.pk)
        self.assertEqual((BankTransfer.objects.count(),BankMovement.objects.count()),(0,0))

    def test_long_transfer_description_preserves_evidence_and_can_be_undone(self):
        other = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Other BRL', currency='BRL',
            opening_date=date(2026, 1, 1),
        )
        prefix = 'Imported transfer: '
        description = prefix + 'é' * (300 - len(prefix))
        for amount in ('-25.00', '25.00'):
            with self.subTest(amount=amount):
                batch = self.staged(f'2026-09-01,{description},{amount},long-transfer\n')
                self.confirm(batch, self.decisions(
                    batch, action='TRANSFER', category_id=None,
                    counterparty_account_id=other.pk, counterparty_amount=Decimal('25'),
                ))
                row = batch.rows.get()
                transfer = row.created_transfer
                self.assertEqual(transfer.notes, description)
                self.assertEqual(row.description, description)
                self.assertEqual(row.raw['Text'], description)
                self.assertIn(description, batch.raw_text)
                movements = list(transfer.movements.all())
                self.assertEqual(len(movements), 2)
                self.assertEqual({movement.description for movement in movements}, {description[:255]})
                self.assertEqual({len(movement.description) for movement in movements}, {255})
                self.assertEqual(account_balance(self.account, date(2026, 9, 1)), Decimal('1000') + Decimal(amount))
                self.assertEqual(account_balance(other, date(2026, 9, 1)), -Decimal(amount))
                self.assertFalse(Transaction.objects.exists())

                undo_batch(self.user, batch.pk)
                batch.refresh_from_db()
                self.assertEqual(batch.status, 'UNDONE')
                self.assertEqual((BankTransfer.objects.count(), BankMovement.objects.count()), (0, 0))
                self.assertEqual(account_balance(self.account, date(2026, 9, 1)), Decimal('1000'))
                self.assertEqual(account_balance(other, date(2026, 9, 1)), Decimal('0'))
                self.assertEqual(batch.rows.get().raw['Text'], description)
                self.assertFalse(ExternalStatementIdentity.objects.exists())

    def test_second_payment_failure_rolls_back_every_post_and_identifier(self):
        card=CreditCard.objects.create(user=self.user,account=self.account,name='Small manual',closing_day=31,due_day=28,manual_settlement_from=date(2026,1,1))
        Transaction.objects.create(user=self.user,title='Small purchase',amount=Decimal('30'),transaction_type='EXPENSE',category=self.category,payment_channel='CREDIT_CARD',credit_card=card,date=date(2026,9,1))
        sync_user_ledger(self.user)
        invoice=CardInvoice.objects.get(card=card)
        batch=self.staged('2026-09-01,A,-25.00,a\n2026-09-01,B,-25.00,b\n')
        save_review(self.user,batch.pk,self.decisions(batch,action='PAY_INVOICE',category_id=None,invoice_id=invoice.pk))
        with self.assertRaises(ValidationError):
            confirm_batch(self.user,batch.pk,decision_digest(batch))
        batch.refresh_from_db()
        self.assertEqual(batch.status,'READY')
        self.assertEqual((InvoicePayment.objects.count(),BankMovement.objects.count(),ExternalStatementIdentity.objects.count()),(0,0,0))

    def test_undo_refuses_edited_source_and_preserves_the_whole_batch(self):
        batch=self.staged('2026-09-01,A,-25.00,a\n2026-09-02,B,-30.00,b\n')
        self.confirm(batch)
        source=batch.rows.first().created_transaction
        Transaction.objects.filter(pk=source.pk).update(notes='Reviewed later')
        with self.assertRaises(ValidationError):
            undo_batch(self.user,batch.pk)
        self.assertEqual((Transaction.objects.count(),BankMovement.objects.count()),(2,2))
        batch.refresh_from_db()
        self.assertEqual(batch.status,'CONFIRMED')

    def test_undo_detects_splits_and_direct_cash_edits(self):
        batch=self.staged()
        self.confirm(batch)
        source=batch.rows.get().created_transaction
        TransactionSplit.objects.create(transaction=source,category=self.category,amount=Decimal('25'))
        with self.assertRaises(ValidationError):
            undo_batch(self.user,batch.pk)
        source.splits.all().delete()
        BankMovement.objects.update(amount=Decimal('24'))
        with self.assertRaises(ValidationError):
            undo_batch(self.user,batch.pk)

    def test_another_confirmed_statement_match_protects_created_cash_evidence(self):
        first=self.staged()
        self.confirm(first)
        second=self.staged('2026-09-01,Same movement,-25.00,different\n')
        self.confirm(second,self.decisions(second,action='MATCH',category_id=None,matched_movement_id=BankMovement.objects.get().pk))
        with self.assertRaises(ValidationError):
            undo_batch(self.user,first.pk)
        undo_batch(self.user,second.pk)
        undo_batch(self.user,first.pk)
        self.assertEqual(Transaction.objects.count(),0)

    def test_legacy_unknown_opening_needs_explicit_date_without_inference(self):
        self.account.opening_date=None
        self.account.save(update_fields=['opening_date'])
        batch=self.staged()
        with self.assertRaises(ValidationError):
            self.confirm(batch)
        self.account.refresh_from_db()
        self.assertIsNone(self.account.opening_date)
        self.assertEqual(self.account.opening_balance,Decimal('1000'))
        self.assertEqual(BankMovement.objects.count(),0)

    def test_dated_opening_and_currency_mismatch_reject_staging(self):
        with self.assertRaises(ValidationError):
            self.staged('2025-12-31,Before baseline,-25.00,before\n')
        with self.assertRaises(ValidationError):
            stage_statement(self.user,self.account.pk,self.ofx(currency='USD'),'wrong.ofx','OFX')
        self.assertFalse(ImportBatch.objects.filter(file_format='OFX').exists())
        self.assertFalse(ImportedRow.objects.exists())

    def test_ownership_and_modified_review_digest_are_rechecked(self):
        foreign_bank=Bank.objects.create(user=self.other,name='Other')
        foreign_account=BankAccount.objects.create(user=self.other,bank=foreign_bank,name='Other',currency='BRL')
        foreign_category=Category.objects.create(user=self.other,name='Other')
        with self.assertRaises(ValidationError):
            stage_statement(self.user,foreign_account.pk,self.ofx(),'other.ofx','OFX')
        batch=self.staged()
        with self.assertRaises(ValidationError):
            self.confirm(batch,self.decisions(batch,category_id=foreign_category.pk))
        save_review(self.user,batch.pk,self.decisions(batch))
        digest=decision_digest(batch)
        batch.rows.update(action='SKIP',category=None)
        with self.assertRaises(ValidationError):
            confirm_batch(self.user,batch.pk,digest)
        self.assertEqual(Transaction.objects.count(),0)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('ingestion:review',args=[batch.pk])).status_code,404)

    def test_native_post_flow_and_invalid_fields_preserve_review(self):
        response=self.client.post(reverse('ingestion:index'),{'account':self.account.pk,'file_format':'CSV','encoding':'utf-8-sig','statement':SimpleUploadedFile('local.csv',b'Date,Text,Amount,Id\n2026-09-01,Coffee,-25,one\n')})
        batch=ImportBatch.objects.get()
        self.assertRedirects(response,reverse('ingestion:mapping',args=[batch.pk]))
        response=self.client.post(reverse('ingestion:mapping',args=[batch.pk]),{**MAPPING,'amount_mode':'signed'})
        self.assertRedirects(response,reverse('ingestion:review',args=[batch.pk]))
        row=batch.rows.get()
        response=self.client.post(reverse('ingestion:review',args=[batch.pk]),{f'row-{row.pk}-action':'CREATE'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Choose an owned category')
        self.assertContains(response,'value="CREATE" selected')
        self.assertEqual(Transaction.objects.count(),0)
        response=self.client.post(reverse('ingestion:review',args=[batch.pk]),{f'row-{row.pk}-action':'CREATE',f'row-{row.pk}-category':self.category.pk})
        self.assertRedirects(response,reverse('ingestion:confirmation',args=[batch.pk]))
        batch.refresh_from_db()
        response=self.client.post(reverse('ingestion:confirmation',args=[batch.pk]),{'digest':decision_digest(batch)})
        self.assertEqual(response.status_code,200)
        self.assertEqual(Transaction.objects.count(),0)
        response=self.client.post(reverse('ingestion:confirmation',args=[batch.pk]),{'digest':decision_digest(batch),'reviewed':'on'})
        self.assertRedirects(response,reverse('ingestion:detail',args=[batch.pk]))
        self.assertEqual(Transaction.objects.count(),1)
