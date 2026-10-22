# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Budgets coverage for planning."""

from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from banking.models import BankAccount, CreditCard, ExchangeRate
from categories.models import Category
from planning.forms import CategoryBudgetForm
from planning.models import CategoryBudget
from planning.services import budget_progress, copy_previous_budgets, validate_budget_category_change
from transactions.models import TransactionSplit
from planning.tests.fixtures import PlanningFixture


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
