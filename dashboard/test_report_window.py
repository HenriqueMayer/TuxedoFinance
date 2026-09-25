# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from dashboard.tests import DashboardFixture
from transactions.models import Transaction


@patch('django.utils.timezone.localdate', return_value=date(2026, 9, 20))
class InstrumentMonthTests(DashboardFixture):
    def test_default_month_is_independent_of_other_chart_offsets(self, localdate):
        self.transaction(date=date(2026, 8, 31), amount='10')
        self.transaction(date=date(2026, 9, 1), amount='35')
        self.transaction(date=date(2026, 10, 1), amount='100')
        for offset in (-1, 0, 2):
            for htmx in (False, True):
                with self.subTest(offset=offset, htmx=htmx):
                    response = self.client.get(reverse('dashboard:reports'), {
                        'charts_offset': offset, 'installment_month': '2026-08',
                    }, **({'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TARGET': 'reports-charts'} if htmx else {}))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['instrument_month_param'], '2026-09')
                    self.assertEqual(response.context['instrument_activity']['expense_total'], Decimal('35'))
                    self.assertNotContains(response, 'id="instrument-month"')
                    self.assertEqual(response.context['instrument_previous_month'], '2026-08')
                    self.assertEqual(response.context['instrument_next_month'], '2026-10')
                    self.assertEqual(response.context['installment_month_param'], '2026-08')
                    for chart in ('balance', 'cashflow'):
                        self.assertContains(response, f'id="report-{chart}-today"')
                    self.assertContains(response, 'Back to today', count=2 if offset else 0)

    def test_explicit_month_filters_totals_and_details_independently(self, localdate):
        self.transaction(date=date(2026, 8, 31), amount='12')
        self.transaction(date=date(2026, 9, 1), amount='35')
        self.transaction(date=date(2026, 9, 30), amount='5',
                         transaction_type=Transaction.TransactionType.INCOME)
        self.transaction(date=date(2026, 10, 1), amount='100')
        for offset in (0, 2):
            response = self.client.get(reverse('dashboard:reports'), {
                'charts_offset': offset, 'instrument_month': '2026-09',
                'installment_month': '2026-08',
            }, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='reports-charts')
            self.assertEqual(response.context['instrument_month_param'], '2026-09')
            self.assertEqual(response.context['instrument_activity']['expense_total'], Decimal('35'))
            self.assertEqual(response.context['instrument_activity']['income_total'], Decimal('5'))
            self.assertEqual(response.context['recurrence_breakdown']['total'], Decimal('12'))
            details = response.context['instrument_selection']['points'][0]['details']
            for endpoint, cents in zip(details, ('3500', '500')):
                self.assertEqual(self.client.get(endpoint).json()['rows'], [
                    {'label': 'Groceries', 'cents': cents},
                ])
            self.assertContains(response, 'September 2026')

    def test_all_and_invalid_instrument_months_keep_visible_scope_consistent(self, localdate):
        self.transaction(date=date(2026, 1, 1), amount='10')
        self.transaction(date=date(2026, 9, 1), amount='35')
        for period, selected, expected in [('ALL', 'ALL', '45'),
                                            ('invalid', '2026-09', '35'),
                                            ('2026-13', '2026-09', '35'),
                                            ('2026-00', '2026-09', '35')]:
            with self.subTest(period=period):
                response = self.client.get(reverse('dashboard:reports'), {'instrument_month': period})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['instrument_month_param'], selected)
                self.assertEqual(response.context['instrument_activity']['expense_total'], Decimal(expected))
                self.assertContains(response, 'id="instrument-window"')

    def test_future_months_and_year_boundaries_keep_totals_and_details_aligned(self, localdate):
        self.transaction(date=date(2026, 12, 31), amount='20')
        self.transaction(date=date(2027, 1, 1), amount='40')
        for month, previous, following, amount in [
            ('2026-12', '2026-11', '2027-01', '20'),
            ('2027-01', '2026-12', '2027-02', '40'),
        ]:
            response = self.client.get(reverse('dashboard:reports'), {'instrument_month': month})
            self.assertEqual(response.context['instrument_previous_month'], previous)
            self.assertEqual(response.context['instrument_next_month'], following)
            self.assertEqual(response.context['instrument_activity']['expense_total'], Decimal(amount))
            endpoint = response.context['instrument_selection']['points'][0]['details'][0]
            self.assertEqual(self.client.get(endpoint).json()['rows'], [
                {'label': 'Groceries', 'cents': str(int(amount) * 100)},
            ])

    def test_navigation_stops_at_representable_date_boundaries(self, localdate):
        for month, direction in [('0001-01', 'previous'), ('9999-12', 'next')]:
            response = self.client.get(reverse('dashboard:reports'), {'instrument_month': month})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context[f'instrument_{direction}_month'])
