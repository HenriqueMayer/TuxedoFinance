# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from dashboard.tests import DashboardFixture
from dashboard.views import _is_offset_window_safe


@patch('django.utils.timezone.localdate', return_value=date(2026, 9, 20))
class ForecastWindowTests(DashboardFixture):
    def setUp(self):
        super().setUp()
        self.transaction(date=date(2026, 9, 28), is_fixed=True)

    def test_reports_last_window_includes_late_month_cash_settlements(self, localdate):
        response = self.client.get(reverse('dashboard:reports'), {'charts_offset': 5})

        self.assertEqual(response.context['charts_offset'], 5)
        self.assertTrue(response.context['has_previous_window'])
        self.assertFalse(response.context['has_next_window'])
        last = response.context['evolution']['months'][-1]
        self.assertEqual(last['date'], date(2027, 8, 1))
        self.assertEqual(last['expenses'], Decimal('100.00'))
        self.assertEqual(last['closing_balance'], Decimal('-200.00'))
        self.assertContains(response, 'Forecast limit', count=2)
        self.assertNotContains(response, 'aria-label="Next window"')

    def test_reports_reject_partial_horizon_month_and_later_requests(self, localdate):
        for offset in (6, 24):
            with self.subTest(offset=offset):
                response = self.client.get(
                    reverse('dashboard:reports'), {'charts_offset': offset},
                    HTTP_HX_REQUEST='true', HTTP_HX_TARGET='reports-charts',
                )
                self.assertEqual(response.context['charts_offset'], 0)
                self.assertTrue(response.context['has_next_window'])
                self.assertEqual(
                    response.context['evolution']['months'][-1]['date'],
                    date(2027, 3, 1),
                )

    def test_reports_allow_past_windows_and_require_representable_opening(self, localdate):
        response = self.client.get(reverse('dashboard:reports'), {'charts_offset': -24})

        self.assertEqual(response.context['charts_offset'], -24)
        self.assertTrue(response.context['has_previous_window'])
        self.assertTrue(response.context['has_next_window'])
        self.assertFalse(_is_offset_window_safe(1, 6))
        self.assertTrue(_is_offset_window_safe(1, 7))

    def test_dashboard_last_outlook_includes_late_month_cash_settlements(self, localdate):
        response = self.client.get(reverse('dashboard:index'), {'month': '2027-03'})

        self.assertEqual(response.context['selected_month_param'], '2027-03')
        self.assertFalse(response.context['has_next_month'])
        last = response.context['outlook'][-1]
        self.assertEqual(last['date'], date(2027, 8, 1))
        self.assertEqual(last['expenses'], Decimal('100.00'))
        self.assertEqual(last['projected_balance'], Decimal('-200.00'))
        self.assertContains(response, 'Forecast limit')

        outside = self.client.get(reverse('dashboard:index'), {'month': '2027-04'})
        self.assertEqual(outside.context['selected_month_param'], '2026-09')
        self.assertTrue(outside.context['has_next_month'])
