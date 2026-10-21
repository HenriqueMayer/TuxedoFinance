"""Invoice credits reduce dated expenses and debt without inventing income."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from banking.models import BankAccount, CardInvoiceCredit, CreditCard
from dashboard.charts import build_bar_chart
from dashboard.details import composition
from dashboard.services import (get_dashboard_summary, get_expenses_by_instrument,
                                get_expenses_by_recurrence, get_income_by_account)
from dashboard.tests.fixtures import DashboardFixture
from dashboard.wealth import wealth_snapshot
from transactions.services import sync_user_ledger


class InvoiceCreditReportingTests(DashboardFixture):
    def setUp(self):
        super().setUp()
        self.card = CreditCard.objects.create(user=self.user, account=self.account,
            name='Statement card', closing_day=24, due_day=1,
            manual_settlement_from=date(2026, 1, 1))
        self.purchase = self.transaction(date=date(2026, 10, 5), amount='100',
            payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.card)

    def credit(self, **changes):
        values = dict(user=self.user, card=self.card,
            category=self.category, title='Card refund', amount=Decimal('8.95'),
            date=date(2026, 10, 10), reference_month=date(2026, 10, 1))
        values.update(changes)
        return CardInvoiceCredit.objects.create(**values)

    def summary(self, day):
        with patch('dashboard.services.timezone.localdate', return_value=day):
            return get_dashboard_summary(self.user, 2026, 10)

    def test_credit_reduces_category_instrument_and_oneoff_expenses_never_income(self):
        self.credit()
        summary = self.summary(date(2026, 10, 15))
        self.assertEqual(summary['expense_month'], Decimal('91.05'))
        self.assertEqual(summary['performance']['through_cutoff']['expenses'], Decimal('91.05'))
        self.assertEqual(summary['expense_categories'][0]['total'], Decimal('91.05'))
        self.assertEqual(get_expenses_by_instrument(self.user, 2026, 10)['total'], Decimal('91.05'))
        recurrence = get_expenses_by_recurrence(self.user, 2026, 10)
        self.assertEqual(recurrence['total'], Decimal('91.05'))
        self.assertEqual(recurrence['slices'][2]['value'], Decimal('91.05'))
        self.assertEqual(get_income_by_account(self.user, 2026, 10)['total'], 0)
        self.assertFalse(self.user.bank_movements.exists())

    def test_posting_cutoff_and_explicit_reference_month_are_independent(self):
        credit = self.credit()
        self.assertEqual(self.summary(date(2026, 10, 8))['performance']['through_cutoff']['expenses'], Decimal('100'))
        credit.date = date(2026, 11, 3)
        credit.save()
        october = self.summary(date(2026, 10, 20))
        self.assertEqual(october['expense_month'], Decimal('91.05'))
        self.assertEqual(october['performance']['through_cutoff']['expenses'], Decimal('100'))
        self.assertEqual(get_expenses_by_instrument(self.user, 2026, 11)['total'], 0)
        historical = self.summary(date(2026, 11, 20))
        self.assertEqual(historical['expense_month'], Decimal('91.05'))
        self.assertEqual(historical['performance']['through_cutoff']['expenses'], Decimal('100'))

    def test_signed_composition_retains_credit_identity_and_editor(self):
        credit = self.credit()
        result = composition(self.user, {'scope': 'instruments', 'series': 'expenses', 'period': '2026-10'})
        row = result['rows'][0]
        self.assertEqual(row['cents'], '9105')
        self.assertEqual(len(row['sources']), 2)
        source = next(item for item in row['sources'] if item['cents'] == '-895')
        self.assertEqual(source['url'], reverse('banking:invoice_credit_edit', args=[credit.pk]))
        self.assertNotEqual(source['url'], reverse('transactions:update', args=[self.purchase.pk]))
        before = composition(self.user, {'scope': 'instruments', 'series': 'expenses',
            'period': '2026-10', 'cutoff': '2026-10-08'})
        self.assertEqual(before['rows'][0]['cents'], '10000')
        self.assertEqual(len(before['rows'][0]['sources']), 1)

    def test_credit_only_zero_net_and_negative_svg_geometry_are_safe(self):
        self.credit(amount=Decimal('100'))
        self.assertEqual(self.summary(date(2026, 10, 20))['expense_categories'][0]['share'], 0)
        self.purchase.delete()
        summary = self.summary(date(2026, 10, 20))
        self.assertEqual(summary['expense_month'], Decimal('-100'))
        self.assertEqual(summary['expense_categories'][0]['bar_width'], 0)
        recurrence = get_expenses_by_recurrence(self.user, 2026, 10)
        self.assertFalse(any(row['draw'] for row in recurrence['slices']))
        self.assertTrue(all(0 <= row['share'] <= 100 for row in recurrence['slices']))
        chart = build_bar_chart(['October'], [{'name': 'Expense', 'tone': 'expense', 'values': [-100]}])
        bar = chart['groups'][0]['bars'][0]
        self.assertGreater(bar['height'], 0)
        self.assertGreaterEqual(bar['y'], chart['zero_y'])
        self.assertLessEqual(bar['y'] + bar['height'], chart['plot_bottom'])

    def test_foreign_credits_and_missing_exchange_rates_do_not_become_zero_expenses(self):
        other = get_user_model().objects.create_user('foreign-credit-report')
        other_card = CreditCard.objects.create(user=other, account=self.account,
            name='Foreign credit', closing_day=24, due_day=1)
        self.credit(user=other, card=other_card, amount=Decimal('999'))
        self.assertEqual(self.summary(date(2026, 10, 20))['expense_month'], Decimal('100'))
        foreign_account = BankAccount.objects.create(user=self.user, bank=self.bank,
            name='USD card account', currency='USD')
        self.card.account = foreign_account
        self.card.save()
        self.credit()
        summary = self.summary(date(2026, 10, 20))
        self.assertIn('USD', summary['missing_currencies'])

    def test_signed_stacks_use_separate_positive_and_negative_extents(self):
        chart = build_bar_chart(['October'], [
            {'name': 'Expense', 'tone': 'expense', 'stack': 'flow', 'values': [100]},
            {'name': 'Credit', 'tone': 'expense', 'stack': 'flow', 'values': [-120]},
        ])
        expense, credit = chart['groups'][0]['bars']
        self.assertLess(expense['y'], chart['zero_y'])
        self.assertEqual(credit['y'], chart['zero_y'])
        for bar in (expense, credit):
            self.assertGreater(bar['height'], 0)
            self.assertGreaterEqual(bar['y'], chart['plot_top'])
            self.assertLessEqual(bar['y'] + bar['height'], chart['plot_bottom'])

    def test_credit_reduces_incurred_debt_at_posting_and_excess_remains_card_asset(self):
        self.credit(amount=Decimal('120'))
        before = wealth_snapshot(self.user, date(2026, 10, 8))
        self.assertEqual(before['debt_total'], Decimal('100'))
        self.assertEqual(before['card_credits'], 0)
        after = wealth_snapshot(self.user, date(2026, 10, 15))
        self.assertEqual(after['debt_total'], 0)
        self.assertEqual(after['card_credits'], Decimal('20'))
        self.assertEqual(after['bank_total'], before['bank_total'])
        self.assertEqual(wealth_snapshot(self.user, date(2026, 12, 15))['card_credits'], Decimal('20'))

    def test_late_credit_preserves_actual_automatic_payment_and_becomes_card_asset(self):
        self.card.manual_settlement_from = None
        self.card.save()
        self.credit(date=date(2026, 11, 10))
        sync_user_ledger(self.user, through_date=date(2026, 11, 15))
        before = wealth_snapshot(self.user, date(2026, 11, 3))
        after = wealth_snapshot(self.user, date(2026, 11, 15))
        self.assertEqual(before['bank_total'], Decimal('900'))
        self.assertEqual(before['debt_total'], 0)
        self.assertEqual(before['card_credits'], 0)
        self.assertEqual(after['bank_total'], Decimal('900'))
        self.assertEqual(after['debt_total'], 0)
        self.assertEqual(after['card_credits'], Decimal('8.95'))
        self.assertEqual(after['net_worth'], Decimal('908.95'))
