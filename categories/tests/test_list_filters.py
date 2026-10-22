"""List filters coverage for categories."""

from html.parser import HTMLParser
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from categories.models import Category


User = get_user_model()


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

    @staticmethod
    def filter_choices(response):
        class FilterInputs(HTMLParser):
            def __init__(self):
                super().__init__()
                self.choices = {}

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if tag == 'input' and attributes.get('name') in ('level', 'type'):
                    self.choices[attributes['id']] = attributes

        parser = FilterInputs()
        parser.feed(response.content.decode())
        return parser.choices

    def test_filter_choices_are_always_visible_native_radios_with_stable_values(self):
        for query, checked_ids in (
            ({}, {'filter-level-all', 'filter-type-all'}),
            ({'level': 'sub', 'type': 'unclassified'}, {'filter-level-sub', 'filter-type-unclassified'}),
            ({'level': 'unknown', 'type': 'unknown'}, {'filter-level-all', 'filter-type-all'}),
        ):
            with self.subTest(query=query):
                response = self.client.get(reverse('categories:list'), query)
                self.assertNotContains(response, 'id="category-extra-filters"')
                self.assertContains(response, '<fieldset id="filter-level"', count=1)
                self.assertContains(response, '<fieldset id="filter-type"', count=1)
                choices = self.filter_choices(response)
                self.assertEqual(
                    {key: item['value'] for key, item in choices.items()},
                    {'filter-level-all': '', 'filter-level-top': 'top', 'filter-level-sub': 'sub',
                     'filter-type-all': '', 'filter-type-income': 'INCOME',
                     'filter-type-expense': 'EXPENSE', 'filter-type-unclassified': 'unclassified'},
                )
                self.assertEqual({key for key, item in choices.items() if 'checked' in item}, checked_ids)
                self.assertTrue(all(item.get('type') == 'radio' for item in choices.values()))
                self.assertTrue(all('data-live-change' in item for item in choices.values()))

    def test_portuguese_filter_labels_keep_unlocalized_get_identifiers(self):
        self.client.cookies['django_language'] = 'pt-br'
        response = self.client.get(reverse('categories:list'), {'level': 'top', 'type': 'INCOME'})
        self.assertContains(response, 'Todos os níveis')
        self.assertContains(response, 'Sem classificação')
        self.assertContains(response, 'Receita')
        choices = self.filter_choices(response)
        self.assertIn('checked', choices['filter-level-top'])
        self.assertIn('checked', choices['filter-type-income'])
        self.assertEqual(choices['filter-type-income']['value'], 'INCOME')

    def test_search_is_partial_case_insensitive_trimmed_and_user_scoped(self):
        response = self.client.get(reverse('categories:list'), {'q': ' DELIVERY '})

        self.assertEqual(self.response_names(response), ['Food Delivery'])
        self.assertEqual(response.context['search_query'], 'DELIVERY')

    def test_disclosure_groups_keep_matching_children_in_owned_parent_context(self):
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        groups = response.context['category_groups']
        groceries = next(group for group in groups if group['category'] == self.groceries)
        self.assertEqual([group['category'] for group in groceries['children']], [self.delivery])
        self.assertContains(response, f'aria-controls="category-children-{self.groceries.pk}"')
        self.assertContains(response, '<details data-category-branch>')

        filtered = self.client.get(reverse('categories:list'), {'q': 'Delivery'})
        self.assertEqual([group['category'] for group in filtered.context['category_groups']], [self.groceries])
        self.assertEqual(filtered.context['category_groups'][0]['children'][0]['category'], self.delivery)
        self.assertTrue(filtered.context['has_category_groups'])
        self.assertEqual(filtered.context['result_count'], 1)
        self.assertContains(filtered, 'Food Delivery')
        self.assertNotContains(filtered, 'Private Delivery')

    def test_disclosure_tree_supports_nested_categories_and_renders_legacy_cycles_once(self):
        grandchild = Category.objects.create(user=self.user, name='Weekend Delivery', parent_category=self.delivery)
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        groceries = next(group for group in response.context['category_groups'] if group['category'] == self.groceries)
        self.assertEqual(groceries['children'][0]['children'][0]['category'], grandchild)

        # Existing/imported relationships can contain cycles. Rendering should
        # still expose every owned record once, without recursive graph traversal.
        self.groceries.parent_category = grandchild
        self.groceries.save(update_fields=['parent_category'])
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        for category in (self.groceries, self.delivery, grandchild, self.salary):
            self.assertContains(response, f'data-category-group="{category.pk}"', count=1)

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
            ['Groceries', 'Food Delivery', 'Salary'],
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
        self.assertIn('checked', self.filter_choices(response)['filter-level-top'])

    def test_type_filter_combines_with_hierarchy_and_preserves_unclassified(self):
        self.salary.transaction_type = Category.TransactionType.INCOME
        self.salary.save(update_fields=['transaction_type'])
        response = self.client.get(reverse('categories:list'), {'type': 'INCOME', 'level': 'top'})
        self.assertEqual(self.response_names(response), ['Salary'])
        response = self.client.get(reverse('categories:list'), {'type': 'unclassified'})
        self.assertEqual(self.response_names(response), ['Groceries', 'Food Delivery'])

    def test_subcategory_shortcut_accepts_only_an_owned_top_level_parent(self):
        response = self.client.get(reverse('categories:create'), {'parent': self.groceries.pk})
        self.assertEqual(response.context['form'].initial['parent_category'], self.groceries.pk)
        foreign = Category.objects.get(user=self.other_user)
        for parent in (foreign, self.delivery):
            with self.subTest(parent=parent.pk):
                response = self.client.get(reverse('categories:create'), {'parent': parent.pk})
                self.assertNotIn('parent_category', response.context['form'].initial)
