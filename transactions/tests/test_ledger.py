"""Ledger coverage for transactions."""

from datetime import date
from decimal import Decimal
from banking.models import BankMovement, CardInvoice, LoyaltyProgram, RewardRedemption
from transactions.models import Transaction
from transactions.services import sync_user_ledger
from transactions.tests.fixtures import TransactionFixture


class LedgerSyncTests(TransactionFixture):
    def test_pix_and_debit_are_immediate_debits(self):
        pix = self.make_transaction(title='External PIX', payment_channel=Transaction.PaymentChannel.PIX)
        self.make_transaction(
            title='Store', amount=Decimal('30.00'),
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            bank_account=None, debit_card=self.debit,
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        movements = BankMovement.objects.filter(user=self.user).order_by('amount')
        self.assertEqual(movements.count(), 2)
        self.assertEqual({movement.direction for movement in movements}, {'DEBIT'})
        self.assertEqual(
            BankMovement.objects.get(source_key=f'transaction:{pix.pk}:2026-01').description,
            'External PIX',
        )
        self.assertEqual(self.account.current_balance(as_of=date(2026, 1, 31)), Decimal('850.00'))

    def test_income_is_credit(self):
        self.make_transaction(
            amount=Decimal('500.00'), transaction_type=Transaction.TransactionType.INCOME
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        movement = BankMovement.objects.get(user=self.user)
        self.assertEqual((movement.direction, movement.kind), ('CREDIT', 'INCOME'))

    def test_credit_purchase_only_debits_cash_on_invoice_due_date(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None, credit_card=self.credit,
            date=date(2026, 1, 25),
        )
        sync_user_ledger(self.user, through_date=date(2026, 3, 1), projection_months=0)
        invoice = CardInvoice.objects.get(card=self.credit, reference_month=date(2026, 2, 1))
        movement = BankMovement.objects.get(user=self.user)
        self.assertEqual(invoice.amount, item.amount)
        self.assertEqual(invoice.status, CardInvoice.Status.PAID)
        self.assertEqual(movement.kind, BankMovement.Kind.INVOICE)
        self.assertEqual(movement.effective_date, date(2026, 2, 28))
        self.assertFalse(BankMovement.objects.filter(kind=BankMovement.Kind.EXPENSE).exists())

    def test_deleting_credit_purchase_removes_invoice_and_settlement(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None, credit_card=self.credit,
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertTrue(CardInvoice.objects.filter(user=self.user).exists())
        item.delete()
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertFalse(CardInvoice.objects.filter(user=self.user).exists())
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_recurring_ledger_is_idempotent_and_clamps_day(self):
        item = self.make_transaction(date=date(2026, 1, 31), is_fixed=True)
        for _ in range(2):
            sync_user_ledger(self.user, through_date=date(2026, 3, 31), projection_months=0)
        movements = BankMovement.objects.filter(user=self.user).order_by('effective_date')
        self.assertEqual(movements.count(), 3)
        self.assertEqual(
            list(movements.values_list('effective_date', flat=True)),
            [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)],
        )
        self.assertEqual(movements.first().source_key, f'transaction:{item.pk}:2026-01')

    def test_update_and_delete_remove_stale_projection(self):
        item = self.make_transaction(amount=Decimal('10.00'))
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        item.amount = Decimal('25.00')
        item.save()
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertEqual(BankMovement.objects.get(user=self.user).amount, Decimal('25.00'))
        item.delete()
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_iof_credit_card_is_included_in_invoice(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Miles')
        RewardRedemption.objects.create(
            user=self.user, program=program, points=Decimal('1000'),
            target_account=self.account, target_amount=Decimal('10'),
            iof_amount=Decimal('2.50'), iof_credit_card=self.credit,
            date=date(2026, 1, 25),
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=2)
        invoice = CardInvoice.objects.get(card=self.credit, reference_month=date(2026, 2, 1))
        self.assertEqual(invoice.amount, Decimal('2.50'))
