"""Cash settlement and investment-flow regressions for monthly planning."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from banking.models import Bank, BankAccount, LoyaltyProgram, LoyaltyEntry
from dashboard.services import get_dashboard_summary
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import sync_investment_ledger


class InvestmentCashProjectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('cash-projection')
        self.today = timezone.localdate()
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Current', currency='BRL', opening_balance=Decimal('1000'))
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Product')
        self.asset = Asset.objects.create(user=self.user, name='Asset', code='ASSET', currency='BRL', asset_class=Asset.AssetClass.LIQUIDITY, valuation_mode=Asset.ValuationMode.MONETARY)

    def test_cash_deposit_uses_actual_debit_instead_of_gross_asset_value(self):
        operation = Investment.objects.create(user=self.user, product=self.product, asset=self.asset, kind='DEPOSIT', amount=Decimal('100'), cash_amount=Decimal('105'), source_account=self.account, date=self.today)
        sync_investment_ledger(operation)
        result = get_dashboard_summary(self.user)
        self.assertEqual(result['current_balance'], Decimal('895'))
        self.assertEqual(result['projected_balance'], Decimal('895'))
        self.assertEqual(result['investment_month'], Decimal('105'))

    def test_points_funded_deposit_does_not_reduce_cash_or_monthly_cash_flow(self):
        program = LoyaltyProgram.objects.create(user=self.user, bank=self.bank, name='Points')
        LoyaltyEntry.objects.create(user=self.user, program=program, direction='CREDIT', kind='ADJUSTMENT', amount=Decimal('1000'), date=self.today)
        operation = Investment.objects.create(user=self.user, product=self.product, asset=self.asset, kind='DEPOSIT', amount=Decimal('100'), source_program=program, source_points=Decimal('100'), date=self.today)
        sync_investment_ledger(operation)
        result = get_dashboard_summary(self.user)
        self.assertEqual(result['projected_balance'], Decimal('1000'))
        self.assertEqual(result['investment_month'], Decimal('0'))

    def test_monthly_cash_transfer_is_not_an_investment_or_a_loss_of_available_money(self):
        self.product.purpose = InvestmentProduct.Purpose.MONTHLY_CASH
        self.product.save()
        operation = Investment.objects.create(user=self.user, product=self.product, asset=self.asset, kind='DEPOSIT', amount=Decimal('300'), cash_amount=Decimal('300'), source_account=self.account, date=self.today)
        sync_investment_ledger(operation)
        result = get_dashboard_summary(self.user)
        self.assertEqual(result['projected_balance'], Decimal('700'))
        self.assertEqual(result['investment_month'], Decimal('0'))
        self.assertEqual(result['planning_availability']['available_total'], Decimal('1000'))
