"""Fixtures coverage for transactions."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from banking.models import Bank, BankAccount, CreditCard, DebitCard
from categories.models import Category
from transactions.models import Transaction


User = get_user_model()


class TransactionFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('owner', password='test')
        cls.other = User.objects.create_user('other', password='test')
        cls.category = Category.objects.create(user=cls.user, name='General')
        cls.other_category = Category.objects.create(user=cls.other, name='Private')
        cls.bank = Bank.objects.create(user=cls.user, name='North Bank')
        cls.account = BankAccount.objects.create(
            user=cls.user, bank=cls.bank, name='Daily', currency='BRL',
            opening_balance=Decimal('1000.00')
        )
        cls.debit = DebitCard.objects.create(
            user=cls.user, account=cls.account, name='Daily Debit'
        )
        cls.credit = CreditCard.objects.create(
            user=cls.user, account=cls.account, name='Blue Credit',
            closing_day=24, due_day=31
        )
        cls.other_bank = Bank.objects.create(user=cls.other, name='Other Bank')
        cls.other_account = BankAccount.objects.create(
            user=cls.other, bank=cls.other_bank, name='Secret', currency='BRL'
        )
        cls.other_credit = CreditCard.objects.create(
            user=cls.other, account=cls.other_account, name='Other Card',
            closing_day=10, due_day=10
        )

    def make_transaction(self, **overrides):
        values = {
            'user': self.user,
            'title': 'Purchase',
            'amount': Decimal('120.00'),
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category,
            'payment_channel': Transaction.PaymentChannel.ACCOUNT,
            'bank_account': self.account,
            'date': date(2026, 1, 15),
        }
        values.update(overrides)
        return Transaction.objects.create(**values)
