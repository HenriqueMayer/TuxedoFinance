import csv
import io

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

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

    def test_new_portuguese_user_receives_localized_default_categories(self):
        with translation.override('pt-br'):
            user = User.objects.create_user('nova-conta', password='test')

        self.assertEqual(
            list(Category.objects.filter(user=user).order_by('pk').values_list('name', flat=True)),
            [
                'Mercado',
                'Alimentação',
                'Assinaturas',
                'Educação',
                'Academia',
                'Transporte',
                'Animais de estimação',
                'Hobbies e entretenimento',
                'Serviços',
            ],
        )


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


class CategoryClassificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('classification', password='test')
        Category.objects.filter(user=self.user).delete()

    def test_used_category_cannot_be_classified_against_existing_transactions(self):
        from banking.models import Bank, BankAccount
        from transactions.models import Transaction

        category = Category.objects.create(user=self.user, name='Shared')
        bank = Bank.objects.create(user=self.user, name='Bank')
        account = BankAccount.objects.create(user=self.user, bank=bank, name='Account', currency='BRL')
        Transaction.objects.create(
            user=self.user, title='Expense', amount='10.00', transaction_type='EXPENSE',
            category=category, payment_channel='ACCOUNT', bank_account=account, date='2026-01-01',
        )
        category.transaction_type = Category.TransactionType.INCOME

        with self.assertRaises(ValidationError):
            category.full_clean()

    def test_category_form_labels_the_unclassified_option(self):
        from categories.forms import CategoryForm

        form = CategoryForm(user=self.user)

        self.assertIn('Unclassified (income and expense)', str(form['transaction_type']))

    def test_new_category_form_renders_parent_category_search(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('categories:create'))

        self.assertContains(response, 'id="parent-category-search"')
        self.assertContains(response, 'aria-controls="id_parent_category"')
        self.assertContains(response, 'Search parent categories')


class CategoryDeleteAllTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('delete-categories', password='test')
        self.other_user = User.objects.create_user('keep-categories', password='test')
        Category.objects.filter(user__in=(self.user, self.other_user)).delete()
        self.first = Category.objects.create(user=self.user, name='First')
        self.second = Category.objects.create(user=self.user, name='Second')
        self.other_category = Category.objects.create(user=self.other_user, name='Private')
        self.client.force_login(self.user)

    def test_confirmation_page_does_not_delete_categories(self):
        response = self.client.get(reverse('categories:delete_all'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delete all categories')
        self.assertContains(response, 'all 2 categories')
        self.assertEqual(Category.objects.filter(user=self.user).count(), 2)

    def test_confirmation_deletes_only_the_current_users_categories(self):
        response = self.client.post(reverse('categories:delete_all'))

        self.assertRedirects(response, reverse('categories:list'))
        self.assertFalse(Category.objects.filter(user=self.user).exists())
        self.assertTrue(Category.objects.filter(pk=self.other_category.pk).exists())

    def test_used_category_blocks_the_entire_deletion(self):
        from banking.models import Bank, BankAccount
        from transactions.models import Transaction

        bank = Bank.objects.create(user=self.user, name='Bank')
        account = BankAccount.objects.create(
            user=self.user, bank=bank, name='Account', currency='BRL'
        )
        Transaction.objects.create(
            user=self.user, title='Used category', amount='10.00',
            transaction_type='EXPENSE', category=self.first,
            payment_channel='ACCOUNT', bank_account=account, date='2026-01-01',
        )

        response = self.client.post(reverse('categories:delete_all'), follow=True)

        self.assertContains(
            response,
            'Categories cannot be deleted while they are used by existing transactions.',
        )
        self.assertEqual(Category.objects.filter(user=self.user).count(), 2)


class CategoryImportExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('category-files', password='test')
        self.other_user = User.objects.create_user('other-category-files', password='test')
        Category.objects.filter(user__in=(self.user, self.other_user)).delete()
        self.client.force_login(self.user)

    def upload(self, content):
        file = SimpleUploadedFile('categories.csv', content.encode('utf-8'), 'text/csv')
        return self.client.post(reverse('categories:import'), {'file': file})

    def test_export_contains_user_categories_and_hierarchy(self):
        parent = Category.objects.create(
            user=self.user,
            name='Food',
            transaction_type=Category.TransactionType.EXPENSE,
        )
        Category.objects.create(user=self.user, name='Restaurants', parent_category=parent)
        Category.objects.create(user=self.other_user, name='Private')

        response = self.client.get(reverse('categories:export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="categories.csv"',
        )
        rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows, [
            {'name': 'Food', 'transaction_type': 'EXPENSE', 'parent_category': ''},
            {'name': 'Restaurants', 'transaction_type': '', 'parent_category': 'Food'},
        ])

    def test_import_creates_categories_and_links_parent_regardless_of_row_order(self):
        response = self.upload(
            'name,transaction_type,parent_category\n'
            'Restaurants,EXPENSE,Food\n'
            'Food,EXPENSE,\n'
        )

        self.assertRedirects(response, reverse('categories:list'))
        food = Category.objects.get(user=self.user, name='Food')
        restaurant = Category.objects.get(user=self.user, name='Restaurants')
        self.assertEqual(restaurant.parent_category, food)
        self.assertEqual(restaurant.transaction_type, Category.TransactionType.EXPENSE)

    def test_import_skips_existing_names_without_overwriting_them(self):
        existing = Category.objects.create(user=self.user, name='Food')

        response = self.upload(
            'name,transaction_type,parent_category\nFood,EXPENSE,\nTransport,EXPENSE,\n'
        )

        self.assertRedirects(response, reverse('categories:list'))
        existing.refresh_from_db()
        self.assertIsNone(existing.transaction_type)
        self.assertTrue(Category.objects.filter(user=self.user, name='Transport').exists())

    def test_invalid_file_does_not_partially_import(self):
        response = self.upload(
            'name,transaction_type,parent_category\nFood,EXPENSE,\nTaxi,INVALID,\n'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'invalid transaction type')
        self.assertFalse(Category.objects.filter(user=self.user).exists())

    def test_import_and_export_require_login(self):
        self.client.logout()

        export_response = self.client.get(reverse('categories:export'))
        import_response = self.client.get(reverse('categories:import'))

        self.assertEqual(export_response.status_code, 302)
        self.assertEqual(import_response.status_code, 302)
