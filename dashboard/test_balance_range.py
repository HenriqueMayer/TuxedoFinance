# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from categories.models import Category
from dashboard.selection import selection_data
from dashboard.tests import DashboardFixture


class ChartCompositionTests(DashboardFixture):
    def test_series_keep_cents_exact_including_large_and_negative_values(self):
        data = selection_data([{'name': 'A', 'value': Decimal('90071992547409.93')},
            {'name': 'B', 'value': Decimal('-0.01')}], [('value', 'Amount')], label='name')
        self.assertEqual(data['points'][0]['values'], ['9007199254740993'])
        self.assertEqual(data['points'][1]['values'], ['-1'])

    def test_subcategory_scope_and_user_isolation(self):
        parent = Category.objects.create(user=self.user, name='Food')
        child = Category.objects.create(user=self.user, name='Cafe', parent_category=parent)
        self.transaction(amount='123.45', category=child)
        response = self.client.get(reverse('dashboard:reports'))
        endpoint = response.context['instrument_selection']['points'][0]['details'][0]
        self.assertEqual(self.client.get(endpoint).json()['rows'], [{'label':'Food > Cafe', 'cents':'12345'}])
        other = get_user_model().objects.create_user('other-chart', password='test')
        self.client.force_login(other)
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertEqual(self.client.get(reverse('dashboard:chart_details'), {'token':'invalid'}).status_code, 400)

    def test_removed_report_and_manual_selectors(self):
        response = self.client.get(reverse('dashboard:reports'))
        self.assertNotContains(response, 'id="where"')
        self.assertNotContains(response, 'data-selection-start')
        self.assertNotContains(response, 'id_range_start')
        self.assertEqual(response.context['balance_selection']['mode'], 'change')

    def test_balance_composition_preserves_opening_accounts(self):
        response = self.client.get(reverse('dashboard:reports'))
        endpoint = response.context['balance_selection']['points'][0]['details'][0]
        result = self.client.get(endpoint)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['title'], 'Balances by bank and account')
