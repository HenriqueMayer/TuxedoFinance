# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from datetime import date

from categories.models import Category


class CategoryOriginTests(TestCase):
    def test_recursive_rows_preserve_filters_through_invalid_and_valid_posts(self):
        user = get_user_model().objects.create_user('category-origin')
        parent = Category.objects.create(user=user, name='Meals', transaction_type='EXPENSE')
        child = Category.objects.create(user=user, name='Meals daily', transaction_type='EXPENSE', parent_category=parent)
        self.client.force_login(user)
        origin = '/categories/?q=Meals&type=EXPENSE'
        response = self.client.get(origin)
        self.assertContains(response, 'next=%2Fcategories%2F%3Fq%3DMeals%26type%3DEXPENSE', count=8)
        for category in (parent, child):
            url = reverse('categories:update', args=[category.pk])
            response = self.client.post(url, {'name': '', 'transaction_type': 'EXPENSE', 'next': origin})
            self.assertEqual(response.context['return_url'], origin)
            self.assertEqual(response.status_code, 200)
            response = self.client.post(url, {'name': category.name, 'transaction_type': 'EXPENSE', 'parent_category': category.parent_category_id or '', 'next': origin})
            self.assertRedirects(response, origin, fetch_redirect_response=False)


class CategoryActionOriginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('category-action-origin')
        self.other = get_user_model().objects.create_user('category-action-private')
        self.category = Category.objects.create(user=self.user, name='Action category', transaction_type='EXPENSE')
        self.origin = '/categories/?q=Action&type=EXPENSE&level=top#category-results'
        self.client.force_login(self.user)

    def test_delete_preserves_confirmation_cancel_success_and_protected_origin(self):
        from planning.models import CategoryBudget
        path = reverse('categories:delete', args=[self.category.pk])
        response = self.client.get(path, {'next': self.origin})
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertContains(response, f'name="next" value="{escape(self.origin)}"')
        self.assertContains(response, f'href="{escape(self.origin)}"')
        budget = CategoryBudget.objects.create(user=self.user, category=self.category,
            month=date(2030, 1, 1), currency='BRL', amount='100')
        self.assertRedirects(self.client.post(path, {'next': self.origin}), self.origin, fetch_redirect_response=False)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        budget.delete()
        self.assertRedirects(self.client.post(path, {'next': self.origin}), self.origin, fetch_redirect_response=False)
        self.assertFalse(Category.objects.filter(pk=self.category.pk).exists())
        private = Category.objects.create(user=self.other, name='Private action category')
        self.assertEqual(self.client.post(reverse('categories:delete', args=[private.pk]), {'next': self.origin}).status_code, 404)
        self.assertTrue(Category.objects.filter(pk=private.pk).exists())

    def test_import_keeps_origin_through_invalid_file_and_success(self):
        path = reverse('categories:import')
        response = self.client.post(path, {'next': self.origin, 'file': SimpleUploadedFile('invalid.csv',
            b'name,transaction_type,parent_category\nBroken,EXPENSE,,extra\n', content_type='text/csv')})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form']['file'].errors)
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertContains(response, f'name="next" value="{escape(self.origin)}"')
        response = self.client.post(path, {'next': self.origin, 'file': SimpleUploadedFile('valid.csv',
            b'name,transaction_type,parent_category\nAction imported,EXPENSE,\n', content_type='text/csv')})
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        self.assertTrue(Category.objects.filter(user=self.user, name='Action imported').exists())

    def test_bulk_delete_preserves_safe_origin_and_other_owners(self):
        private = Category.objects.create(user=self.other, name='Keep private')
        path = reverse('categories:delete_all')
        response = self.client.get(path, {'next': self.origin})
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertRedirects(self.client.post(path, {'next': self.origin}), self.origin, fetch_redirect_response=False)
        self.assertFalse(Category.objects.filter(user=self.user).exists())
        self.assertTrue(Category.objects.filter(pk=private.pk).exists())
        for path in [path, reverse('categories:import')]:
            response = self.client.get(path, {'next': '//external.example/path'})
            self.assertEqual(response.context['return_url'], reverse('categories:list'))
        category = Category.objects.create(user=self.user, name='Safe fallback')
        path = reverse('categories:delete', args=[category.pk])
        self.assertEqual(self.client.get(path, {'next': '//external.example/path'}).context['return_url'], reverse('categories:list'))
