# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from calendar import monthrange
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from banking.models import BankMovement, CreditCard, ExchangeRate
from investments.models import Investment, InvestmentProduct, PositionPlanningSetting
from planning.monthly import monthly_outlook
from planning.tests.fixtures import PlanningFixture
from transactions.models import Transaction
from transactions.services import sync_user_ledger


class MonthlyOutlookTests(PlanningFixture):
    def test_legacy_undated_cash_opening_warns_without_changing_recorded_money(self):
        self.asset.opening_date = None  # Simulate the nullable legacy migration.
        self.asset.save(update_fields=['opening_date'])
        past = date(2024, 1, 1)
        result = monthly_outlook(self.user, past)
        self.assertTrue(result['unknown_openings'])
        self.assertEqual(result['projected_available'], Decimal('1200'))
        self.client.force_login(self.user)
        response = self.client.get(reverse('planning:index'), {'month': '2024-01'})
        self.assertContains(response, 'Historical amounts may include those undated balances.')
        self.assertFalse(BankMovement.objects.exists())

    def test_zero_or_other_product_opening_does_not_mark_cash_position_unknown(self):
        self.asset.opening_date = None
        self.asset.opening_balance = Decimal('0')
        self.asset.save(update_fields=['opening_date', 'opening_balance'])
        self.assertFalse(monthly_outlook(self.user, self.month)['unknown_openings'])
        portfolio = InvestmentProduct.objects.create(user=self.user, bank=self.bank,
            name='Different opening product', purpose='INVESTMENT')
        self.asset.opening_balance = Decimal('500')
        self.asset.opening_product = portfolio
        self.asset.save(update_fields=['opening_balance', 'opening_product'])
        Investment.objects.create(user=self.user, product=self.product, asset=self.asset,
            kind='YIELD', amount=Decimal('10'), date=self.today)
        result = monthly_outlook(self.user, self.month)
        self.assertFalse(result['unknown_openings'])
        self.assertEqual(result['recorded']['pot_total'], Decimal('10'))
        self.assertEqual(result['projected_available'], Decimal('710'))
        self.assertFalse(BankMovement.objects.exists())

    def test_past_recorded_cash_does_not_claim_zero_unpaid_invoice_obligations(self):
        past = date(2026, 9, 1)
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Historical manual', closing_day=1, due_day=15, manual_settlement_from=past)
        Transaction.objects.create(user=self.user, title='Historical bill', category=self.category, amount='400',
            transaction_type='EXPENSE', payment_channel='CREDIT_CARD', credit_card=card, date=past)
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 14)):
            sync_user_ledger(self.user)
            result = monthly_outlook(self.user, past)
            self.assertTrue(result['is_past'])
            self.assertIsNone(result['unpaid_invoices'])
            self.assertEqual(result['projected_available'], result['recorded']['available_total'])
            self.client.force_login(self.user)
            response = self.client.get(reverse('planning:index'), {'month': '2026-09'})
        self.assertContains(response, 'Available at month end')
        self.assertNotContains(response, 'Unpaid confirmed-mode invoices')

    def test_unchanged_foreign_balance_uses_the_same_cent_reconciliation(self):
        self.account.currency = 'USD'
        self.account.opening_balance = Decimal('0.03')
        self.account.reserved_amount = Decimal('0.01')
        self.account.save()
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='1.5', effective_date=self.month)
        result = monthly_outlook(self.user, self.month)
        self.assertEqual(result['projected_available'], result['recorded']['available_total'])
        self.assertEqual(result['known_change'], Decimal('0.00'))

    def test_excluded_reserve_stays_in_balance_but_not_available(self):
        PositionPlanningSetting.objects.create(user=self.user, product=self.product, asset=self.asset, planning_enabled=False)
        outlook = monthly_outlook(self.user, self.month)
        self.assertEqual(outlook['recorded']['bank_total'] + outlook['recorded']['pot_total'], Decimal('1500'))
        self.assertEqual(outlook['recorded']['available_total'], Decimal('700'))
        self.assertEqual(outlook['projected_available'], Decimal('700'))
        self.assertEqual(outlook['projected_reserved'], Decimal('800'))
        self.assertFalse(BankMovement.objects.exists())

    def test_manual_invoice_obligation_caps_reserve_without_inventing_cash_deficit(self):
        self.account.planning_enabled = False
        self.account.save()
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual', closing_day=31, due_day=31, manual_settlement_from=self.month)
        Transaction.objects.create(user=self.user, title='Known bill', category=self.category, amount='400',
            transaction_type='EXPENSE', payment_channel='CREDIT_CARD', credit_card=card, date=self.month)
        sync_user_ledger(self.user)
        result = monthly_outlook(self.user, self.month)
        self.assertEqual(result['unpaid_invoices'], Decimal('400'))
        self.assertEqual(result['projected_available'], Decimal('500'))
        self.assertEqual(result['projected_reserved'], Decimal('600'))
        self.assertEqual(result['recorded']['bank_total'], Decimal('1000'))
        self.assertFalse(BankMovement.objects.filter(account=self.account).exists())

    def test_projection_is_separate_from_recorded_cash_and_exposes_missing_rates(self):
        end = date(self.today.year, self.today.month, monthrange(self.today.year, self.today.month)[1])
        BankMovement.objects.create(user=self.user, account=self.account, effective_date=end, direction='DEBIT', amount='50', description='Known expense')
        result = monthly_outlook(self.user, self.month)
        self.assertEqual(result['projected_available'], Decimal('1150'))
        self.assertEqual(result['recorded']['available_total'], Decimal('1150' if end == self.today else '1200'))
        self.account.currency = 'USD'; self.account.save()
        result = monthly_outlook(self.user, self.month)
        self.assertFalse(result['complete'])
        self.assertEqual(result['missing_currencies'], ['USD'])

    def test_monthly_page_tools_legacy_bookmarks_and_owned_goal_search(self):
        self.client.force_login(self.user)
        self.goal(name='Emergency')
        self.goal(name='Travel')
        response = self.client.get(reverse('planning:index'))
        self.assertContains(response, 'data-live-results="monthly-results"')
        self.assertContains(response, 'After known commitments')
        self.assertNotContains(response, reverse('sandbox:simulation'))
        self.assertRedirects(self.client.get(reverse('planning:budgets'), {'month': '2024-02'}), reverse('planning:index') + '?month=2024-02#budgets')
        self.assertContains(self.client.get(reverse('planning:tools'), follow=True), reverse('sandbox:simulation'))
        response = self.client.get(reverse('planning:goals'), {'q': 'emerg'})
        self.assertContains(response, 'Emergency')
        self.assertNotContains(response, 'Travel')
        unsupported = self.client.get(reverse('planning:index'), {'month': '2035-12'})
        self.assertContains(unsupported, 'Cash projections cover')
