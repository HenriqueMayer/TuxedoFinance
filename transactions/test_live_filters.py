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
        for marker in ('data-live-search', 'type="hidden" id="filter-category"', 'name="sort" data-live-change', 'type="submit" data-live-submit'):
            self.assertIn(marker, form)
        self.assertNotIn('id="transaction-sort"', html)
        self.assertNotContains(response, 'id="transaction-clear-filters"')

    def test_compact_bar_keeps_primary_controls_visible_and_groups_refinements(self):
        response = self.client.get(reverse('transactions:list'))
        html = response.content.decode()
        start = html.index('<details id="transaction-extra-filters"')
        end = html.index('</details>', start)
        disclosure = html[start:end]
        self.assertNotIn('open', disclosure.split('>')[0])
        for marker in ('id="transaction-category-context"', 'id="transaction-recurrence-options"',
                       'id="filter-date"', 'id="filter-sort"'):
            self.assertIn(marker, disclosure)
        self.assertNotRegex(disclosure, r'<select\b[^>]*(?:name="category"|id="filter-category")')
        for marker in ('id="filter-search"', 'id="filter-month"',
                       'id="transaction-type-options"', 'id="transaction-apply-filters"'):
            self.assertNotIn(marker, disclosure)
        self.assertEqual(response.context['extra_filter_count'], 0)

    def test_legacy_category_is_named_and_preserved_without_another_picker(self):
        response = self.client.get(reverse('transactions:list'), {
            'category': str(self.category.pk), 'q': 'Heating', 'sort': 'oldest',
        })
        self.assertContains(response, f'type="hidden" id="filter-category" name="category" value="{self.category.pk}"')
        self.assertNotContains(response, 'data-search-select')
        self.assertContains(response, 'id="transaction-clear-category"')
        self.assertContains(response, 'Category:')
        self.assertContains(response, self.category.name)
        self.assertEqual(response.context['paginator'].count, 2)

    def test_additional_criteria_open_disclosure_and_count_without_changing_filters(self):
        self.make_transaction(title='Monthly', is_fixed=True)
        response = self.client.get(reverse('transactions:list'), {
            'q': 'Monthly', 'type': 'EXPENSE', 'month': '2026-01',
            'category': str(self.category.pk), 'recurrence': 'fixed',
            'date': '2026-01-15', 'sort': 'oldest',
        })
        self.assertEqual(response.context['paginator'].count, 1)
        self.assertEqual(response.context['extra_filter_count'], 4)
        self.assertContains(response, 'id="transaction-extra-filters" class="filter-disclosure" open')
        self.assertContains(response, '4 active filters')
        self.assertContains(response, 'id="transaction-clear-filters"', count=1)
        self.assertEqual(response.context['selected_category'], str(self.category.pk))

    def test_primary_criteria_do_not_count_as_hidden_refinements(self):
        response = self.client.get(reverse('transactions:list'), {
            'q': 'Heating', 'type': 'EXPENSE', 'month': '2026-01',
        })
        self.assertEqual(response.context['extra_filter_count'], 0)
        self.assertContains(response, 'id="transaction-clear-filters"', count=1)

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
        self.assertEqual(response.context['extra_filter_count'], 0)
        self.assertContains(response, 'id="transaction-extra-filters" class="filter-disclosure" open')
