from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from categories.models import Category

User = get_user_model()


class DefaultCategorySeedingTests(TestCase):
    def test_new_user_receives_only_the_approved_default_categories(self):
        expected_names = [
            'Groceries',
            'Food & Dining',
            'Subscriptions',
            'Education',
            'Fitness',
            'Transportation',
            'Pets',
            'Hobbies & Entertainment',
            'Services',
        ]
        user = User.objects.create_user('new-account', password='test')

        categories = Category.objects.filter(user=user).order_by('pk')

        self.assertEqual(
            list(categories.values_list('name', flat=True)),
            expected_names,
        )
        self.assertFalse(categories.exclude(parent_category=None).exists())


class CategoryListFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('categories', password='test')
        cls.other_user = User.objects.create_user('other-categories', password='test')
        Category.objects.filter(user__in=(cls.user, cls.other_user)).delete()

        cls.groceries = Category.objects.create(user=cls.user, name='Groceries')
        cls.salary = Category.objects.create(user=cls.user, name='Salary')
        cls.delivery = Category.objects.create(
            user=cls.user,
            name='Food Delivery',
            parent_category=cls.groceries,
        )
        Category.objects.create(user=cls.other_user, name='Private Delivery')

    def setUp(self):
        self.client.force_login(self.user)

    @staticmethod
    def response_names(response):
        return [category.name for category in response.context['categories']]

    def test_search_is_partial_case_insensitive_trimmed_and_user_scoped(self):
        response = self.client.get(reverse('categories:list'), {'q': ' DELIVERY '})

        self.assertEqual(self.response_names(response), ['Food Delivery'])
        self.assertEqual(response.context['search_query'], 'DELIVERY')

    def test_level_filters_top_level_and_subcategories(self):
        top_response = self.client.get(reverse('categories:list'), {'level': 'top'})
        sub_response = self.client.get(reverse('categories:list'), {'level': 'sub'})

        self.assertEqual(self.response_names(top_response), ['Groceries', 'Salary'])
        self.assertEqual(self.response_names(sub_response), ['Food Delivery'])

    def test_search_and_level_combine(self):
        response = self.client.get(
            reverse('categories:list'),
            {'q': 'food', 'level': 'sub'},
        )

        self.assertEqual(self.response_names(response), ['Food Delivery'])
        self.assertEqual(response.context['selected_level'], 'sub')

    def test_invalid_level_is_ignored(self):
        response = self.client.get(reverse('categories:list'), {'level': 'invalid'})

        self.assertEqual(
            self.response_names(response),
            ['Food Delivery', 'Groceries', 'Salary'],
        )
        self.assertEqual(response.context['selected_level'], '')

    def test_filtered_empty_state_and_controls_are_rendered(self):
        response = self.client.get(
            reverse('categories:list'),
            {'q': 'missing', 'level': 'top'},
        )

        self.assertContains(response, 'No matching categories')
        self.assertContains(response, 'Clear filters')
        self.assertContains(response, 'value="missing"')
        self.assertContains(response, 'value="top" selected')
