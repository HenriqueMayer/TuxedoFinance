# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Financial cutoffs and zero-value evidence agree across read models."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from banking.models import BankAccount, CreditCard, ExchangeRate, LoyaltyEntry, LoyaltyProgram
from banking.services import ConversionContext
from dashboard.details import composition
from dashboard.services import get_dashboard_summary, get_instrument_activity, get_ledger_snapshot
from dashboard.tests.fixtures import DashboardFixture
from planning.models import CategoryBudget
from planning.services import budget_progress
from transactions.models import TransactionSplit
from transactions.services import sync_user_ledger


TODAY = date(2026, 10, 16)


class ReportingIntegrityTests(DashboardFixture):
    def foreign_account(self):
        self.account.currency = 'USD'
        self.account.opening_balance = Decimal('0')
        self.account.save(update_fields=['currency', 'opening_balance'])

    def rates(self):
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
                                    rate='5', effective_date=date(2026, 10, 1))
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
                                    rate='6', effective_date=date(2026, 10, 20))

    @patch('dashboard.services.timezone.localdate', return_value=TODAY)
    def test_realized_fx_and_category_composition_match_budget_cutoff(self, localdate):
        self.foreign_account()
        self.rates()
        item = self.transaction(amount='100', date=date(2026, 10, 1))
        TransactionSplit.objects.create(transaction=item, category=self.category, amount='100')
        CategoryBudget.objects.create(user=self.user, category=self.category, month=TODAY.replace(day=1),
                                      currency='BRL', amount='1000')
        summary = get_dashboard_summary(self.user, 2026, 10)
        self.assertEqual(summary['performance']['through_cutoff']['expenses'], Decimal('500'))
        self.assertEqual(summary['expense_categories'][0]['total'], Decimal('500'))
        self.assertEqual(budget_progress(self.user, TODAY, as_of=TODAY)[0]['actual'], Decimal('500'))
        self.assertEqual(summary['performance']['full_month']['expenses'], Decimal('500'))
        self.assertEqual(summary['performance']['remaining']['expenses'], Decimal('0'))
        detail = composition(self.user, {'scope': 'categories', 'series': 'expenses',
                                         'period': '2026-10', 'cutoff': TODAY.isoformat()})
        self.assertEqual(detail['rows'][0]['cents'], '50000')
        self.assertEqual(detail['rows'][0]['sources'][0]['cents'], '50000')

    @patch('dashboard.services.timezone.localdate', return_value=TODAY)
    def test_planned_activity_excludes_fx_revaluation_of_realized_occurrences(self, localdate):
        self.foreign_account()
        self.rates()
        self.transaction(amount='100', date=date(2026, 10, 1))
        self.transaction(amount='25', date=date(2026, 10, 20))
        summary = get_dashboard_summary(self.user, 2026, 10)
        performance = summary['performance']
        self.assertEqual(performance['through_cutoff']['expenses'], Decimal('500'))
        self.assertEqual(performance['remaining']['expenses'], Decimal('150'))
        self.assertEqual(performance['full_month']['expenses'], Decimal('650'))

    @patch('dashboard.services.timezone.localdate', return_value=TODAY)
    def test_future_rate_does_not_hide_missing_realized_rate(self, localdate):
        self.foreign_account()
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
                                    rate='6', effective_date=date(2026, 10, 20))
        self.transaction(amount='100', date=date(2026, 10, 1))
        summary = get_dashboard_summary(self.user, 2026, 10)
        actual = summary['performance']['through_cutoff']
        self.assertEqual(actual['expenses'], Decimal('0'))
        self.assertEqual(actual['missing_currencies'], ['USD'])
        self.assertEqual(summary['performance']['full_month']['expenses'], Decimal('0'))
        self.assertEqual(summary['performance']['full_month']['missing_currencies'], ['USD'])
        self.assertEqual(summary['performance']['remaining']['expenses'], Decimal('0'))

    @patch('dashboard.services.timezone.localdate', return_value=TODAY)
    def test_points_cost_and_its_cashflow_sources_use_the_same_cutoff(self, localdate):
        self.foreign_account()
        self.rates()
        program = LoyaltyProgram.objects.create(user=self.user, name='Points')
        LoyaltyEntry.objects.create(user=self.user, program=program, kind='PURCHASE',
                                    direction='CREDIT', amount='100', date=date(2026, 10, 1),
                                    cash_amount='25', funding_account=self.account)
        LoyaltyEntry.objects.create(user=self.user, program=program, kind='PURCHASE',
                                    direction='CREDIT', amount='100', date=date(2026, 10, 20),
                                    cash_amount='10', funding_account=self.account)
        summary = get_dashboard_summary(self.user, 2026, 10)
        self.assertEqual(summary['performance']['through_cutoff']['expenses'], Decimal('125'))
        detail = composition(self.user, {'scope': 'cashflow', 'series': 'expenses',
                                         'period': '2026-10', 'cutoff': TODAY.isoformat()})
        self.assertEqual(len(detail['rows']), 1)
        self.assertEqual(detail['rows'][0]['cents'], '12500')
        self.assertEqual(len(detail['rows'][0]['sources']), 1)
        # These two recuts intentionally cover categorized records, not points.
        self.assertEqual(get_instrument_activity(self.user, 2026, 10)['expense_total'], 0)
        self.assertEqual(summary['expense_categories'], [])

    def test_zero_foreign_account_needs_no_rate_even_after_nonzero_account(self):
        self.foreign_account()
        self.account.opening_balance = Decimal('100')
        self.account.save(update_fields=['opening_balance'])
        empty = BankAccount.objects.create(user=self.user, bank=self.bank, name='Z empty', currency='USD')
        snapshot = get_ledger_snapshot(self.user, TODAY)
        rows = {row['account'].pk: row for row in snapshot['accounts']}
        self.assertEqual(snapshot['missing_currencies'], ['USD'])
        self.assertIsNone(rows[self.account.pk]['converted_balance'])
        self.assertEqual(rows[empty.pk]['converted_balance'], Decimal('0'))
        self.assertEqual(rows[empty.pk]['recorded_converted_balance'], Decimal('0'))

    def test_zero_net_forecast_keeps_nonzero_cash_and_obligation_fx_warning(self):
        self.foreign_account()
        self.account.opening_balance = Decimal('100')
        self.account.save(update_fields=['opening_balance'])
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual',
                                        closing_day=20, due_day=28, manual_settlement_from=date(2026, 10, 1))
        self.transaction(amount='100', date=date(2026, 10, 1), payment_channel='CREDIT_CARD',
                         bank_account=None, credit_card=card)
        sync_user_ledger(self.user, through_date=TODAY)
        snapshot = get_ledger_snapshot(self.user, date(2026, 10, 31), projected=True,
                                       forecast_from=TODAY, conversion=ConversionContext(self.user))
        row = snapshot['accounts'][0]
        self.assertEqual(row['native_balance'], Decimal('0'))
        self.assertEqual(snapshot['missing_currencies'], ['USD'])
        self.assertIsNone(row['recorded_converted_balance'])
        self.assertIsNone(row['invoice_obligations'][0]['converted_amount'])
