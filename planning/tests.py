# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from banking.models import Bank, BankAccount, BankMovement, CreditCard, ExchangeRate
from banking.services import account_balance, get_planning_availability
from categories.models import Category
from investments.models import Asset, InvestmentProduct
from planning.forms import CategoryBudgetForm, GoalAllocationForm
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalDecision, SignalSettings
from planning.services import budget_progress, copy_previous_budgets, goal_progress, local_signals, reserved_by_source, save_allocation, set_goal_archived, validate_budget_category_change
from transactions.models import Transaction, TransactionSplit


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


class BudgetTests(PlanningFixture):
    def test_category_move_or_income_reclassification_cannot_invalidate_limits(self):
        independent = Category.objects.create(user=self.user, name='Movable budget category')
        for category in [self.category, independent]:
            CategoryBudget.objects.create(user=self.user, category=category, month=self.month, currency='BRL', amount='100')
        independent.name = 'Renamed budget category'
        with self.assertNumQueries(1):
            validate_budget_category_change(independent)
        independent.parent_category = self.category
        with self.assertRaises(ValidationError) as error:
            validate_budget_category_change(independent)
        self.assertIn('parent_category', error.exception.message_dict)
        independent.parent_category = None
        independent.transaction_type = 'INCOME'
        with self.assertRaises(ValidationError) as error:
            validate_budget_category_change(independent)
        self.assertIn('transaction_type', error.exception.message_dict)


    def test_hierarchy_overlap_rejected_but_other_month_currency_allowed(self):
        CategoryBudget.objects.create(user=self.user, category=self.category, month=self.month, currency='BRL', amount='200')
        form = CategoryBudgetForm({'month': self.month.strftime('%Y-%m'), 'category': self.child.pk, 'currency': 'BRL', 'amount': '300'}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)
        for currency, month in [('USD', self.month), ('BRL', date(2027, 3, 1))]:
            item = CategoryBudget(user=self.user, category=self.child, month=month, currency=currency, amount='50')
            item.full_clean()
            item.save()

    def test_ownership_income_and_invalid_month_rejected(self):
        income = Category.objects.create(user=self.user, name='Planning income', transaction_type='INCOME')
        for category in [self.private_category, income]:
            form = CategoryBudgetForm({'month': self.month.strftime('%Y-%m'), 'category': category.pk, 'currency': 'BRL', 'amount': '100'}, user=self.user)
            self.assertFalse(form.is_valid())
        form = CategoryBudgetForm({'month': 'bad-month', 'category': self.category.pk, 'currency': 'BRL', 'amount': '-1'}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(form['month'].value(), 'bad-month')
        self.assertNotEqual(form.fields['month'].widget.attrs.get('type'), 'month')

    def test_copy_keeps_existing_and_skips_overlapping_limits(self):
        previous = (self.month - timedelta(days=1)).replace(day=1)
        independent = Category.objects.create(user=self.user, name='Independent')
        for category in [self.child, independent]:
            CategoryBudget.objects.create(user=self.user, category=category, month=previous, amount='200', currency='BRL')
        existing = CategoryBudget.objects.create(user=self.user, category=self.category, month=self.month, amount='400', currency='BRL')
        self.assertEqual(copy_previous_budgets(self.user, self.month), (1, 1))
        existing.refresh_from_db()
        self.assertEqual(existing.amount, Decimal('400'))
        self.assertEqual(copy_previous_budgets(self.user, self.month), (0, 2))
        self.assertFalse(CategoryBudget.objects.filter(user=self.other).exists())

    def test_actual_forecast_descendants_and_currency_gaps(self):
        month = date(2026, 2, 1)
        CategoryBudget.objects.create(user=self.user, category=self.category, month=month, currency='BRL', amount='100')
        self.expense(category=self.child, date=date(2026, 2, 5), amount='80')
        self.expense(date=date(2026, 2, 25), amount='40')
        foreign = BankAccount.objects.create(user=self.user, bank=self.bank, name='USD', currency='USD')
        self.expense(bank_account=foreign, date=date(2026, 2, 10), amount='10')
        self.expense(user=self.other, category=self.private_category, bank_account=self.private_account, date=date(2026, 2, 5), amount='999')
        row = budget_progress(self.user, month, as_of=date(2026, 2, 15))[0]
        self.assertEqual((row['actual'], row['forecast']), (Decimal('80'), Decimal('120')))
        self.assertFalse(row['complete'])
        self.assertEqual(row['missing_currencies'], ['USD'])
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='5', effective_date=date(2026, 2, 1))
        row = budget_progress(self.user, month, as_of=date(2026, 2, 15))[0]
        self.assertEqual((row['actual'], row['forecast']), (Decimal('130'), Decimal('170')))
        self.assertTrue(row['complete'])
        self.assertTrue(row['over_budget'])
        self.assertEqual(row['remaining'], Decimal('-30'))

    def test_splits_do_not_charge_the_primary_category_again(self):
        other_category = Category.objects.create(user=self.user, name='Other split expenses')
        primary = Category.objects.create(user=self.user, name='Original split category')
        for category in [self.category, other_category, primary]:
            CategoryBudget.objects.create(user=self.user, category=category, month=self.month, amount='100', currency='BRL')
        operation = self.expense(category=primary, amount='100')
        TransactionSplit.objects.create(transaction=operation, category=self.child, amount='60')
        TransactionSplit.objects.create(transaction=operation, category=other_category, amount='40')
        values = {row['budget'].category_id: row['actual'] for row in budget_progress(self.user, self.month)}
        self.assertEqual(values, {self.category.pk: Decimal('60'), other_category.pk: Decimal('40'), primary.pk: Decimal('0')})

    def test_installment_month_rounding_and_future_actual(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Invoice card', closing_day=20, due_day=28)
        other_category = Category.objects.create(user=self.user, name='Tiny split')
        operation = self.expense(date=date(2026, 1, 5), amount='0.05', payment_channel='CREDIT_CARD', bank_account=None, credit_card=card, installments=3)
        TransactionSplit.objects.create(transaction=operation, category=self.category, amount='0.02')
        TransactionSplit.objects.create(transaction=operation, category=other_category, amount='0.03')
        collected = {self.category.pk: Decimal('0'), other_category.pk: Decimal('0')}
        for month_number in [1, 2, 3]:
            month = date(2026, month_number, 1)
            for category in [self.category, other_category]:
                CategoryBudget.objects.create(user=self.user, category=category, month=month, amount='1', currency='BRL')
            for row in budget_progress(self.user, month, as_of=date(2026, 1, 15)):
                collected[row['budget'].category_id] += row['forecast']
                if month_number > 1:
                    self.assertEqual(row['actual'], Decimal('0'))
        self.assertEqual(collected, {self.category.pk: Decimal('0.02'), other_category.pk: Decimal('0.03')})


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


class SignalTests(PlanningFixture):
    def test_historical_cash_signal_does_not_count_later_payments_twice(self):
        from banking.models import CardInvoice, InvoicePayment
        from banking.settlements import save_invoice_payment, delete_invoice_payment
        self.account.opening_balance = Decimal('100')
        self.account.save()
        other = BankAccount.objects.create(user=self.user, bank=self.bank, name='Other real cash', currency='BRL', opening_balance=100, opening_date=date(2020, 1, 1))
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Historical manual', closing_day=10, due_day=28, manual_settlement_from=self.today-timedelta(days=200))
        cutoff = self.today-timedelta(days=1)
        invoice = CardInvoice.objects.create(user=self.user, card=card, reference_month=self.month, due_date=self.today+timedelta(days=10), amount=80, manual_settlement=True)
        for account in (self.account, other):
            for due in (self.today+timedelta(days=10), cutoff-timedelta(days=2)):
                with self.subTest(account=account.pk, due=due):
                    invoice.due_date = due
                    invoice.save()
                    payment = save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=account, amount=40, date=self.today))
                    signals = [row for row in local_signals(self.user, as_of=cutoff)['signals'] if row['kind']=='futurecashshortage']
                    self.assertEqual(signals, [])
                    self.assertEqual(account_balance(self.account, cutoff), 100)
                    delete_invoice_payment(payment)

    def test_cash_signal_includes_manual_remainder_without_fabricating_debit(self):
        from banking.models import CardInvoice, InvoicePayment
        from banking.settlements import save_invoice_payment
        from transactions.services import sync_user_ledger
        self.account.opening_balance = Decimal('100')
        self.account.save()
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual', closing_day=31, due_day=31, manual_settlement_from=self.today)
        self.expense(amount=150, payment_channel='CREDIT_CARD', bank_account=None, credit_card=card)
        sync_user_ledger(self.user)
        SignalSettings.objects.create(user=self.user, forecast_days=90)
        invoice = CardInvoice.objects.get(card=card)
        signals = [row for row in local_signals(self.user)['signals'] if row['kind']=='futurecashshortage']
        self.assertEqual(len(signals), 1)
        self.assertIn('-50.00', signals[0]['explanation'])
        self.assertIn(reverse('banking:invoice_detail', args=[invoice.pk]), [source['url'] for source in signals[0]['sources']])
        self.assertEqual(account_balance(self.account), 100)
        self.assertFalse(BankMovement.objects.filter(account=self.account).exists())
        save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=self.account, amount=40, date=self.today))
        signals = [row for row in local_signals(self.user)['signals'] if row['kind']=='futurecashshortage']
        self.assertEqual(len(signals), 1)
        self.assertIn('-50.00', signals[0]['explanation'])
        self.assertEqual(account_balance(self.account), 60)

    def test_duplicates_explained_owned_stable_and_review_does_not_mutate_sources(self):
        self.expense(title='  Local subscription ', date=self.today - timedelta(days=1))
        latest = self.expense(title='local   subscription', date=self.today)
        self.expense(user=self.other, category=self.private_category, bank_account=self.private_account, title='local subscription', date=self.today)
        result = local_signals(self.user)
        duplicate = next(row for row in result['signals'] if row['kind'] == 'duplicates')
        self.assertEqual(len(duplicate['sources']), 2)
        self.assertEqual(duplicate['key'], next(row for row in local_signals(self.user)['signals'] if row['kind'] == 'duplicates')['key'])
        before = list(Transaction.objects.values('pk', 'amount', 'updated_at'))
        self.client.force_login(self.user)
        response = self.client.post(reverse('planning:signal_decision'), {'key': duplicate['key'], 'action': 'ACK'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(Transaction.objects.values('pk', 'amount', 'updated_at')), before)
        self.assertFalse(BankMovement.objects.exists())
        reviewed = next(row for row in local_signals(self.user)['signals'] if row['kind'] == 'duplicates')
        self.assertEqual(reviewed['decision'].action, 'ACK')
        latest.title = 'A different record'
        latest.save()
        self.assertFalse(any(row['kind'] == 'duplicates' for row in local_signals(self.user)['signals']))

    def test_subscription_threshold_and_fixed_template_history_limit(self):
        self.expense(title='Streaming', amount='100', date=self.today - timedelta(days=30))
        self.expense(title='streaming', amount='115')
        self.expense(title='Fixed template', amount='900', is_fixed=True)
        signals = local_signals(self.user)['signals']
        increases = [row for row in signals if row['kind'] == 'subscriptionincrease']
        self.assertEqual(len(increases), 1)
        self.assertIn('15.00%', increases[0]['explanation'])
        SignalSettings.objects.create(user=self.user, subscription_increase_percent='20')
        self.assertFalse(any(row['kind'] == 'subscriptionincrease' for row in local_signals(self.user)['signals']))

    def test_budget_and_cash_forecast_explain_only_known_money(self):
        CategoryBudget.objects.create(user=self.user, category=self.category, month=self.month, amount='50', currency='BRL')
        self.expense(amount='100')
        BankMovement.objects.create(user=self.user, account=self.account, direction='DEBIT', kind='EXPENSE', amount='1200', effective_date=self.today + timedelta(days=2))
        signals = local_signals(self.user)['signals']
        self.assertTrue(any(row['kind'] == 'budgetoverspend' for row in signals))
        shortage = next(row for row in signals if row['kind'] == 'futurecashshortage')
        self.assertIn('-200.00', shortage['explanation'])
        self.assertIn(str(self.today + timedelta(days=2)), shortage['explanation'])
        self.assertIn('Unrecorded income', shortage['explanation'])

    def test_read_only_get_defaults_disabled_signals_and_review_ownership(self):
        self.expense(title='Duplicate')
        self.expense(title='Duplicate')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('planning:signals')).status_code, 200)
        self.assertFalse(SignalSettings.objects.filter(user=self.user).exists())
        self.assertFalse(SignalDecision.objects.exists())
        SignalSettings.objects.create(user=self.user, duplicates_enabled=False, subscriptionincrease_enabled=False, budgetoverspend_enabled=False, futurecashshortage_enabled=False)
        self.assertEqual(local_signals(self.user)['signals'], [])
        response = self.client.post(reverse('planning:signal_decision'), {'key': 'duplicates:private-key', 'action': 'DISMISS'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SignalDecision.objects.exists())


class PlanningViewTests(PlanningFixture):
    def test_forms_routes_ownership_and_nonmutating_gets(self):
        own = self.goal()
        private = FinancialGoal.objects.create(user=self.other, name='Private goal', currency='BRL', target_amount='100')
        self.assertEqual(self.client.get(reverse('planning:goals')).status_code, 302)
        self.client.force_login(self.user)
        for route in ['budgets', 'goals', 'signals', 'budget_create', 'goal_create', 'signals_settings']:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(f'planning:{route}')).status_code, 200)
        self.assertEqual(self.client.get(reverse('planning:goal_detail', args=[private.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('planning:goal_archive', args=[private.pk])).status_code, 404)
        response = self.client.get(reverse('planning:allocation_create', args=[own.pk]))
        self.assertContains(response, 'data-search-select')
        self.assertContains(response, 'novalidate')
        self.assertNotContains(response, 'Private cash')
        self.assertEqual(self.client.get(reverse('planning:budget_copy')).status_code, 405)
        self.assertFalse(BankMovement.objects.exists())

    def test_goal_and_reservation_post_retains_invalid_and_valid_values(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('planning:goal_create'), {'name': 'Study', 'target_amount': '200', 'currency': 'BRL', 'target_date': '31/12/2027'})
        self.assertEqual(response.status_code, 302)
        goal = FinancialGoal.objects.get(name='Study')
        self.assertEqual(goal.target_date, date(2027, 12, 31))
        response = self.client.post(reverse('planning:allocation_create', args=[goal.pk]), {'source': f'account:{self.account.pk}', 'amount': '1500'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, 'value="1500"')
        response = self.client.post(reverse('planning:allocation_create', args=[goal.pk]), {'source': f'account:{self.account.pk}', 'amount': '200'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(goal.allocations.get().amount, Decimal('200'))

    def test_budget_invalid_filter_recovery_and_copy_invalid_month(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('planning:budgets'), {'month': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="invalid"')
        self.assertContains(response, 'role="alert"')
        response = self.client.post(reverse('planning:budget_copy'), {'month': 'invalid'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'value="invalid"', status_code=400)
