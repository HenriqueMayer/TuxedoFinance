"""List/tree presentation, filter normalization and native GET fallback."""
import re
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from categories.models import Category


class CategoryLiveFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('category-live', password='test')
        other = get_user_model().objects.create_user('category-private', password='test')
        Category.objects.filter(user__in=[cls.user, other]).delete()
        cls.parent = Category.objects.create(user=cls.user, name='House', transaction_type='EXPENSE')
        cls.child = Category.objects.create(user=cls.user, name='House heating', parent_category=cls.parent, transaction_type='EXPENSE')
        Category.objects.create(user=other, name='House private', transaction_type='EXPENSE')

    def setUp(self):
        self.client.force_login(self.user)

    def test_default_list_exposes_every_owned_row_without_a_disclosure(self):
        response = self.client.get(reverse('categories:list'))
        self.assertEqual(response.context['selected_view'], 'list')
        self.assertEqual(response.context['result_count'], 2)
        for category in (self.parent, self.child):
            self.assertContains(response, f'data-category-group="{category.pk}"', count=1)
        self.assertNotContains(response, 'House private')
        self.assertNotContains(response, 'data-category-branch')
        self.assertNotContains(response, 'id="category-clear-filters"')

    def test_tree_uses_native_collapsed_details_and_preserves_view_when_clearing(self):
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        self.assertContains(response, '<details data-category-branch >')
        self.assertContains(response, f'<summary id="category-toggle-{self.parent.pk}"')
        summary = response.content.decode().split(f'<summary id="category-toggle-{self.parent.pk}"', 1)[1].split('>', 1)[0]
        self.assertNotIn('aria-expanded', summary)  # Native state remains accurate without JS.
        filtered = self.client.get(reverse('categories:list'), {'view': 'tree', 'q': 'House'})
        self.assertContains(filtered, '<details data-category-branch open>')
        clear = re.search(r'<a id="category-clear-filters"[^>]*>', filtered.content.decode()).group()
        self.assertIn('href="/categories/?view=tree"', clear)
        self.assertIn('data-live-link="category-filters"', clear)
        self.assertIn('data-live-reset', clear)
        self.assertEqual(filtered.context['result_count'], 2)

    def test_tree_search_keeps_a_matching_child_whose_parent_is_not_a_result(self):
        response = self.client.get(reverse('categories:list'), {'view': 'tree', 'q': 'heating'})
        self.assertEqual(list(response.context['categories']), [self.child])
        self.assertContains(response, 'House heating')
        self.assertNotContains(response, f'data-category-group="{self.parent.pk}"')
        self.assertNotContains(response, 'data-category-branch')
        self.assertContains(response, '1 category')

    def test_invalid_choices_do_not_activate_clear_and_native_filters_combine(self):
        response = self.client.get(reverse('categories:list'), {'view': 'unknown', 'type': 'invalid', 'level': 'bad'})
        self.assertFalse(response.context['has_filters'])
        self.assertEqual(response.context['selected_view'], 'list')
        self.assertEqual(response.context['selected_type'], '')
        self.assertNotContains(response, 'id="category-clear-filters"')
        filtered = self.client.get(reverse('categories:list'), {'type': 'EXPENSE', 'level': 'sub', 'q': 'HOUSE'})
        self.assertEqual(list(filtered.context['categories']), [self.child])
        self.assertContains(filtered, 'id="category-clear-filters"', count=1)

    def test_controls_are_outside_results_and_submit_remains_available_without_js(self):
        response = self.client.get(reverse('categories:list'))
        html = response.content.decode()
        start = html.index('<form id="category-filters"')
        end = html.index('</form>', start)
        self.assertLess(end, html.index('<div id="category-results">'))
        form = html[start:end]
        self.assertIn('data-live-search', form)
        self.assertIn('data-live-change', form)
        self.assertIn('type="submit" data-live-submit', form)
        self.assertNotIn('type="submit" data-live-submit hidden', form)
