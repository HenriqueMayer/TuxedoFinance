# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Account baselines constrain cash legs independently of position baselines."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import sync_investment_ledger


class InvestmentEndpointDateTests(TestCase):
    def setUp(self):
        self.day = date(2026, 1, 15)
        self.user = get_user_model().objects.create_user('investment-dates')
        self.bank = Bank.objects.create(user=self.user, name='Local')
        self.account = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Cash', currency='BRL',
            opening_balance=Decimal('1000'), opening_date=self.day,
        )
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Portfolio')
        self.asset = Asset.objects.create(
            user=self.user, name='Monetary', code='DATE', asset_class='LIQUIDITY',
            currency='BRL', valuation_mode='MONETARY', opening_product=self.product,
            opening_balance=Decimal('200'), opening_date=date(2026, 1, 1),
        )
        self.client.force_login(self.user)

    def values(self, kind='DEPOSIT', **overrides):
        values = dict(
            product=self.product.pk, asset=self.asset.pk, kind=kind, amount='100',
            cash_amount='100', fees='0', date=self.day.isoformat(),
        )
        if kind == 'DEPOSIT':
            values.update(funding_source='ACCOUNT', source_account=self.account.pk)
        else:
            values['destination_account'] = self.account.pk
        return values | overrides

    def test_deposit_and_withdrawal_reject_before_account_opening_atomically(self):
        for kind in ('DEPOSIT', 'WITHDRAWAL'):
            with self.subTest(kind=kind):
                response = self.client.post(reverse('investments:create'), self.values(
                    kind, date=(self.day - timedelta(days=1)).isoformat()))
                self.assertContains(response, 'The operation cannot precede')
                self.assertFalse(Investment.objects.exists())
                self.assertFalse(BankMovement.objects.exists())

    def test_edit_to_prebaseline_date_retains_original_source_and_cash_leg(self):
        response = self.client.post(reverse('investments:create'), self.values())
        self.assertEqual(response.status_code, 302)
        operation = Investment.objects.get()
        before = list(BankMovement.objects.values())
        response = self.client.post(reverse('investments:update', args=[operation.pk]), self.values(
            date=(self.day - timedelta(days=1)).isoformat()))
        self.assertContains(response, 'The operation cannot precede')
        operation.refresh_from_db()
        self.assertEqual(operation.date, self.day)
        self.assertEqual(before, list(BankMovement.objects.values()))

    def test_unknown_account_baseline_does_not_invent_a_date(self):
        self.account.opening_date = None
        self.account.save(update_fields=['opening_date'])
        response = self.client.post(reverse('investments:create'), self.values(
            date=(self.day - timedelta(days=1)).isoformat()))
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertIsNone(self.account.opening_date)
        self.assertEqual(Investment.objects.get().bank_movement.effective_date, self.day - timedelta(days=1))

    def test_position_only_yield_does_not_require_an_account_date(self):
        operation = Investment(
            user=self.user, product=self.product, asset=self.asset, kind='YIELD',
            amount=Decimal('1'), date=self.day - timedelta(days=1),
        )
        operation.full_clean()
        operation.save()
        sync_investment_ledger(operation)
        self.assertFalse(BankMovement.objects.exists())

    def test_cash_endpoint_ownership_remains_enforced(self):
        other = get_user_model().objects.create_user('private-investment-account')
        other_bank = Bank.objects.create(user=other, name='Private')
        other_account = BankAccount.objects.create(user=other, bank=other_bank, name='Private', currency='BRL')
        operation = Investment(
            user=self.user, product=self.product, asset=self.asset, kind='DEPOSIT', amount=Decimal('1'),
            cash_amount=Decimal('1'), source_account=other_account, date=self.day,
        )
        with self.assertRaises(ValidationError) as caught:
            operation.full_clean()
        self.assertIn('source_account', caught.exception.message_dict)
        self.assertFalse(Investment.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_delete_confirmation_uses_the_holdings_native_measure(self):
        monetary = Investment.objects.create(
            user=self.user, product=self.product, asset=self.asset,
            kind='YIELD', amount=Decimal('12.34'), date=self.day,
        )
        response = self.client.get(reverse('investments:delete', args=[monetary.pk]))
        self.assertRegex(response.content.decode(), r'BRL 12[,.]34')
        self.assertNotContains(response, 'units, gross')
        units = Asset.objects.create(
            user=self.user, name='Units', code='UNIT', asset_class='EQUITY',
            currency='BRL', valuation_mode='UNITS',
        )
        operation = Investment.objects.create(
            user=self.user, product=self.product, asset=units, kind='YIELD',
            quantity=Decimal('1.12345678'), unit_price=Decimal('9.98765432'), date=self.day,
        )
        response = self.client.get(reverse('investments:delete', args=[operation.pk]))
        self.assertRegex(response.content.decode(), r'1[,.]12345678 units, gross')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="next"')
        self.assertEqual(Investment.objects.count(), 2)
        self.assertFalse(BankMovement.objects.exists())
