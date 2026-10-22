# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Analytical relocation preserves financial scopes, filters and legacy entrypoints."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from dashboard.services import get_dashboard_summary
from dashboard.tests.fixtures import DashboardFixture


@patch('django.utils.timezone.localdate', return_value=date(2026, 9, 20))
class AnalyticsWorkspaceTests(DashboardFixture):
    def test_home_has_operational_information_and_month_scoped_analytics_shortcut(self, localdate):
        response = self.client.get(reverse('dashboard:index'), {'month': '2026-08'})
        self.assertContains(response, 'Bank accounts today')
        self.assertContains(response, 'Outstanding invoices')
        self.assertContains(response, 'Month performance')
        self.assertContains(response, 'href="/analytics/?month=2026-08"')
        self.assertNotContains(response, 'id="category-heading"')
        self.assertNotContains(response, 'id="outlook-heading"')

    def test_finances_reuses_current_past_and_future_monthly_financial_evidence(self, localdate):
        self.transaction(date=date(2026, 8, 25), amount='10.00')
        self.transaction(date=date(2026, 9, 5), amount='20.00')
        self.transaction(date=date(2026, 9, 25), amount='30.00')
        self.transaction(date=date(2026, 10, 25), amount='40.00')
        for month, category_total, period_kind in ((8, '10', 'past'), (9, '20', 'current'), (10, '40', 'future')):
            with self.subTest(month=month):
                response = self.client.get(reverse('analytics:index'), {'month': f'2026-{month:02d}'})
                summary = get_dashboard_summary(self.user, 2026, month)
                self.assertEqual(response.context['expense_categories'][0]['total'], Decimal(category_total))
                self.assertEqual(response.context['period_kind'], period_kind)
                for key in ('performance', 'outlook', 'period_cutoff', 'period_closing_balance'):
                    self.assertEqual(response.context[key], summary[key])
                self.assertContains(response, 'id="category-heading"')
                self.assertContains(response, 'id="outlook-heading"')

    def test_month_and_report_windows_keep_independent_parameters(self, localdate):
        query = {'month': '2026-07', 'charts_offset': '-1', 'instrument_month': '2026-08',
                 'installment_month': '2026-10'}
        response = self.client.get(reverse('analytics:index'), query)
        self.assertEqual(response.context['selected_month_param'], '2026-07')
        self.assertEqual(response.context['evolution']['anchor_month'], 8)
        self.assertEqual(response.context['instrument_month_param'], '2026-08')
        self.assertEqual(response.context['installment_month_param'], '2026-10')
        html = response.content.decode()
        self.assertIn('month=2026-06&amp;charts_offset=-1&amp;instrument_month=2026-08&amp;installment_month=2026-10', html)
        monthly = self.client.get(reverse('analytics:index'), query, HTTP_HX_REQUEST='true',
                                  HTTP_HX_TARGET='finance-monthly-analysis')
        self.assertContains(monthly, 'id="finance-monthly-analysis"')
        self.assertNotContains(monthly, 'id="reports-charts"')
        reports = self.client.get(reverse('analytics:index'), query, HTTP_HX_REQUEST='true',
                                  HTTP_HX_TARGET='reports-charts')
        self.assertContains(reports, 'id="reports-charts"')
        self.assertNotContains(reports, 'id="finance-monthly-analysis"')

    def test_boosted_primary_navigation_returns_complete_workspace(self, localdate):
        response = self.client.get(reverse('analytics:index'), HTTP_HX_REQUEST='true', HTTP_HX_BOOSTED='true')
        self.assertContains(response, '<html')
        self.assertContains(response, 'Analytics sections')
        self.assertContains(response, 'id="finance-monthly-analysis"')

    def test_investment_analysis_has_new_sections_and_canonical_scope_form(self, localdate):
        response = self.client.get(reverse('analytics:investments'), {'scope': 'cash', 'total_offset': '-1'})
        self.assertContains(response, 'Analytics sections')
        self.assertContains(response, 'Investment evolution')
        self.assertContains(response, 'action="/analytics/investments/"')
        self.assertEqual(response.context['chart_scope'], 'cash')
        self.assertEqual(response.context['total_offset'], -1)
        self.assertEqual(response.context['flow_offset'], 0)
        partial = self.client.get(reverse('analytics:investments'), HTTP_HX_REQUEST='true',
                                  HTTP_HX_TARGET='investments-charts')
        self.assertContains(partial, 'id="investments-charts"')
        self.assertNotContains(partial, '<html')

    def test_legacy_routes_keep_exact_query_for_get_head_and_htmx(self, localdate):
        query = '?scope=cash&total_offset=-1&instrument_month=ALL&q=a%2Bb&q=c'
        for legacy, destination in (('dashboard:reports', 'analytics:index'),
                                    ('investments:charts', 'analytics:investments')):
            origin, target = reverse(legacy) + query, reverse(destination) + query
            for method in ('get', 'head'):
                with self.subTest(legacy=legacy, method=method):
                    response = getattr(self.client, method)(origin)
                    self.assertRedirects(response, target, fetch_redirect_response=False)
            htmx = self.client.get(origin, HTTP_HX_REQUEST='true')
            self.assertEqual(htmx.status_code, 200)
            self.assertEqual(htmx['HX-Redirect'], target)
            self.assertEqual(htmx.content, b'')
            anchored = self.client.get(origin, HTTP_HX_REQUEST='true',
                                       HTTP_HX_CURRENT_URL='http://testserver' + origin + '#balance-evolution')
            self.assertEqual(anchored['HX-Redirect'], target + '#balance-evolution')
            self.assertEqual(self.client.post(origin).status_code, 405)

    def test_analytics_and_legacy_routes_reauthorize_anonymous_requests(self, localdate):
        self.client.logout()
        for route in ('analytics:index', 'analytics:investments', 'dashboard:reports', 'investments:charts'):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response['Location'].startswith(reverse('accounts:login')))
