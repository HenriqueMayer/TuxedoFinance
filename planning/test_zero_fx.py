# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Zero cash needs no FX, while positive obligations and shortages still do."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from banking.models import Bank, BankAccount, CardInvoice, CreditCard, ExchangeRate
from banking.services import get_planning_availability
from investments.models import Asset, InvestmentProduct
from planning.monthly import monthly_outlook


class ZeroFxPlanningTests(TestCase):
    def setUp(self):
        self.day = date(2026, 10, 16)
        self.user = get_user_model().objects.create_user('zero-fx-planning')
        self.bank = Bank.objects.create(user=self.user, name='Local')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Empty USD', currency='USD')
        product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Empty cash pot', purpose='MONTHLY_CASH')
        Asset.objects.create(user=self.user, name='Empty cash', code='ZEROUSD', currency='USD',
                             asset_class='LIQUIDITY', valuation_mode='MONETARY', opening_product=product)

    def test_zero_account_and_cash_pot_do_not_require_a_rate(self):
        available = get_planning_availability(self.user, self.day)
        self.assertEqual(available['missing_currencies'], [])
        self.assertEqual(available['bank_total'], Decimal('0'))
        self.assertEqual(available['pot_total'], Decimal('0'))
        self.assertEqual(available['account_rows'][0]['converted_balance'], Decimal('0'))
        self.assertEqual(available['cash_pots'][0]['base_balance'], Decimal('0'))
        with patch('django.utils.timezone.localdate', return_value=self.day):
            outlook = monthly_outlook(self.user, self.day.replace(day=1))
        self.assertTrue(outlook['complete'])
        self.assertEqual(outlook['missing_currencies'], [])
        self.assertEqual(outlook['projected_available'], Decimal('0'))

    def test_zero_cash_does_not_hide_a_nonzero_reserve_shortfall(self):
        self.account.reserved_amount = Decimal('10')
        self.account.save(update_fields=['reserved_amount'])
        available = get_planning_availability(self.user, self.day)
        row = available['account_rows'][0]
        self.assertEqual(row['converted_balance'], Decimal('0'))
        self.assertEqual(row['shortfall'], Decimal('10'))
        self.assertIsNone(row['converted_shortfall'])
        self.assertEqual(available['missing_currencies'], ['USD'])

    def test_zero_cash_does_not_hide_unpaid_foreign_invoice(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual', closing_day=1, due_day=31)
        CardInvoice.objects.create(user=self.user, card=card, reference_month=self.day.replace(day=1),
                                   due_date=self.day, amount=Decimal('10'), manual_settlement=True)
        with patch('django.utils.timezone.localdate', return_value=self.day):
            missing = monthly_outlook(self.user, self.day.replace(day=1))
            self.assertFalse(missing['complete'])
            self.assertEqual(missing['missing_currencies'], ['USD'])
            ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
                                        rate=Decimal('5'), effective_date=self.day)
            converted = monthly_outlook(self.user, self.day.replace(day=1))
        self.assertTrue(converted['complete'])
        self.assertEqual(converted['unpaid_invoices'], Decimal('50'))
        self.assertEqual(converted['projected_available'], Decimal('-50'))
