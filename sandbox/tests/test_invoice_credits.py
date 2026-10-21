"""Planning snapshots deduct credit magnitudes without payment duplication."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from banking.models import Bank, BankAccount, CardInvoiceCredit, CreditCard
from categories.models import Category
from sandbox.planning import commitment_snapshot, snapshot_total
from transactions.models import Transaction


class CommitmentInvoiceCreditTests(TestCase):
    def test_credit_kind_reduces_reference_and_due_month_and_positive_override(self):
        user = get_user_model().objects.create_user('snapshot-credit')
        bank = Bank.objects.create(user=user, name='Bank')
        account = BankAccount.objects.create(user=user, bank=bank, name='Cash', currency='BRL')
        card = CreditCard.objects.create(user=user, account=account, name='Card', closing_day=24, due_day=1)
        category = Category.objects.filter(user=user).first()
        Transaction.objects.create(user=user, credit_card=card, category=category,
            title='Expense', amount='100', transaction_type='EXPENSE', payment_channel='CREDIT_CARD', date=date(2026, 10, 5))
        credit = CardInvoiceCredit.objects.create(user=user, card=card, category=category,
            title='Refund', amount='8.95', date=date(2026, 10, 10), reference_month=date(2026, 10, 1))
        snapshot = commitment_snapshot(user, date(2026, 10, 1), month_basis='reference_month')
        self.assertEqual(snapshot_total(snapshot, '2026-10'), Decimal('91.05'))
        row = next(row for row in snapshot['rows'] if row['key'] == f'invoice-credit:{credit.pk}')
        self.assertEqual(row['amount'], '8.95')
        self.assertEqual(row['kind'], 'invoice_credit')
        row['override'] = '10.00'
        self.assertEqual(snapshot_total(snapshot, '2026-10'), Decimal('90'))
        payment_snapshot = commitment_snapshot(user, date(2026, 11, 1))
        self.assertEqual(snapshot_total(payment_snapshot, '2026-11'), Decimal('91.05'))
        self.assertFalse(user.bank_movements.exists())
