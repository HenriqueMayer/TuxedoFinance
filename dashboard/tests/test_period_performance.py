"""Period performance coverage for dashboard."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
from banking.models import CreditCard
from categories.models import Category
from dashboard.services import get_dashboard_summary
from investments.models import Asset, Investment, InvestmentProduct
from transactions.models import Transaction
from dashboard.tests.fixtures import DashboardFixture


class DashboardPeriodPerformanceTests(DashboardFixture):
    @patch(
        'dashboard.services.timezone.localdate', return_value=date(2026, 9, 15)
    )
    def test_current_month_splits_modeled_activity_at_today(self, localdate):
        food = Category.objects.create(user=self.user, name='Food')
        rent = Category.objects.create(user=self.user, name='Rent')
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Installment card',
            closing_day=31,
            due_day=28,
        )
        self.transaction(
            title='Salary',
            amount='200.00',
            transaction_type=Transaction.TransactionType.INCOME,
            date=date(2026, 9, 5),
        )
        self.transaction(amount='30.00', category=food, date=date(2026, 9, 10))
        self.transaction(amount='40.00', category=rent, date=date(2026, 9, 20))
        self.transaction(
            amount='50.00',
            category=rent,
            date=date(2026, 8, 20),
            is_fixed=True,
        )
        self.transaction(
            amount='60.00',
            category=food,
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
            installments=2,
            date=date(2026, 8, 5),
        )

        summary = get_dashboard_summary(self.user, 2026, 9)

        self.assertEqual(summary['period_kind'], 'current')
        self.assertEqual(summary['period_cutoff'], date(2026, 9, 15))
        self.assertEqual(
            summary['performance']['through_cutoff']['income'],
            Decimal('200.00'),
        )
        self.assertEqual(
            summary['performance']['through_cutoff']['expenses'],
            Decimal('60.00'),
        )
        self.assertEqual(
            summary['performance']['remaining']['expenses'],
            Decimal('90.00'),
        )
        self.assertEqual(
            summary['performance']['full_month']['expenses'],
            Decimal('150.00'),
        )
        self.assertEqual(
            [(row['name'], row['total']) for row in summary['expense_categories']],
            [('Food', Decimal('60.00'))],
        )

    @patch(
        'dashboard.services.timezone.localdate', return_value=date(2026, 9, 15)
    )
    def test_past_is_complete_and_future_is_entirely_planned(self, localdate):
        self.transaction(amount='75.00', date=date(2026, 8, 25))
        self.transaction(
            amount='125.00',
            transaction_type=Transaction.TransactionType.INCOME,
            date=date(2026, 10, 5),
        )

        past = get_dashboard_summary(self.user, 2026, 8)
        future = get_dashboard_summary(self.user, 2026, 10)

        self.assertEqual(past['period_kind'], 'past')
        self.assertEqual(
            past['performance']['through_cutoff']['expenses'], Decimal('75.00')
        )
        self.assertEqual(
            past['performance']['remaining']['expenses'], Decimal('0.00')
        )
        self.assertEqual(future['period_kind'], 'future')
        self.assertEqual(
            future['performance']['through_cutoff']['income'], Decimal('0.00')
        )
        self.assertEqual(
            future['performance']['remaining']['income'], Decimal('125.00')
        )
        self.assertEqual(
            future['performance']['full_month']['income'], Decimal('125.00')
        )

    def test_fixed_recurrence_clamps_to_last_day_for_cutoff(self):
        self.transaction(amount='80.00', date=date(2027, 1, 31), is_fixed=True)

        with patch(
            'dashboard.services.timezone.localdate', return_value=date(2027, 2, 27)
        ):
            before = get_dashboard_summary(self.user, 2027, 2)
        with patch(
            'dashboard.services.timezone.localdate', return_value=date(2027, 2, 28)
        ):
            on_date = get_dashboard_summary(self.user, 2027, 2)

        self.assertEqual(
            before['performance']['through_cutoff']['expenses'], Decimal('0.00')
        )
        self.assertEqual(
            before['performance']['remaining']['expenses'], Decimal('80.00')
        )
        self.assertEqual(
            on_date['performance']['through_cutoff']['expenses'], Decimal('80.00')
        )

    @patch(
        'dashboard.services.timezone.localdate', return_value=date(2026, 9, 15)
    )
    def test_investments_and_withdrawals_follow_the_cutoff(self, localdate):
        product = InvestmentProduct.objects.create(
            user=self.user, bank=self.bank, name='Brokerage'
        )
        asset = Asset.objects.create(
            user=self.user,
            name='Fund',
            code='CUT',
            asset_class=Asset.AssetClass.FIXED_INCOME,
            currency='BRL',
        )
        Investment.objects.create(
            user=self.user,
            product=product,
            asset=asset,
            kind=Investment.Kind.DEPOSIT,
            quantity='1',
            unit_price='100',
            cash_amount='100.00',
            source_account=self.account,
            date=date(2026, 9, 10),
        )
        Investment.objects.create(
            user=self.user,
            product=product,
            asset=asset,
            kind=Investment.Kind.DEPOSIT,
            quantity='2',
            unit_price='100',
            cash_amount='200.00',
            source_account=self.account,
            date=date(2026, 9, 20),
        )
        Investment.objects.create(
            user=self.user,
            product=product,
            asset=asset,
            kind=Investment.Kind.WITHDRAWAL,
            quantity='0.25',
            unit_price='100',
            cash_amount='25.00',
            destination_account=self.account,
            date=date(2026, 9, 12),
        )

        summary = get_dashboard_summary(self.user, 2026, 9)

        self.assertEqual(
            summary['performance']['through_cutoff']['investments'],
            Decimal('100.0000000000000000'),
        )
        self.assertEqual(
            summary['performance']['remaining']['investments'],
            Decimal('200.0000000000000000'),
        )
        self.assertEqual(
            summary['performance']['through_cutoff']['withdrawals'],
            Decimal('25.00'),
        )

    @patch(
        'dashboard.services.timezone.localdate', return_value=date(2026, 9, 15)
    )
    def test_category_breakdown_is_ranked_and_limited_to_six(self, localdate):
        for index in range(1, 8):
            category = Category.objects.create(
                user=self.user, name=f'Category {index}'
            )
            self.transaction(
                amount=f'{index * 10}.00',
                category=category,
                date=date(2026, 9, 5),
            )

        summary = get_dashboard_summary(self.user, 2026, 9)

        self.assertEqual(len(summary['expense_categories']), 6)
        self.assertEqual(summary['expense_categories'][0]['name'], 'Category 7')
        self.assertEqual(summary['expense_categories'][0]['bar_width'], 100.0)
        self.assertNotIn(
            'Category 1', [row['name'] for row in summary['expense_categories']]
        )
