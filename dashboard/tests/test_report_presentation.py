# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Report presentation exposes native chart pans without changing financial scope."""
from datetime import date
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.urls import reverse

from dashboard.tests.fixtures import DashboardFixture


class Elements(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.tags = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def by_id(self, identifier):
        return next((tag, attrs) for tag, attrs in self.tags if attrs.get('id') == identifier)


@patch('django.utils.timezone.localdate', return_value=date(2026, 9, 20))
class ReportPresentationTests(DashboardFixture):
    def test_full_and_htmx_documents_expose_named_native_chart_pans(self, localdate):
        self.transaction(date=date(2026, 9, 1), amount='12.34')
        for htmx in (False, True):
            with self.subTest(htmx=htmx):
                response = self.client.get(reverse('dashboard:reports'),
                    HTTP_HX_REQUEST='true' if htmx else 'false')
                elements = Elements(response.content.decode())
                pans = [attrs for tag, attrs in elements.tags
                    if 'report-chart-scroll' in attrs.get('class', '').split()]
                self.assertEqual(len(pans), 3)
                for pan in pans:
                    self.assertEqual(pan['role'], 'region')
                    self.assertEqual(pan['tabindex'], '0')
                    self.assertEqual(elements.by_id(pan['aria-labelledby'])[0], 'h2')
                    self.assertEqual(elements.by_id(pan['aria-describedby'])[0], 'p')
                self.assertEqual(str(response.context['instrument_activity']['expense_total']), '12.34')

    def test_full_identities_remain_available_beside_short_chart_labels(self, localdate):
        self.bank.name = 'Institution' + 'X' * 85
        self.bank.save(update_fields=['name'])
        self.account.name = 'Account' + 'Y' * 90
        self.account.save(update_fields=['name'])
        self.transaction(date=date(2026, 9, 1), amount='12.34', title='Source one')
        self.transaction(date=date(2026, 9, 2), amount='56.78', title='Source two')
        response = self.client.get(reverse('dashboard:reports'), {'instrument_month': '2026-09'})
        self.assertContains(response, f'<title>{self.bank.name}</title>', html=True)
        self.assertContains(response, self.account.name)
        selection = response.context['instrument_selection']['points'][0]
        self.assertIn(self.bank.name, selection['label'])
        self.assertIn(self.account.name, selection['label'])
        details = self.client.get(selection['details'][0]).json()
        self.assertEqual(sum(int(row['cents']) for row in details['rows']), 6912)
        self.assertEqual({source['label'].split(' · ')[0] for row in details['rows'] for source in row['sources']},
                         {'Source one', 'Source two'})

    def test_selected_shortcuts_keep_native_destinations_and_independent_filters(self, localdate):
        for period, current in [('2026-09', 'current'), ('ALL', 'all')]:
            with self.subTest(period=period):
                response = self.client.get(reverse('dashboard:reports'), {
                    'charts_offset': '-1', 'instrument_month': period, 'installment_month': period,
                })
                elements = Elements(response.content.decode())
                for prefix in ('instrument', 'installment'):
                    tag, selected = elements.by_id(f'{prefix}-{current}')
                    self.assertEqual(tag, 'span')
                    self.assertIn('aria-current', selected)
                    self.assertIn('period-navigation-choice', selected['class'].split())
                    for direction in ('previous', 'next'):
                        tag, attrs = elements.by_id(f'{prefix}-{direction}')
                        if tag == 'span':
                            self.assertEqual(attrs['aria-disabled'], 'true')
                            continue
                        self.assertEqual(tag, 'a')
                        query = parse_qs(urlsplit(attrs['href']).query)
                        self.assertEqual(query['charts_offset'], ['-1'])
                        other = 'installment' if prefix == 'instrument' else 'instrument'
                        self.assertEqual(query[f'{other}_month'], [period])
