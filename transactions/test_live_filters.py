"""GET controls remain complete and stable while the result island refreshes."""
from django.urls import reverse

from transactions.tests import TransactionFixture


class TransactionLiveFilterTests(TransactionFixture):
    def setUp(self):
        self.client.force_login(self.user)
        self.make_transaction(title='Heating one', notes='winter')
        self.make_transaction(title='Heating two', notes='summer')
        self.make_transaction(user=self.other, category=self.other_category, bank_account=self.other_account, title='Heating private')

    def test_shared_form_contains_sort_and_native_fallback_outside_result_island(self):
        response = self.client.get(reverse('transactions:list'))
        html = response.content.decode()
        start = html.index('<form id="transaction-filters"')
        end = html.index('</form>', start)
        self.assertLess(end, html.index('<div id="transaction-results"'))
        form = html[start:end]
        for marker in ('data-live-search', 'data-live-options', 'name="sort" data-live-change', 'type="submit" data-live-submit'):
            self.assertIn(marker, form)
        self.assertNotIn('id="transaction-sort"', html)
        self.assertNotContains(response, 'id="transaction-clear-filters"')

    def test_combined_get_search_and_sort_keep_server_ownership_and_one_clear(self):
        response = self.client.get(reverse('transactions:list'), {'q': 'Heating', 'sort': 'oldest', 'type': 'EXPENSE'})
        self.assertEqual(response.context['paginator'].count, 2)
        self.assertNotContains(response, 'Heating private')
        self.assertContains(response, 'id="transaction-clear-filters"', count=1)
        self.assertContains(response, 'value="oldest" selected')
        self.assertContains(response, 'data-live-set="type"')

    def test_invalid_date_errors_stay_next_to_the_original_filter(self):
        response = self.client.get(reverse('transactions:list'), {'date': '32/01/2026', 'q': 'winter'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="filter-date"')
        self.assertContains(response, 'value="32/01/2026"')
        self.assertContains(response, 'data-field-error')
        self.assertEqual(response.context['paginator'].count, 1)
