from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from dashboard.services import add_months
from payments.models import PaymentMethod
from transactions.models import Transaction

User = get_user_model()


class DashboardIndexTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dashboard', password='test')
        self.client.force_login(self.user)

    def test_dashboard_omits_recent_transactions_widget(self):
        response = self.client.get(reverse('dashboard:index'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Recent transactions')
        self.assertNotIn('recent_transactions', response.context)
        self.assertContains(response, 'Outlook')
        self.assertContains(response, 'New Transaction')


class DashboardReportsTemplateTests(TestCase):
    CHART_HEADINGS = (
        'Balance evolution',
        'Monthly cash flow',
        'How much is on installments',
        'Spending by payment method',
        'Income by payment method',
        'Where the money goes',
    )

    def setUp(self):
        self.user = User.objects.create_user('reports', password='test')
        self.client.force_login(self.user)

    def assert_chart_order(self, response):
        content = response.content.decode()
        positions = [content.index(heading) for heading in self.CHART_HEADINGS]

        self.assertEqual(positions, sorted(positions))
        for heading in self.CHART_HEADINGS:
            self.assertEqual(content.count(heading), 1)

    def test_full_page_renders_installments_as_third_chart(self):
        response = self.client.get(reverse('dashboard:reports'))

        self.assertEqual(response.status_code, 200)
        self.assert_chart_order(response)

    def test_htmx_partial_renders_installments_as_third_chart(self):
        response = self.client.get(
            reverse('dashboard:reports'),
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<html')
        self.assertContains(response, 'id="reports-charts"')
        self.assert_chart_order(response)

    def test_current_window_uses_balance_now_label_and_full_range(self):
        response = self.client.get(reverse('dashboard:reports'))
        self.assertEqual(response.status_code, 200)
        today = timezone.localdate()
        first_year, first_month = add_months(today.year, today.month, -5)
        last_year, last_month = add_months(today.year, today.month, 6)
        expected_range = (
            f'{date(first_year, first_month, 1):%b %Y} '
            f'&ndash; '
            f'{date(last_year, last_month, 1):%b %Y}'
        )
        self.assertContains(response, 'Balance now')
        self.assertContains(response, expected_range)

    def test_shifted_window_labels_balance_and_full_range(self):
        offset = -3
        response = self.client.get(
            reverse('dashboard:reports'), {'charts_offset': offset}
        )
        self.assertEqual(response.status_code, 200)
        today = timezone.localdate()
        anchor_year, anchor_month = add_months(today.year, today.month, offset)
        first_year, first_month = add_months(anchor_year, anchor_month, -5)
        last_year, last_month = add_months(anchor_year, anchor_month, 6)
        expected_range = (
            f'{date(first_year, first_month, 1):%b %Y} '
            f'&ndash; '
            f'{date(last_year, last_month, 1):%b %Y}'
        )
        self.assertContains(
            response,
            f'Balance at {date(anchor_year, anchor_month, 1):%b %Y}',
        )
        self.assertNotContains(response, 'Balance now')
        self.assertContains(response, expected_range)

    def test_payment_method_drilldown_encodes_method_name_once(self):
        method = PaymentMethod.objects.create(
            user=self.user,
            name='Blue Card',
            method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        Transaction.objects.create(
            user=self.user,
            title='Groceries',
            amount='25.00',
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=Category.objects.get(user=self.user, name='Groceries'),
            payment_method=method,
            transaction_date=timezone.localdate(),
        )

        response = self.client.get(reverse('dashboard:reports'), {'payment_month': 'ALL'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'expense_method=Blue+Card')
        self.assertNotContains(response, 'expense_method=Blue%2520Card')
        self.assertContains(response, 'data-scroll-target="method-categories-expense"')

        drilldown = self.client.get(
            reverse('dashboard:reports'),
            {'payment_month': 'ALL', 'expense_method': 'Blue Card'},
        )
        self.assertContains(drilldown, 'Categories in')
        self.assertContains(drilldown, 'Groceries')
