# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from banking.credits import delete_invoice_credit, invoice_credit_totals, save_invoice_credit
from banking.models import BankMovement, CardInvoice, CardInvoiceCredit, CreditCard, InvoicePayment
from banking.services import account_balance
from banking.settlements import manual_invoice_obligations, save_invoice_payment
from banking.tests.factories import make_account
from categories.models import Category
from transactions.models import Transaction
from transactions.services import sync_user_ledger

MONTH = date(2026, 10, 1)
CUTOFF = date(2026, 10, 20)


class InvoiceCreditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('invoice-credit')
        self.other = get_user_model().objects.create_user('invoice-credit-other')
        self.account = make_account(self.user, opening='1000.00')
        self.card = CreditCard.objects.create(
            user=self.user, account=self.account, name='Prime', closing_day=24, due_day=1,
        )
        self.category = Category.objects.create(user=self.user, name='Transport', transaction_type='EXPENSE')
        self.purchase = Transaction.objects.create(
            user=self.user, title='Purchase', amount=Decimal('100.00'), transaction_type='EXPENSE',
            category=self.category, payment_channel='CREDIT_CARD', credit_card=self.card,
            date=MONTH,
        )

    def credit(self, amount='8.95', **overrides):
        values = {
            'user': self.user, 'card': self.card, 'category': self.category, 'title': 'Uber credit',
            'amount': Decimal(amount), 'date': date(2026, 9, 4), 'reference_month': MONTH,
        }
        values.update(overrides)
        return CardInvoiceCredit(**values)

    def sync(self, **kwargs):
        sync_user_ledger(self.user, through_date=CUTOFF, **kwargs)
        return CardInvoice.objects.get(card=self.card, reference_month=MONTH)

    def test_credit_nets_invoice_without_income_payment_or_cash_credit(self):
        credit = save_invoice_credit(self.credit(), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.gross_amount, Decimal('100.00'))
        self.assertEqual(invoice.credits_amount, Decimal('8.95'))
        self.assertEqual(invoice.amount, Decimal('91.05'))
        self.assertEqual(invoice.credit_balance, Decimal('0.00'))
        self.assertEqual(credit.date, date(2026, 9, 4))
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)
        self.assertFalse(InvoicePayment.objects.exists())
        self.assertFalse(BankMovement.objects.filter(direction='CREDIT').exists())
        movement = BankMovement.objects.get(user=self.user)
        self.assertEqual(movement.amount, Decimal('91.05'))
        self.assertEqual(movement.effective_date, date(2026, 11, 1))
        self.assertEqual(account_balance(self.account, as_of=CUTOFF), Decimal('1000.00'))

    def test_exact_import_bill_preserves_gross_sources(self):
        self.purchase.amount = Decimal('125.20')
        self.purchase.save()
        save_invoice_credit(self.credit(), user=self.user)
        self.assertEqual(self.sync().amount, Decimal('116.25'))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.amount, Decimal('125.20'))

    def test_credits_are_explicit_month_sources_and_never_recur(self):
        self.purchase.is_fixed = True
        self.purchase.save()
        save_invoice_credit(self.credit(), user=self.user)
        invoice = self.sync()
        next_invoice = CardInvoice.objects.get(card=self.card, reference_month=date(2026, 11, 1))
        self.assertEqual(invoice.amount, Decimal('91.05'))
        self.assertEqual(next_invoice.amount, Decimal('100.00'))

    def test_installments_keep_purchase_allocation_and_credit_month(self):
        self.purchase.amount = Decimal('300.00')
        self.purchase.installments = 3
        self.purchase.save()
        save_invoice_credit(self.credit(), user=self.user)
        self.assertEqual(self.sync().amount, Decimal('91.05'))
        self.assertEqual(CardInvoice.objects.get(card=self.card, reference_month=date(2026, 11, 1)).amount, Decimal('100.00'))
        self.assertEqual(self.purchase.installment_amount, Decimal('100.00'))

    def test_excess_is_retained_without_negative_or_zero_cash_movement(self):
        save_invoice_credit(self.credit('120.00'), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, Decimal('0.00'))
        self.assertEqual(invoice.credit_balance, Decimal('20.00'))
        self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(account_balance(self.account), Decimal('1000.00'))

    def test_credit_only_statement_remains_discoverable(self):
        self.purchase.delete()
        save_invoice_credit(self.credit(), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.gross_amount, 0)
        self.assertEqual(invoice.credit_balance, Decimal('8.95'))
        self.assertEqual(invoice.amount, 0)
        self.assertFalse(BankMovement.objects.exists())

    def test_zero_statement_removes_old_projection_movement(self):
        self.sync()
        self.assertTrue(BankMovement.objects.exists())
        save_invoice_credit(self.credit('100.00'), user=self.user)
        self.assertEqual(self.sync().amount, 0)
        self.assertFalse(BankMovement.objects.exists())

    def test_late_credit_does_not_rewrite_automatic_due_date_cash(self):
        save_invoice_credit(self.credit(date=date(2026, 11, 10)), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, Decimal('91.05'))
        movement = BankMovement.objects.get(user=self.user)
        self.assertEqual(movement.amount, Decimal('100.00'))
        self.assertEqual(movement.effective_date, date(2026, 11, 1))
        self.assertEqual(account_balance(self.account, as_of=date(2026, 11, 5)), Decimal('900.00'))
        self.assertEqual(account_balance(self.account, as_of=date(2026, 11, 20)), Decimal('900.00'))

    def test_late_credit_can_zero_statement_without_erasing_automatic_cash(self):
        save_invoice_credit(self.credit('120.00', date=date(2026, 11, 10)), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, 0)
        self.assertEqual(invoice.credit_balance, Decimal('20.00'))
        self.assertEqual(BankMovement.objects.get(user=self.user).amount, Decimal('100.00'))

    def test_due_date_credit_reduces_automatic_cash(self):
        save_invoice_credit(self.credit(date=date(2026, 11, 1)), user=self.user)
        self.sync()
        self.assertEqual(BankMovement.objects.get(user=self.user).amount, Decimal('91.05'))

    def test_manual_obligation_uses_only_credits_posted_by_cutoff(self):
        self.card.manual_settlement_from = date(2026, 1, 1)
        self.card.save()
        save_invoice_credit(self.credit('120.00', date=date(2026, 11, 10)), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, 0)
        earlier = manual_invoice_obligations(self.user, date(2026, 11, 5))
        self.assertEqual(earlier[0].remaining_amount_at_cutoff, Decimal('100.00'))
        self.assertEqual(manual_invoice_obligations(self.user, date(2026, 11, 20)), [])

    def test_future_credit_does_not_mark_manual_invoice_paid_before_posting(self):
        self.card.manual_settlement_from = date(2026, 1, 1)
        self.card.save()
        save_invoice_credit(self.credit('120.00', date=date(2026, 11, 10)), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, 0)
        self.assertEqual(invoice.status, CardInvoice.Status.SCHEDULED)
        sync_user_ledger(self.user, through_date=date(2026, 11, 5))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, CardInvoice.Status.OVERDUE)
        sync_user_ledger(self.user, through_date=date(2026, 11, 10))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, CardInvoice.Status.PAID)

    def test_payment_refresh_does_not_use_future_credit_as_settlement_evidence(self):
        self.card.manual_settlement_from = date(2026, 1, 1)
        self.card.save()
        invoice = self.sync()
        payment = save_invoice_payment(InvoicePayment(
            user=self.user, invoice=invoice, account=self.account,
            amount=Decimal('40.00'), date=CUTOFF,
        ))
        save_invoice_credit(self.credit('20.00', date=date(2026, 11, 10)), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, Decimal('80.00'))
        payment.amount = Decimal('80.00')
        save_invoice_payment(payment)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, CardInvoice.Status.PARTIAL)

    def test_future_credit_does_not_block_an_actual_payment_today(self):
        self.card.manual_settlement_from = date(2026, 1, 1)
        self.card.save()
        save_invoice_credit(self.credit('120.00', date=date(2026, 11, 10)), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, 0)
        payment = save_invoice_payment(InvoicePayment(
            user=self.user, invoice=invoice, account=self.account,
            amount=Decimal('100.00'), date=CUTOFF,
        ))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, CardInvoice.Status.PAID)
        self.assertEqual(payment.amount, Decimal('100.00'))
        self.assertEqual(account_balance(self.account, as_of=CUTOFF), Decimal('900.00'))
        with self.assertRaises(ValidationError):
            save_invoice_payment(InvoicePayment(
                user=self.user, invoice=invoice, account=self.account,
                amount=Decimal('0.01'), date=CUTOFF,
            ))

    def test_second_sync_keeps_identity_and_timestamp(self):
        credit = save_invoice_credit(self.credit(), user=self.user)
        invoice = self.sync()
        movement = BankMovement.objects.get(user=self.user)
        before = (invoice.pk, invoice.updated_at, movement.pk, movement.updated_at, credit.updated_at)
        invoice = self.sync()
        movement.refresh_from_db(); credit.refresh_from_db()
        self.assertEqual(before, (invoice.pk, invoice.updated_at, movement.pk, movement.updated_at, credit.updated_at))

    def test_credit_edits_and_deletion_reconcile_old_and_new_months(self):
        credit = save_invoice_credit(self.credit(), user=self.user)
        credit.reference_month = date(2026, 11, 1)
        save_invoice_credit(credit, user=self.user)
        self.assertEqual(self.sync().amount, Decimal('100.00'))
        november = CardInvoice.objects.get(card=self.card, reference_month=credit.reference_month)
        self.assertEqual(november.credit_balance, Decimal('8.95'))
        delete_invoice_credit(credit, user=self.user)
        self.assertFalse(CardInvoice.objects.filter(pk=november.pk).exists())
        self.assertEqual(self.sync().amount, Decimal('100.00'))

    def test_idempotent_repeat_returns_existing_credit_and_rejects_changed_payload(self):
        key = uuid.uuid4()
        first = save_invoice_credit(self.credit(idempotency_key=key), user=self.user)
        repeated = self.credit(idempotency_key=str(key), amount='8.95')
        self.assertEqual(save_invoice_credit(repeated, user=self.user).pk, first.pk)
        self.assertEqual(CardInvoiceCredit.objects.count(), 1)
        with self.assertRaises(ValidationError):
            save_invoice_credit(self.credit('9.00', idempotency_key=key), user=self.user)
        first.idempotency_key = uuid.uuid4()
        with self.assertRaises(ValidationError):
            save_invoice_credit(first, user=self.user)

    def test_foreign_user_cannot_create_edit_delete_or_reuse_confirmation(self):
        credit = save_invoice_credit(self.credit(), user=self.user)
        for operation in (save_invoice_credit, delete_invoice_credit):
            with self.assertRaises(ValidationError):
                operation(credit, user=self.other)
        foreign = self.credit(user=self.other, idempotency_key=credit.idempotency_key)
        with self.assertRaises(ValidationError):
            save_invoice_credit(foreign, user=self.other)
        self.assertEqual(CardInvoiceCredit.objects.count(), 1)

    def test_save_and_delete_roll_back_source_when_reconciliation_fails(self):
        with patch('transactions.services.sync_user_ledger', side_effect=ValidationError('projection failure')):
            with self.assertRaises(ValidationError):
                save_invoice_credit(self.credit(), user=self.user)
        self.assertFalse(CardInvoiceCredit.objects.exists())
        credit = save_invoice_credit(self.credit(), user=self.user)
        with patch('transactions.services.sync_user_ledger', side_effect=ValidationError('projection failure')):
            with self.assertRaises(ValidationError):
                delete_invoice_credit(credit, user=self.user)
        self.assertTrue(CardInvoiceCredit.objects.filter(pk=credit.pk).exists())

    def test_credit_does_not_erase_confirmed_cash_payment(self):
        self.card.manual_settlement_from = date(2026, 1, 1)
        self.card.save()
        invoice = self.sync()
        payment = save_invoice_payment(InvoicePayment(
            user=self.user, invoice=invoice, account=self.account,
            amount=Decimal('100.00'), date=CUTOFF,
        ))
        save_invoice_credit(self.credit(), user=self.user)
        invoice = self.sync()
        self.assertEqual(invoice.amount, Decimal('91.05'))
        self.assertEqual(invoice.overpaid_amount, Decimal('8.95'))
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal('100.00'))
        self.assertEqual(account_balance(self.account, as_of=CUTOFF), Decimal('900.00'))
        self.assertEqual(BankMovement.objects.count(), 1)

    def test_payment_bearing_statement_keeps_credit_outside_projection_horizon(self):
        self.card.manual_settlement_from = date(2026, 1, 1)
        self.card.save()
        invoice = self.sync()
        save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=self.account, amount=Decimal('40.00'), date=CUTOFF))
        save_invoice_credit(self.credit(), user=self.user)
        sync_user_ledger(self.user, through_date=date(2026, 1, 1), projection_months=0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount, Decimal('91.05'))
        self.assertEqual(invoice.payments.count(), 1)

    def test_read_totals_are_owner_scoped_and_use_posting_cutoff(self):
        save_invoice_credit(self.credit(), user=self.user)
        self.assertEqual(invoice_credit_totals(self.other), 0)
        self.assertEqual(invoice_credit_totals(self.user, as_of=date(2026, 9, 3)), 0)
        self.assertEqual(invoice_credit_totals(self.user, reference_month=MONTH, as_of=date(2026, 9, 4)), Decimal('8.95'))
        self.assertEqual(invoice_credit_totals(self.user, reference_month=date(2026, 9, 1)), 0)

    def test_model_rejects_wrong_owner_category_type_month_and_baseline(self):
        foreign_account = make_account(self.other)
        foreign_card = CreditCard.objects.create(user=self.other, account=foreign_account, name='Other', closing_day=20, due_day=1)
        income = Category.objects.create(user=self.user, name='Salary', transaction_type='INCOME')
        foreign_category = Category.objects.create(user=self.other, name='Other expense')
        invalid_cases = [
            {'amount': Decimal('0.00')}, {'amount': Decimal('-1.00')},
            {'card': foreign_card}, {'category': foreign_category}, {'category': income},
            {'reference_month': date(2026, 10, 2)},
        ]
        for changes in invalid_cases:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.credit(**changes).full_clean()
        self.account.opening_date = MONTH; self.account.save()
        with self.assertRaises(ValidationError):
            self.credit().full_clean()

    def test_model_rejects_corrupt_cross_owner_account_or_bank(self):
        self.account.user = self.other; self.account.save()
        with self.assertRaises(ValidationError):
            self.credit().full_clean()
        self.account.user = self.user; self.account.save()
        self.account.bank.user = self.other; self.account.bank.save()
        with self.assertRaises(ValidationError):
            self.credit().full_clean()

    def test_unclassified_category_is_allowed_and_references_are_protected(self):
        self.category.transaction_type = None; self.category.save()
        credit = save_invoice_credit(self.credit(), user=self.user)
        with self.assertRaises(ProtectedError):
            self.category.delete()
        with self.assertRaises(ProtectedError):
            self.card.delete()
        self.assertTrue(CardInvoiceCredit.objects.filter(pk=credit.pk).exists())

    def test_database_disallows_nonpositive_amount_and_duplicate_key(self):
        credit = save_invoice_credit(self.credit(), user=self.user)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            invalid = self.credit('0.00'); invalid.save()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            self.credit(idempotency_key=credit.idempotency_key).save()
