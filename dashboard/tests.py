from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from banking.models import (
    Bank,
    BankAccount,
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
        self.assertEqual(summary['missing_currencies'], ['EUR'])
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
        sync_user_ledger(self.user)

        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['investment_month'], Decimal('200.00'))
        self.assertEqual(summary['expense_month'], Decimal('0.00'))
        self.assertEqual(summary['current_balance'], Decimal('800.00'))


class InstrumentReportTests(DashboardFixture):
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


class DashboardPageContractTests(DashboardFixture):
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
        self.assertContains(response, 'Spending by card or account')
        self.assertContains(response, 'Income by bank account')
        self.assertContains(response, 'Monthly spending by credit card')

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
