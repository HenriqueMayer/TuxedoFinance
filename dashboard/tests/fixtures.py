"""Fixtures coverage for dashboard."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from banking.models import Bank, BankAccount
from categories.models import Category
from transactions.models import Transaction


User = get_user_model()


class DashboardFixture(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dashboard', password='test')
        self.bank = Bank.objects.create(user=self.user, name='Bank With Spaces')
        self.account = BankAccount.objects.create(
            user=self.user,
            bank=self.bank,
            name='Main Account',
            currency='BRL',
            opening_balance='1000.00',
        )
        self.category, _ = Category.objects.get_or_create(
            user=self.user, name='Groceries'
        )
        self.client.force_login(self.user)

    def transaction(self, **overrides):
        values = {
            'user': self.user,
            'title': 'Transaction',
            'amount': Decimal('100.00'),
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category,
            'payment_channel': Transaction.PaymentChannel.PIX,
            'bank_account': self.account,
            'date': timezone.localdate(),
        }
        values.update(overrides)
        return Transaction.objects.create(**values)
