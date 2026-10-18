# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Current valuation, historical FX recovery and scoped investment navigation."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserPreference
from banking.models import Bank, BankAccount, ExchangeRate
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import historical_value_in_base, refresh_fx_snapshot


class InvestmentFxReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('fx-review')
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.bank = Bank.objects.create(user=self.user, name='Review bank')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Dollar fund')
        self.asset = Asset.objects.create(user=self.user, name='Dollar balance', code='USD',
            currency='USD', asset_class='LIQUIDITY', valuation_mode='MONETARY',
            opening_balance=Decimal('100'), opening_product=self.product)

    def rate(self, effective_date=None, **kwargs):
        values = dict(user=self.user, from_currency='USD', to_currency='BRL',
                      rate=Decimal('5'), effective_date=effective_date or self.today)
        values.update(kwargs)
        return ExchangeRate.objects.create(**values)

    def operation(self):
        operation = Investment.objects.create(user=self.user, product=self.product, asset=self.asset,
            kind='YIELD', amount=Decimal('10'), date=self.today - timedelta(days=2))
        refresh_fx_snapshot(operation)
        return operation

    def data(self, operation, **kwargs):
        values = dict(product=self.product.pk, asset=self.asset.pk, kind='YIELD',
            yield_input_mode='YIELD_AMOUNT', amount='10', fees='0', date=operation.date.isoformat())
        values.update(kwargs)
        return values

    def test_current_total_does_not_inherit_missing_historical_opening_rate(self):
        self.rate()
        response = self.client.get(reverse('investments:list'))
        self.assertEqual(response.context['simulated_total'], Decimal('500'))
        self.assertEqual(response.context['missing_rate_currencies'], [])
        self.assertEqual(response.context['native_totals'], [('USD', Decimal('100'))])
        self.assertNotContains(response, 'Current total incomplete')
        self.assertNotIn('chart_total', response.context)
        charts = self.client.get(reverse('investments:charts'))
        issue = charts.context['chart_fx_issues'][0]
        self.assertEqual(issue['reason'], 'opening')
        self.assertLess(issue['date'], self.today)
        self.assertIn('from_currency=USD&to_currency=BRL', issue['rate_url'])
        self.assertContains(charts, 'Historical conversion incomplete')

    def test_inverse_rate_and_zero_native_balance(self):
        self.rate(from_currency='BRL', to_currency='USD', rate=Decimal('0.2'))
        response = self.client.get(reverse('investments:list'))
        self.assertEqual(response.context['simulated_total'], Decimal('500'))
        self.assertEqual(response.context['valuation_rates'][0].from_currency, 'BRL')
        ExchangeRate.objects.all().delete()
        account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash', currency='USD')
        Investment.objects.create(user=self.user, product=self.product, asset=self.asset,
            kind='WITHDRAWAL', amount=Decimal('100'), date=self.today,
            destination_account=account, cash_amount=Decimal('100'))
        response = self.client.get(reverse('investments:list'))
        self.assertEqual(response.context['simulated_total'], Decimal('0'))
        self.assertEqual(response.context['missing_rate_currencies'], [])

    def test_missing_current_rate_is_partial_and_preserves_native_value(self):
        response = self.client.get(reverse('investments:list'))
        self.assertEqual(response.context['missing_rate_currencies'], ['USD'])
        self.assertContains(response, 'Partial total')
        self.assertContains(response, reverse('banking:exchange_rates'))

    def test_native_history_needs_no_fx_after_changing_reporting_currency(self):
        self.rate(self.today - timedelta(days=3))
        operation = self.operation()
        self.assertEqual(historical_value_in_base(self.user, operation, 'USD'), Decimal('10'))
        preference = UserPreference.for_user(self.user)
        preference.base_currency = 'USD'
        preference.save()
        charts = self.client.get(reverse('investments:charts'))
        self.assertEqual(charts.context['chart_missing_rate_currencies'], [])
        operation.refresh_from_db()
        self.assertEqual(operation.fx_rate, Decimal('5'))
        self.assertEqual(operation.fx_target_currency, 'BRL')

    def test_explicit_capture_repairs_missing_evidence_without_changing_native_amount(self):
        operation = self.operation()
        url = reverse('investments:update', args=[operation.pk])
        response = self.client.post(url, self.data(operation, capture_missing_fx='on'))
        self.assertFormError(response.context['form'], 'capture_missing_fx',
                             'Register an exchange rate on or before the operation date first.')
        self.assertTrue(response.context['form']['capture_missing_fx'].value())
        operation.refresh_from_db()
        self.assertEqual(operation.fx_snapshot_status, 'UNKNOWN')
        self.rate(operation.date)
        response = self.client.post(url, self.data(operation, capture_missing_fx='on'))
        self.assertEqual(response.status_code, 302)
        operation.refresh_from_db()
        self.assertEqual(operation.fx_snapshot_status, 'CAPTURED')
        self.assertEqual(operation.fx_rate, Decimal('5'))
        self.assertEqual(operation.amount, Decimal('10'))
        self.assertIsNone(operation.bank_movement_id)
        rate = ExchangeRate.objects.get(user=self.user)
        rate.rate = Decimal('9')
        rate.save()
        self.client.post(url, self.data(operation, capture_missing_fx='on', notes='Description'))
        operation.refresh_from_db()
        self.assertEqual(operation.fx_rate, Decimal('5'))

    def test_chart_snapshot_mismatch_explains_saved_target_and_has_owned_editor(self):
        self.rate(self.today - timedelta(days=3))
        operation = self.operation()
        preference = UserPreference.for_user(self.user)
        preference.base_currency = 'EUR'
        preference.save()
        response = self.client.get(reverse('investments:charts'))
        issue = next(row for row in response.context['chart_fx_issues'] if row.get('operation_url'))
        self.assertEqual(issue['reason'], 'base')
        self.assertEqual(issue['snapshot_target'], 'BRL')
        self.assertContains(response, reverse('accounts:settings'))
        self.assertEqual(issue['operation_url'], reverse('investments:update', args=[operation.pk]))

    def test_unknown_evidence_does_not_claim_a_conversion_was_saved_in_another_base(self):
        self.operation()
        preference = UserPreference.for_user(self.user)
        preference.base_currency = 'EUR'
        preference.save()
        response = self.client.get(reverse('investments:charts'))
        issue = next(row for row in response.context['chart_fx_issues'] if row.get('operation_url'))
        self.assertEqual(issue['reason'], 'snapshot')
        self.assertIn('to_currency=EUR', issue['rate_url'])

    def test_shortcuts_prefill_only_owned_records(self):
        response = self.client.get(reverse('investments:create'),
                                   {'product': self.product.pk, 'asset': self.asset.pk})
        self.assertEqual(response.context['form']['product'].value(), str(self.product.pk))
        self.assertEqual(response.context['form']['asset'].value(), str(self.asset.pk))
        self.client.force_login(get_user_model().objects.create_user('fx-other'))
        response = self.client.get(reverse('investments:create'),
                                   {'product': self.product.pk, 'asset': self.asset.pk})
        self.assertFalse(response.context['form']['product'].value())
        self.assertFalse(response.context['form']['asset'].value())
        self.assertNotContains(response, 'Dollar fund')

    def test_operation_filters_use_currency_class_and_valid_date_range(self):
        operation = self.operation()
        url = reverse('investments:operations')
        values = dict(currency='USD', asset_class='LIQUIDITY',
                      date_from=operation.date.isoformat(), date_to=operation.date.isoformat())
        self.assertEqual(self.client.get(url, values).context['paginator'].count, 1)
        self.assertEqual(self.client.get(url, {**values, 'currency': 'BRL'}).context['paginator'].count, 0)
        invalid = self.client.get(url, {**values, 'date_from': self.today.isoformat()})
        self.assertEqual(invalid.context['paginator'].count, 0)
        self.assertTrue(invalid.context['operation_filter'].errors)
        self.assertContains(invalid, 'The end date must be on or after the start date.')
        self.assertEqual(self.client.get(url, {'currency': 'invalid'}).context['paginator'].count, 0)

    def test_dated_rate_shortcut_prefills_context_without_a_guessed_price(self):
        response = self.client.get(reverse('banking:exchange_rate_create'),
            {'from_currency': 'USD', 'to_currency': 'BRL', 'effective_date': self.today.isoformat(), 'rate': '999'})
        form = response.context['form']
        self.assertEqual(form['from_currency'].value(), 'USD')
        self.assertEqual(form['effective_date'].value(), self.today)
        self.assertFalse(form['rate'].value())
