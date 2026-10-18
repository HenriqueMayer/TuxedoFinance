"""Monetary yield coverage for investments."""

from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from investments.forms import InvestmentForm
from investments.models import Asset, Investment
from investments.services import YIELD_INPUT_AMOUNT, YIELD_INPUT_ENDING_BALANCE, calculate_monetary_yield
from investments.tests.fixtures import InvestmentFixtureMixin


BASE = 'BRL'


class MonetaryYieldTests(InvestmentFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.savings = Asset.objects.create(
            user=self.user,
            name='Savings pot',
            code='POT',
            asset_class=Asset.AssetClass.LIQUIDITY,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.MONETARY,
            opening_balance=Decimal('1000.00'),
            opening_product=self.product,
        )

    def yield_data(self, **overrides):
        data = {
            'product': self.product.pk,
            'asset': self.savings.pk,
            'kind': Investment.Kind.YIELD,
            'yield_input_mode': YIELD_INPUT_ENDING_BALANCE,
            'ending_balance': '1200.00',
            'amount': '',
            'quantity': '',
            'unit_price': '',
            'fees': '0.00',
            'cash_amount': '',
            'source_account': '',
            'source_program': '',
            'source_points': '',
            'destination_account': '',
            'date': timezone.localdate(),
            'reason': '',
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_ending_balance_calculates_the_yield(self):
        calculation = calculate_monetary_yield(
            user=self.user,
            product=self.product,
            asset=self.savings,
            operation_date=timezone.localdate(),
            input_mode=YIELD_INPUT_ENDING_BALANCE,
            value=Decimal('1200.00'),
        )

        self.assertEqual(calculation.previous_balance, Decimal('1000.00'))
        self.assertEqual(calculation.yield_amount, Decimal('200.00'))
        self.assertEqual(calculation.ending_balance, Decimal('1200.00'))

    def test_direct_yield_calculates_the_ending_balance(self):
        calculation = calculate_monetary_yield(
            user=self.user,
            product=self.product,
            asset=self.savings,
            operation_date=timezone.localdate(),
            input_mode=YIELD_INPUT_AMOUNT,
            value=Decimal('200.00'),
        )

        self.assertEqual(calculation.ending_balance, Decimal('1200.00'))

    def test_form_rejects_an_unchanged_or_lower_ending_balance(self):
        unchanged = InvestmentForm(
            self.yield_data(ending_balance='1000.00'), user=self.user
        )
        lower = InvestmentForm(
            self.yield_data(ending_balance='999.99'), user=self.user
        )

        self.assertFalse(unchanged.is_valid())
        self.assertIn('ending_balance', unchanged.errors)
        self.assertFalse(lower.is_valid())
        self.assertIn('ending_balance', lower.errors)

    def test_operation_form_marks_nested_yield_error_groups(self):
        ending_balance_response = self.client.post(
            reverse('investments:create'),
            self.yield_data(
                yield_input_mode=YIELD_INPUT_AMOUNT,
                ending_balance='0',
                amount='200.00',
            ),
        )

        self.assertEqual(ending_balance_response.status_code, 200)
        self.assertIn('ending_balance', ending_balance_response.context['form'].errors)
        ending_balance_html = ending_balance_response.content.decode()
        # The mode selector and value fields are siblings in keyboard order;
        # the monetary section is the parent that must preserve value errors.
        self.assertRegex(
            ending_balance_html,
            r'id="money-fields"\s+data-has-errors="true"',
        )
        self.assertRegex(
            ending_balance_html,
            r'id="ending-balance-field"\s+data-has-errors="true"',
        )

        amount_response = self.client.post(
            reverse('investments:create'),
            self.yield_data(amount='not-a-number'),
        )

        self.assertEqual(amount_response.status_code, 200)
        self.assertIn('amount', amount_response.context['form'].errors)
        self.assertRegex(
            amount_response.content.decode(),
            r'id="regular-amount-field"\s+data-has-errors="true"',
        )
        self.assertEqual(Investment.objects.count(), 0)

    def test_same_day_calculation_uses_registration_order_when_editing(self):
        first = Investment.objects.create(
            user=self.user, product=self.product, asset=self.savings,
            kind=Investment.Kind.YIELD, amount=Decimal('25.00'), date=timezone.localdate(),
        )
        Investment.objects.create(
            user=self.user, product=self.product, asset=self.savings,
            kind=Investment.Kind.YIELD, amount=Decimal('75.00'), date=timezone.localdate(),
        )

        calculation = calculate_monetary_yield(
            user=self.user,
            product=self.product,
            asset=self.savings,
            operation_date=timezone.localdate(),
            input_mode=YIELD_INPUT_ENDING_BALANCE,
            value=Decimal('1100.00'),
            operation=first,
        )

        self.assertEqual(calculation.previous_balance, Decimal('1000.00'))
        self.assertEqual(calculation.yield_amount, Decimal('100.00'))

    def test_preview_is_non_persistent_and_create_stores_only_the_yield(self):
        preview = self.client.post(
            reverse('investments:yield_preview'), self.yield_data()
        )

        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'Calculated yield')
        self.assertContains(preview, 'BRL 200,00')
        self.assertEqual(Investment.objects.count(), 0)

        response = self.client.post(reverse('investments:create'), self.yield_data())

        self.assertRedirects(response, reverse('investments:operations'))
        operation = Investment.objects.get(asset=self.savings)
        self.assertEqual(operation.amount, Decimal('200.00'))
        self.assertIsNone(operation.bank_movement)

    def test_editing_a_monetary_yield_reconstructs_its_ending_balance(self):
        operation = Investment.objects.create(
            user=self.user, product=self.product, asset=self.savings,
            kind=Investment.Kind.YIELD, amount=Decimal('200.00'), date=timezone.localdate(),
        )

        form = InvestmentForm(user=self.user, instance=operation)

        self.assertEqual(form.initial['yield_input_mode'], YIELD_INPUT_ENDING_BALANCE)
        self.assertEqual(form.initial['ending_balance'], Decimal('1200.00'))
