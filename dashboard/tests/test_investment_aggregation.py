"""Investment aggregation coverage for dashboard."""

from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from dashboard.services import get_account_evolution, get_dashboard_summary
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import sync_investment_ledger
from transactions.services import sync_user_ledger
from dashboard.tests.fixtures import DashboardFixture


class InvestmentAggregationTests(DashboardFixture):
    def test_deposits_are_separate_from_transaction_expenses(self):
        product = InvestmentProduct.objects.create(
            user=self.user, bank=self.bank, name='Brokerage'
        )
        asset = Asset.objects.create(
            user=self.user,
            name='Fund',
            code='FUND',
            asset_class=Asset.AssetClass.FIXED_INCOME,
            currency='BRL',
        )
        operation = Investment.objects.create(
            user=self.user,
            product=product,
            asset=asset,
            kind=Investment.Kind.DEPOSIT,
            quantity='2',
            unit_price='100',
            cash_amount='200.00',
            source_account=self.account,
            date=timezone.localdate(),
        )
        sync_investment_ledger(operation)
        withdrawal = Investment.objects.create(
            user=self.user,
            product=product,
            asset=asset,
            kind=Investment.Kind.WITHDRAWAL,
            quantity='1',
            unit_price='100',
            cash_amount='95.00',
            destination_account=self.account,
            date=timezone.localdate(),
        )
        sync_investment_ledger(withdrawal)
        sync_user_ledger(self.user)

        summary = get_dashboard_summary(self.user)
        evolution = get_account_evolution(self.user)
        current_month = next(
            row for row in evolution['months'] if row['is_current_month']
        )
        response = self.client.get(reverse('analytics:index'))

        self.assertEqual(summary['investment_month'], Decimal('200.00'))
        self.assertEqual(summary['expense_month'], Decimal('0.00'))
        self.assertEqual(summary['income_month'], Decimal('0.00'))
        self.assertEqual(summary['current_balance'], Decimal('895.00'))
        self.assertEqual(summary['projected_balance'], Decimal('895.00'))
        self.assertEqual(summary['balance_month'], Decimal('-105.00'))
        self.assertEqual(current_month['withdrawals'], Decimal('95.00'))
        self.assertEqual(current_month['balance'], Decimal('-105.00'))
        self.assertContains(response, 'Withdrawals')
        self.assertContains(
            response,
            'Grouped bar chart of income, expenses, investments, and withdrawals per month',
        )
