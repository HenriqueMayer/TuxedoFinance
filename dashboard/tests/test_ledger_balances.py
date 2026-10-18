"""Ledger balances coverage for dashboard."""

from datetime import date
from decimal import Decimal
from django.utils import timezone
from banking.models import BankAccount, CreditCard, DebitCard, ExchangeRate, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from banking.services import create_transfer
from dashboard.services import add_months, get_dashboard_summary, get_expenses_by_instrument
from transactions.models import Transaction
from transactions.services import sync_user_ledger
from dashboard.tests.fixtures import DashboardFixture


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

    def test_projected_cash_waits_for_card_due_date_while_performance_uses_statement_month(self):
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
        self.assertEqual(summary['projected_balance'], Decimal('1000.00'))
        self.assertEqual(summary['balance_month'], Decimal('0.00'))
        self.assertEqual(summary['expense_month'], Decimal('120.00'))

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
