# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Fixtures coverage for planning."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from banking.models import Bank, BankAccount
from categories.models import Category
from investments.models import Asset, InvestmentProduct
from planning.models import FinancialGoal, GoalAllocation
from planning.services import save_allocation
from transactions.models import Transaction


class PlanningFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('local-planner', password='test')
        cls.other = get_user_model().objects.create_user('private-planner', password='test')
        cls.today = timezone.localdate()
        cls.month = cls.today.replace(day=1)
        cls.bank = Bank.objects.create(user=cls.user, name='Local bank')
        cls.account = BankAccount.objects.create(user=cls.user, bank=cls.bank, name='Real cash', currency='BRL', opening_balance=Decimal('1000.00'), opening_date=date(2020, 1, 1), reserved_amount=Decimal('300.00'))
        cls.private_bank = Bank.objects.create(user=cls.other, name='Private bank')
        cls.private_account = BankAccount.objects.create(user=cls.other, bank=cls.private_bank, name='Private cash', currency='BRL', opening_balance='9000.00')
        cls.category = Category.objects.create(user=cls.user, name='Planning expenses', transaction_type='EXPENSE')
        cls.child = Category.objects.create(user=cls.user, name='Planning child', parent_category=cls.category, transaction_type='EXPENSE')
        cls.private_category = Category.objects.create(user=cls.other, name='Private expenses')
        cls.product = InvestmentProduct.objects.create(user=cls.user, bank=cls.bank, name='Reserve pot', purpose='MONTHLY_CASH')
        cls.asset = Asset.objects.create(user=cls.user, name='Cash BRL', code='LOCALCASH', currency='BRL', asset_class='LIQUIDITY', valuation_mode='MONETARY', opening_balance='500.00', opening_product=cls.product, opening_date=date(2020, 1, 1))

    def expense(self, **kwargs):
        values = dict(user=self.user, category=self.category, title='Recorded expense', amount=Decimal('100.00'), transaction_type='EXPENSE', payment_channel='ACCOUNT', bank_account=self.account, date=self.today)
        values.update(kwargs)
        return Transaction.objects.create(**values)

    def goal(self, name='Emergency', **kwargs):
        values = dict(user=self.user, name=name, target_amount=Decimal('1000.00'), currency='BRL')
        values.update(kwargs)
        return FinancialGoal.objects.create(**values)

    def reserve(self, goal=None, amount='100.00', **kwargs):
        values = dict(user=self.user, goal=goal or self.goal(), bank_account=self.account, amount=Decimal(amount))
        values.update(kwargs)
        return save_allocation(GoalAllocation(**values))
