"""Page contracts coverage for dashboard."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from banking.models import BankAccount, CardInvoice, CreditCard
from dashboard.services import add_months, get_account_evolution
from transactions.models import Transaction
from transactions.services import sync_user_ledger
from dashboard.tests.fixtures import DashboardFixture


class DashboardPageContractTests(DashboardFixture):
    def test_index_translates_new_dashboard_copy_to_portuguese(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'pt-br'

        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, 'Desempenho do mês')
        self.assertContains(response, 'Despesas por categoria')
        self.assertContains(response, 'Perspectiva de seis meses')
        self.assertNotContains(response, 'Posição dos saldos')

    def test_index_explains_current_month_performance_and_categories(self):
        self.transaction(amount='45.00', date=timezone.localdate())

        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, 'Month performance')
        self.assertNotContains(response, 'Available cash today')
        self.assertNotContains(
            response,
            'What is available now and where this month is heading.',
        )
        self.assertContains(response, 'Income through today')
        self.assertContains(response, 'remaining planned')
        self.assertContains(response, 'Expenses by category')
        self.assertContains(response, 'Groceries')
        self.assertNotContains(response, 'Explore in Reports')

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
        self.assertContains(response, 'View Banking', count=1)
        self.assertContains(response, 'href="/banking/invoices/" class="quiet-action shrink-0">All invoices</a>', count=1)
        self.assertContains(response, 'href="/banking/invoices/%s/?next=' % response.context['open_invoices_preview'][0].pk)

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

    @patch('dashboard.services.timezone.localdate', return_value=date(2026, 9, 7))
    def test_report_cards_separate_live_cash_monthly_result_and_window_change(self, localdate):
        self.transaction(
            amount='500.00', transaction_type=Transaction.TransactionType.INCOME,
            date=date(2026, 9, 5),
        )
        self.transaction(amount='200.00', date=date(2026, 9, 20))
        self.transaction(
            amount='123.00', transaction_type=Transaction.TransactionType.INCOME,
            date=date(2026, 10, 5),
        )
        response = self.client.get(reverse('dashboard:reports'))
        evolution = response.context['evolution']
        self.assertEqual(evolution['balance_today'], Decimal('1500.00'))
        self.assertEqual(evolution['current_month']['balance'], Decimal('300.00'))
        self.assertEqual(evolution['net_change'], Decimal('423.00'))
        self.assertContains(response, 'Projected (month)')
        self.assertContains(response, 'September 2026')
        self.assertContains(response, 'R$ 300,00')
        self.assertContains(response, 'Apr 2026 to Mar 2027')
        self.assertNotContains(response, 'Best month')
        self.assertNotContains(response, 'Projected (end of window)')

        shifted = self.client.get(
            reverse('dashboard:reports'), {'charts_offset': 1}, HTTP_HX_REQUEST='true'
        )
        self.assertEqual(shifted.context['evolution']['current_month']['balance'], Decimal('123.00'))
        self.assertEqual(shifted.context['evolution']['balance_today'], Decimal('1500.00'))
        self.assertContains(shifted, 'Balance now')
        summary = shifted.content.decode().split('id="report-summary"', 1)[1].split('<section', 1)[0]
        self.assertNotIn('Balance at ', summary)
        self.assertContains(shifted, 'October 2026')
        self.assertContains(shifted, 'May 2026 to Apr 2027')

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
