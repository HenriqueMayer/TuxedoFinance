"""Navigation coverage for transactions."""

from datetime import date
from django.urls import reverse
from categories.models import Category
from transactions.models import Transaction
from transactions.tests.fixtures import TransactionFixture


class TransactionNavigationTests(TransactionFixture):
    def setUp(self):
        self.client.force_login(self.user)
        self.salary_category = Category.objects.create(
            user=self.user, name='Salary', transaction_type='INCOME',
        )
        self.child = Category.objects.create(
            user=self.user, name='Subscription', parent_category=self.category,
            transaction_type='EXPENSE',
        )
        self.fixed = self.make_transaction(
            title='Monthly subscription', category=self.child,
            is_fixed=True, fixed_until=date(2026, 2, 28),
        )
        self.income = self.make_transaction(
            title='Salary', category=self.salary_category, transaction_type='INCOME',
        )
        self.oneoff = self.make_transaction(title='One purchase')
        self.plan = self.make_transaction(
            title='Card plan', date=date(2026, 1, 26), installments=3,
            payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit,
        )
        self.make_transaction(
            title='Private row', user=self.other, category=self.other_category,
            bank_account=self.other_account,
        )

    def listing(self, **params):
        response = self.client.get(reverse('transactions:list'), params)
        self.assertEqual(response.status_code, 200)
        return response

    def test_counts_precede_refinements_and_count_records(self):
        response = self.listing(type='EXPENSE', recurrence='fixed', category=self.child.pk)
        self.assertEqual([card['count'] for card in response.context['type_cards']], [4, 1, 3])
        self.assertEqual(list(response.context['transactions']), [self.fixed])
        self.assertContains(response, 'General › Subscription')
        self.assertNotContains(response, 'Private row')
        self.assertNotContains(response, '>Private</option>')

    def test_category_filter_keeps_large_identifiers_unlocalized(self):
        category = Category.objects.create(pk=12345, user=self.user, name='Large identifier')
        transaction = self.make_transaction(category=category)
        for language in ('en', 'pt-br'):
            with self.subTest(language=language):
                self.client.cookies['django_language'] = language
                response = self.listing(category=str(category.pk))
                self.assertEqual(list(response.context['transactions']), [transaction])
                self.assertContains(response, 'type="hidden" id="filter-category" name="category" value="12345"')
                self.assertContains(response, 'Large identifier')

    def test_month_fold_drives_counts_categories_and_rows_once(self):
        from unittest.mock import patch
        original = Transaction.amount_for_month
        calls = []

        def counted(item, year, month):
            calls.append(item.pk)
            return original(item, year, month)

        with patch.object(Transaction, 'amount_for_month', counted):
            response = self.listing(month='2026-02', recurrence='fixed')
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(set(calls)), 4)
        self.assertEqual([card['count'] for card in response.context['type_cards']], [2, 0, 2])
        self.assertEqual(list(response.context['transactions']), [self.fixed])
        self.assertEqual(response.context['category_choices'], [self.child])
        response = self.listing(month='2026-03', recurrence='fixed')
        self.assertEqual(response.context['paginator'].count, 0)
        self.assertEqual(response.context['category_choices'], [])
        self.assertContains(response, 'No matching transactions')
        self.assertEqual(list(self.listing(recurrence='fixed').context['transactions']), [self.fixed])

    def test_card_cycle_and_installment_end(self):
        for month, expected in [('2026-01', []), ('2026-02', [self.plan]),
                                ('2026-04', [self.plan]), ('2026-05', [])]:
            with self.subTest(month=month):
                response = self.listing(month=month, recurrence='installment')
                self.assertEqual(list(response.context['transactions']), expected)

    def test_search_and_exact_date_narrow_card_counts(self):
        response = self.listing(q='Card', date='2026-01-26', month='2026-02')
        self.assertEqual([card['count'] for card in response.context['type_cards']], [1, 0, 1])
        self.assertEqual(list(response.context['transactions']), [self.plan])
        self.assertEqual(response.context['selected_date'], '2026-01-26')
        self.assertContains(response, 'id="transaction-extra-filters" class="filter-disclosure" open')

    def test_category_is_exact_and_oneoff_excludes_fixed_and_plans(self):
        response = self.listing(category=self.category.pk)
        self.assertEqual(set(response.context['transactions']), {self.oneoff, self.plan})
        response = self.listing(type='EXPENSE', recurrence='oneoff')
        self.assertEqual(list(response.context['transactions']), [self.oneoff])
        self.assertEqual(response.context['category_choices'], [self.category])

    def test_invalid_and_foreign_selections_are_not_retained(self):
        for category in [str(self.other_category.pk), '99999999999999999999999999', 'bogus', '-1']:
            with self.subTest(category=category):
                response = self.listing(category=category, type='INVESTMENT', recurrence='weekly',
                                        date='bad', month='0000-01', sort='bad', unknown='hidden')
                self.assertEqual(dict(response.context['filter_params']), {'sort': ['newest']})
                self.assertEqual(response.context['paginator'].count, 4)
        response = self.listing(type='INCOME', recurrence='installment', category=self.child.pk)
        self.assertEqual(list(response.context['transactions']), [self.income])
        self.assertEqual(response.context['selected_category'], '')
        self.assertEqual(response.context['selected_recurrence'], '')
        self.assertEqual(len(response.context['recurrence_links']), 3)

    def test_navigation_clears_category_and_page_preserving_other_filters(self):
        from urllib.parse import parse_qs, urlsplit
        response = self.listing(q='Card', month='2026-02', date='2026-01-26',
                                type='EXPENSE', recurrence='installment',
                                category=self.category.pk, sort='highest', page=1)
        income = response.context['type_cards'][1]
        self.assertEqual(parse_qs(urlsplit(income['url']).query), {
            'q': ['Card'], 'month': ['2026-02'], 'date': ['2026-01-26'],
            'sort': ['highest'], 'type': ['INCOME'],
        })
        fixed = response.context['recurrence_links'][1]
        params = parse_qs(urlsplit(fixed['url']).query)
        self.assertNotIn('category', params)
        self.assertNotIn('page', params)
        self.assertEqual(params['recurrence'], ['fixed'])
        self.assertEqual(params['type'], ['EXPENSE'])

    def test_pagination_preserves_normalized_filters_and_full_counts(self):
        for index in range(11):
            self.make_transaction(title=f'Paged {index}', category=self.child, is_fixed=True)
        response = self.listing(q='Paged', month='2026-02', type='EXPENSE',
                                recurrence='fixed', category=self.child.pk, sort='highest')
        self.assertEqual(response.context['type_cards'][0]['count'], 11)
        self.assertEqual(response.context['paginator'].count, 11)
        self.assertEqual(len(response.context['transactions']), 10)
        self.assertContains(response, 'recurrence=fixed')
        self.assertContains(response, f'category={self.child.pk}')
        self.assertContains(response, 'page=2')

    def test_empty_installation_differs_from_filtered_empty_results(self):
        self.assertContains(self.listing(q='Missing'), 'No matching transactions')
        Transaction.objects.filter(user=self.user).delete()
        response = self.listing(q='Missing')
        self.assertContains(response, 'No transactions yet')
        self.assertNotContains(response, 'No matching transactions')

    def test_query_count_does_not_grow_per_transaction_or_parent_category(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.listing()  # Initialize the user's presentation preferences first.
        with CaptureQueriesContext(connection) as first:
            self.listing()
        for index in range(12):
            self.make_transaction(title=f'Extra {index}', category=self.child)
        with CaptureQueriesContext(connection) as second:
            self.listing()
        self.assertEqual(len(first), len(second))
