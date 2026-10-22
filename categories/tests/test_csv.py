"""Csv coverage for categories."""

import csv
import io
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from categories.models import Category


User = get_user_model()


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
