from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.charts import build_donut_chart, build_instrument_chart
from banking.models import (
    Bank,
    BankAccount,
    CardInvoice,
    CreditCard,
    DebitCard,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from banking.services import create_transfer
from categories.models import Category
from dashboard.services import (
    add_months,
    get_account_evolution,
    get_dashboard_summary,
    get_expenses_by_instrument,
    get_expenses_by_recurrence,
    get_instrument_activity,
)
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import sync_investment_ledger
from transactions.models import Transaction
from transactions.services import sync_user_ledger


User = get_user_model()


class DashboardFixture(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dashboard', password='test')
        self.bank = Bank.objects.create(user=self.user, name='Bank With Spaces')
        self.account = BankAccount.objects.create(
            user=self.user,
            bank=self.bank,
            name='Main Account',
            currency='BRL',
            opening_balance='1000.00',
        )
        self.category, _ = Category.objects.get_or_create(
            user=self.user, name='Groceries'
        )
        self.client.force_login(self.user)

    def transaction(self, **overrides):
        values = {
            'user': self.user,
            'title': 'Transaction',
            'amount': Decimal('100.00'),
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category,
            'payment_channel': Transaction.PaymentChannel.PIX,
            'bank_account': self.account,
            'date': timezone.localdate(),
        }
        values.update(overrides)
        return Transaction.objects.create(**values)


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


class LedgerBalanceTests(DashboardFixture):
    def test_pix_and_debit_reduce_true_balance_immediately(self):
        self.transaction(amount='75.00')
        debit = DebitCard.objects.create(
            user=self.user, account=self.account, name='Daily Debit'
        )
        self.transaction(
            amount='25.00',
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            bank_account=None,
            debit_card=debit,
        )

        sync_user_ledger(self.user)
        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['current_balance'], Decimal('900.00'))
        self.assertEqual(summary['expense_month'], Decimal('100.00'))

    def test_card_purchase_reduces_cash_only_on_invoice_due_date(self):
        today = timezone.localdate()
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Travel Card',
            closing_day=min(today.day + 1, 31),
            due_day=min(today.day + 5, 28),
        )
        purchase = self.transaction(
            amount='120.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )
        sync_user_ledger(self.user)
        invoice = card.invoices.get(reference_month=purchase.billed_month)

        before = get_dashboard_summary(self.user)
        self.assertEqual(before['current_balance'], Decimal('1000.00'))
        self.assertEqual(before['expense_month'], Decimal('120.00'))

        due_summary = get_dashboard_summary(
            self.user, invoice.due_date.year, invoice.due_date.month
        )
        self.assertEqual(due_summary['projected_balance'], Decimal('880.00'))

    def test_card_due_day_before_closing_day_does_not_reduce_current_balance_early(self):
        today = timezone.localdate()
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='First Day Card',
            closing_day=24,
            due_day=1,
        )
        purchase = self.transaction(
            amount='120.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )
        sync_user_ledger(self.user)
        invoice = card.invoices.get(reference_month=purchase.billed_month)

        self.assertGreater(invoice.due_date, today)
        self.assertEqual(get_dashboard_summary(self.user)['current_balance'], Decimal('1000.00'))

    def test_projected_balance_includes_card_expense_in_statement_month(self):
        today = timezone.localdate()
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='First Day Card',
            closing_day=24,
            due_day=1,
        )
        self.transaction(
            amount='120.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
            date=today.replace(day=1),
        )
        sync_user_ledger(self.user)

        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['current_balance'], Decimal('1000.00'))
        self.assertEqual(summary['projected_balance'], Decimal('880.00'))
        self.assertEqual(summary['balance_month'], Decimal('-120.00'))

    def test_future_month_current_balance_starts_from_previous_projected_close(self):
        today = timezone.localdate()
        next_year, next_month = add_months(today.year, today.month, 1)
        self.transaction(
            title='Future salary',
            amount='500.00',
            transaction_type=Transaction.TransactionType.INCOME,
            date=date(next_year, next_month, 15),
            is_fixed=False,
        )
        sync_user_ledger(self.user)

        summary = get_dashboard_summary(self.user, next_year, next_month)

        self.assertEqual(summary['current_balance'], Decimal('1000.00'))
        self.assertEqual(summary['projected_balance'], Decimal('1500.00'))
        self.assertEqual(summary['balance_month'], Decimal('500.00'))

    def test_invoice_settlement_is_not_a_second_expense(self):
        today = timezone.localdate()
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='One Card',
            closing_day=31,
            due_day=28,
        )
        self.transaction(
            amount='80.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )
        sync_user_ledger(self.user)

        summary = get_dashboard_summary(self.user, today.year, today.month)
        report = get_expenses_by_instrument(self.user, today.year, today.month)

        self.assertEqual(summary['expense_month'], Decimal('80.00'))
        self.assertEqual(report['total'], Decimal('80.00'))

    def test_multicurrency_conversion_and_missing_rate_are_explicit(self):
        usd = BankAccount.objects.create(
            user=self.user,
            bank=self.bank,
            name='Dollar Account',
            currency='USD',
            opening_balance='10.00',
        )
        eur = BankAccount.objects.create(
            user=self.user,
            bank=self.bank,
            name='Euro Account',
            currency='EUR',
            opening_balance='20.00',
        )
        ExchangeRate.objects.create(
            user=self.user,
            from_currency='USD',
            to_currency='BRL',
            rate='5.00000000',
            effective_date=timezone.localdate(),
        )

        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['current_balance'], Decimal('1050.0000000000'))
        self.assertEqual(summary['missing_currencies'], ['EUR', 'USD'])
        native = {row['account'].pk: row for row in summary['account_balances']}
        self.assertEqual(native[usd.pk]['native_balance'], Decimal('10.00'))
        self.assertIsNone(native[eur.pk]['converted_balance'])

    def test_own_transfer_changes_accounts_but_not_reported_flow(self):
        second = BankAccount.objects.create(
            user=self.user,
            bank=self.bank,
            name='Savings',
            currency='BRL',
            opening_balance='0.00',
        )
        create_transfer(
            user=self.user,
            source_account=self.account,
            destination_account=second,
            source_amount='200.00',
            destination_amount='200.00',
            date=timezone.localdate(),
        )

        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['current_balance'], Decimal('1000.00'))
        self.assertEqual(summary['income_month'], Decimal('0.00'))
        self.assertEqual(summary['expense_month'], Decimal('0.00'))

    def test_points_purchase_and_iof_are_expenses_without_transactions(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Travel')
        LoyaltyEntry.objects.create(
            user=self.user,
            program=program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.PURCHASE,
            amount='1000.00',
            funding_account=self.account,
            cash_amount='25.00',
            date=timezone.localdate(),
        )
        RewardRedemption.objects.create(
            user=self.user,
            program=program,
            points='100.00',
            target_account=self.account,
            target_amount='10.00',
            iof_amount='2.00',
            iof_account=self.account,
            date=timezone.localdate(),
        )

        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['expense_month'], Decimal('27.00'))


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
        response = self.client.get(reverse('dashboard:reports'))

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


class InstrumentReportTests(DashboardFixture):
    def test_donut_tooltip_has_reserved_space_below_the_ring(self):
        chart = build_donut_chart(
            [
                {
                    'name': 'Installments',
                    'tone': 'installment',
                    'value': 100,
                    'share': 100,
                }
            ]
        )

        self.assertGreaterEqual(chart['tooltip_y'], chart['width'])
        self.assertGreaterEqual(
            chart['height'], chart['tooltip_y'] + chart['tooltip_height']
        )

    def test_instrument_chart_adds_visual_gaps_between_banks(self):
        labels = [
            {'short_label': 'One', 'bank_label': 'Bank A'},
            {'short_label': 'Two', 'bank_label': 'Bank A'},
            {'short_label': 'Three', 'bank_label': 'Bank B'},
        ]
        chart = build_instrument_chart(
            labels,
            [
                {'name': 'Expenses', 'tone': 'expense', 'values': [3, 2, 1]},
                {'name': 'Income', 'tone': 'income', 'values': [0, 0, 0]},
            ],
        )

        same_bank_gap = chart['groups'][1]['center'] - chart['groups'][0]['center']
        next_bank_gap = chart['groups'][2]['center'] - chart['groups'][1]['center']
        self.assertGreater(next_bank_gap, same_bank_gap)
        self.assertEqual(
            [group['label'] for group in chart['bank_groups']],
            ['Bank A', 'Bank B'],
        )

    def test_combined_activity_ranks_accounts_and_cards_by_total_moved(self):
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Combined Card',
            closing_day=31,
            due_day=28,
        )
        self.transaction(amount='20.00')
        self.transaction(
            amount='80.00',
            transaction_type=Transaction.TransactionType.INCOME,
        )
        self.transaction(
            amount='50.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )

        activity = get_instrument_activity(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual(
            [row['key'] for row in activity['instruments']],
            [f'account:{self.account.pk}', f'cc:{card.pk}'],
        )
        account = activity['instruments'][0]
        self.assertEqual(account['short_label'], 'Main Account')
        self.assertEqual(account['bank_label'], 'Bank With Spaces')
        self.assertEqual(account['expense_total'], Decimal('20.00'))
        self.assertEqual(account['income_total'], Decimal('80.00'))
        self.assertEqual(activity['expense_total'], Decimal('70.00'))
        self.assertEqual(activity['income_total'], Decimal('80.00'))

    def test_combined_activity_keeps_instruments_from_the_same_bank_together(self):
        other_bank = Bank.objects.create(user=self.user, name='Other Bank')
        other_account = BankAccount.objects.create(
            user=self.user,
            bank=other_bank,
            name='Other Account',
            currency='BRL',
        )
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Same Bank Card',
            closing_day=31,
            due_day=28,
        )
        self.transaction(amount='100.00')
        self.transaction(
            amount='90.00',
            payment_channel=Transaction.PaymentChannel.PIX,
            bank_account=other_account,
        )
        self.transaction(
            amount='80.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )

        activity = get_instrument_activity(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual(
            [row['bank_label'] for row in activity['instruments']],
            ['Bank With Spaces', 'Bank With Spaces', 'Other Bank'],
        )

    def test_account_card_grouping_uses_stable_ids_and_isolated_users(self):
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Blue Card With Spaces',
            closing_day=31,
            due_day=28,
        )
        self.transaction(amount='20.00')
        self.transaction(
            amount='30.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )
        other = User.objects.create_user('other')
        other_bank = Bank.objects.create(user=other, name='Other')
        other_account = BankAccount.objects.create(
            user=other,
            bank=other_bank,
            name='Hidden',
            currency='BRL',
        )
        other_category = Category.objects.create(user=other, name='Private')
        Transaction.objects.create(
            user=other,
            title='Hidden',
            amount='999.00',
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=other_category,
            payment_channel=Transaction.PaymentChannel.PIX,
            bank_account=other_account,
            date=timezone.localdate(),
        )

        breakdown = get_expenses_by_instrument(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual({row['key'] for row in breakdown['instruments']}, {
            f'account:{self.account.pk}', f'cc:{card.pk}'
        })
        self.assertEqual(breakdown['total'], Decimal('50.00'))
        self.assertTrue(all('Bank With Spaces >' in row['label'] for row in breakdown['instruments']))

    def test_id_drilldown_handles_labels_with_spaces_and_htmx(self):
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Blue Card With Spaces',
            closing_day=31,
            due_day=28,
        )
        self.transaction(
            amount='25.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )
        response = self.client.get(reverse('dashboard:reports'))

        self.assertContains(response, f'expense_instrument=cc%3A{card.pk}')
        self.assertContains(response, 'Bank With Spaces &gt; Main Account / Blue Card With Spaces')
        self.assertContains(response, 'Blue Card With Spaces')
        self.assertContains(response, 'Bank With Spaces')
        self.assertContains(response, 'data-scroll-target="instrument-categories-expense"')

        drilldown = self.client.get(
            reverse('dashboard:reports'),
            {'expense_instrument': f'cc:{card.pk}'},
            HTTP_HX_REQUEST='true',
        )
        self.assertNotContains(drilldown, '<html')
        self.assertContains(drilldown, 'id="reports-charts"')
        self.assertContains(drilldown, 'Categories in')
        self.assertContains(drilldown, 'Groceries')

    def test_income_bar_opens_income_categories(self):
        self.transaction(
            amount='125.00',
            transaction_type=Transaction.TransactionType.INCOME,
        )
        response = self.client.get(reverse('dashboard:reports'))

        self.assertContains(response, f'income_account=account%3A{self.account.pk}')
        self.assertContains(response, 'data-scroll-target="account-categories-income"')

        drilldown = self.client.get(
            reverse('dashboard:reports'),
            {'income_account': f'account:{self.account.pk}'},
            HTTP_HX_REQUEST='true',
        )
        self.assertContains(drilldown, 'received on')
        self.assertContains(drilldown, 'Groceries')

    def test_installment_shares_are_rounded_to_one_decimal(self):
        self.transaction(amount='542.00')
        self.transaction(amount='458.00', is_fixed=True)

        breakdown = get_expenses_by_recurrence(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual(sum(row['share'] for row in breakdown['slices']), 100.0)
        self.assertTrue(
            all(row['share'] == round(row['share'], 1) for row in breakdown['slices'])
        )


class DashboardPageContractTests(DashboardFixture):
    def test_index_translates_new_dashboard_copy_to_portuguese(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'pt-br'

        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, 'Desempenho mensal')
        self.assertContains(response, 'Despesas por categoria')
        self.assertContains(response, 'Perspectiva de seis meses')
        self.assertNotContains(response, 'Posição dos saldos')

    def test_index_explains_current_month_performance_and_categories(self):
        self.transaction(amount='45.00', date=timezone.localdate())

        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, 'Monthly performance')
        self.assertNotContains(response, 'Available cash today')
        self.assertNotContains(
            response,
            'What is available now and where this month is heading.',
        )
        self.assertContains(response, 'Income through today')
        self.assertContains(response, 'remaining planned')
        self.assertContains(response, 'Expenses by category')
        self.assertContains(response, 'Groceries')
        self.assertContains(
            response,
            f'category_month={timezone.localdate():%Y-%m}',
        )

    def test_index_uses_period_appropriate_past_and_future_labels(self):
        today = timezone.localdate()
        past_year, past_month = add_months(today.year, today.month, -1)
        future_year, future_month = add_months(today.year, today.month, 1)

        past = self.client.get(
            reverse('dashboard:index'),
            {'month': f'{past_year:04d}-{past_month:02d}'},
        )
        future = self.client.get(
            reverse('dashboard:index'),
            {'month': f'{future_year:04d}-{future_month:02d}'},
        )

        self.assertContains(past, 'Completed month')
        self.assertContains(past, 'Complete activity assigned to the selected month.')
        self.assertContains(future, 'Planned month')
        self.assertContains(future, 'Planned income')
        self.assertNotContains(future, 'Income through today')
        self.assertContains(future, 'Back to this month')

    def test_index_limits_live_account_and_invoice_previews(self):
        for index in range(5):
            BankAccount.objects.create(
                user=self.user,
                bank=self.bank,
                name=f'Extra account {index}',
                currency='BRL',
            )
        for index in range(6):
            card = CreditCard.objects.create(
                user=self.user,
                account=self.account,
                name=f'Card {index}',
                closing_day=20,
                due_day=28,
            )
            CardInvoice.objects.create(
                user=self.user,
                card=card,
                reference_month=date(2099, 1, 1),
                due_date=date(2099, 1, index + 1),
                amount='10.00',
            )

        with patch('dashboard.views.sync_user_ledger'):
            response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, '1 more account')
        self.assertContains(response, '1 more invoice')
        self.assertEqual(len(response.context['account_balances_preview']), 5)
        self.assertEqual(len(response.context['open_invoices_preview']), 5)
        self.assertContains(response, 'View Banking', count=2)

    def test_views_sync_before_render_and_show_current_headings(self):
        for name in ('dashboard:index', 'dashboard:reports'):
            with self.subTest(name=name), patch(
                'dashboard.views.sync_user_ledger'
            ) as ledger_sync:
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                ledger_sync.assert_called_once_with(self.user)

        response = self.client.get(reverse('dashboard:reports'))
        self.assertContains(response, 'Balance evolution')
        self.assertContains(response, 'Monthly cash flow')
        self.assertContains(response, 'How much is on installments')
        self.assertContains(response, 'Income and expenses by account or card')
        self.assertNotContains(response, 'Monthly spending by credit card')

    def test_htmx_partial_and_window_range_remain_intact(self):
        response = self.client.get(
            reverse('dashboard:reports'), HTTP_HX_REQUEST='true'
        )
        self.assertNotContains(response, '<html')
        self.assertContains(response, 'id="reports-charts"')
        self.assertContains(response, 'hx-target="#reports-charts"')

        today = timezone.localdate()
        first = add_months(today.year, today.month, -5)
        last = add_months(today.year, today.month, 6)
        expected = f'{date(*first, 1):%b %Y} &ndash; {date(*last, 1):%b %Y}'
        self.assertContains(response, expected)

    def test_report_charts_have_foreground_mouse_and_keyboard_tooltips(self):
        self.transaction(amount='123.45')

        response = self.client.get(reverse('dashboard:reports'))
        content = response.content.decode()

        self.assertContains(response, 'group-hover:opacity-100')
        self.assertContains(response, 'group-focus-visible:opacity-100')
        self.assertNotContains(response, 'group-focus:opacity-100')
        self.assertContains(response, 'tabindex="0"')
        self.assertContains(response, 'R$ 123,45')
        for marks, interactions in (
            ('balance-marks', 'balance-interactions'),
            ('cashflow-marks', 'cashflow-interactions'),
            ('recurrence-marks', 'recurrence-interactions'),
            ('instrument-marks', 'instrument-interactions'),
        ):
            with self.subTest(chart=marks):
                self.assertLess(
                    content.index(f'data-chart-layer="{marks}"'),
                    content.index(f'data-chart-layer="{interactions}"'),
                )

    def test_evolution_uses_ledger_projection(self):
        future = timezone.localdate() + timedelta(days=35)
        self.transaction(amount='100.00', date=future)
        sync_user_ledger(self.user)

        evolution = get_account_evolution(self.user)

        future_rows = [
            row for row in evolution['months']
            if (row['year'], row['month']) == (future.year, future.month)
        ]
        self.assertEqual(future_rows[0]['closing_balance'], Decimal('900.00'))
