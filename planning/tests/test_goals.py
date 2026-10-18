# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Goals coverage for planning."""

from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from banking.models import BankAccount, BankMovement, ExchangeRate
from banking.services import account_balance, get_planning_availability
from investments.models import InvestmentProduct
from planning.forms import GoalAllocationForm
from planning.models import FinancialGoal, GoalAllocation
from planning.services import goal_progress, reserved_by_source, save_allocation, set_goal_archived
from planning.tests.fixtures import PlanningFixture


class GoalTests(PlanningFixture):
    def test_reservation_names_existing_reserve_without_a_movement(self):
        before = BankMovement.objects.count()
        allocation = self.reserve(amount='200')
        self.assertEqual(BankMovement.objects.count(), before)
        self.assertEqual(account_balance(self.account), Decimal('1000'))
        self.assertEqual(reserved_by_source(self.user)['accounts'], {self.account.pk: Decimal('200')})
        row = get_planning_availability(self.user)['account_rows'][0]
        self.assertEqual(row['reserved'], Decimal('300'))
        self.assertEqual(row['available'], Decimal('700'))
        allocation.amount = Decimal('400')
        save_allocation(allocation)
        row = get_planning_availability(self.user)['account_rows'][0]
        self.assertEqual(row['reserved'], Decimal('400'))
        self.assertEqual(row['available'], Decimal('600'))

    def test_all_goals_share_capacity_and_balance_decline_is_proportional(self):
        first = self.reserve(self.goal('First'), amount='600')
        second = self.reserve(self.goal('Second'), amount='400')
        with self.assertRaises(ValidationError):
            self.reserve(self.goal('Third'), amount='0.01')
        BankMovement.objects.create(user=self.user, account=self.account, direction='DEBIT', kind='ADJUSTMENT', amount='600', effective_date=self.today)
        progress = {row['goal'].name: row for row in goal_progress(self.user)}
        self.assertEqual(progress['First']['progress'], Decimal('240'))
        self.assertEqual(progress['Second']['progress'], Decimal('160'))
        self.assertTrue(progress['First']['has_shortfall'])
        self.assertEqual(progress['First']['allocations'][0]['shortfall'], Decimal('360'))
        self.assertEqual(first.amount + second.amount, Decimal('1000'))
        self.assertEqual(reserved_by_source(self.user)['accounts'][self.account.pk], Decimal('1000'))

    def test_archive_release_and_restore_revalidates_shared_capacity(self):
        first = self.reserve(self.goal('First'), amount='800')
        set_goal_archived(first.goal, True)
        self.assertEqual(reserved_by_source(self.user)['accounts'], {})
        self.reserve(self.goal('Second'), amount='500')
        with self.assertRaises(ValidationError):
            set_goal_archived(first.goal, False)
        first.goal.refresh_from_db()
        self.assertTrue(first.goal.is_archived)

    def test_cashpot_native_reserve_and_foreign_target_need_reference_rate(self):
        goal = self.goal(currency='USD', target_amount='200')
        self.reserve(goal, amount='250', bank_account=None, product=self.product, asset=self.asset)
        self.assertEqual(reserved_by_source(self.user)['cash_pots'], {(self.product.pk, self.asset.pk): Decimal('250')})
        row = goal_progress(self.user)[0]
        self.assertEqual(row['progress'], Decimal('0'))
        self.assertFalse(row['complete'])
        self.assertEqual(row['missing_currencies'], ['BRL'])
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='5', effective_date=self.today)
        row = goal_progress(self.user)[0]
        self.assertTrue(row['complete'])
        self.assertEqual(row['progress'], Decimal('50'))
        self.assertEqual(get_planning_availability(self.user)['cash_pots'][0]['available'], Decimal('250'))

    def test_sources_and_goals_are_owned_and_not_automatically_created(self):
        goal = self.goal()
        form = GoalAllocationForm({'source': f'account:{self.private_account.pk}', 'amount': '50'}, user=self.user, goal=goal)
        self.assertFalse(form.is_valid())
        self.assertIn('source', form.errors)
        private_goal = FinancialGoal.objects.create(user=self.other, name='Private target', currency='BRL', target_amount='100')
        with self.assertRaises(ValidationError):
            self.reserve(private_goal)
        self.assertEqual(BankAccount.objects.filter(user=self.user).count(), 1)
        self.assertEqual(InvestmentProduct.objects.filter(user=self.user).count(), 1)

    def test_negative_balance_and_database_source_constraint(self):
        self.account.opening_balance = Decimal('-10')
        self.account.save()
        with self.assertRaises(ValidationError):
            self.reserve(amount='0.01')
        with self.assertRaises(IntegrityError), transaction.atomic():
            GoalAllocation.objects.create(user=self.user, goal=self.goal(), amount='1')

    def test_historical_read_excludes_later_created_reservation(self):
        allocation = self.reserve(amount='100')
        self.assertEqual(reserved_by_source(self.user, self.today - timedelta(days=1)), {'accounts': {}, 'cash_pots': {}})
        GoalAllocation.objects.filter(pk=allocation.pk).update(created_at=timezone.now() - timedelta(days=10))
        self.assertEqual(reserved_by_source(self.user, self.today - timedelta(days=1))['accounts'], {self.account.pk: Decimal('100')})

    def test_proportional_backing_preserves_source_cents(self):
        for name in ['One', 'Two', 'Three']:
            self.reserve(self.goal(name), amount='1')
        self.account.opening_balance = Decimal('0.01')
        self.account.save()
        rows = goal_progress(self.user)
        self.assertEqual(sum((row['progress'] for row in rows), Decimal('0')), Decimal('0.01'))
        self.assertTrue(all(row['has_shortfall'] for row in rows))

    def test_source_identifiers_above_one_thousand_remain_machine_values(self):
        account = BankAccount.objects.create(pk=1001, user=self.user, bank=self.bank, name='Large id', currency='BRL', opening_balance='5')
        form = GoalAllocationForm({'source': 'account:1001', 'amount': '1'}, user=self.user, goal=self.goal())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.bank_account_id, account.pk)
        self.assertIn('value="account:1001"', str(form['source']))
