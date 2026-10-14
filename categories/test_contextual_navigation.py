# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from categories.models import Category


class CategoryOriginTests(TestCase):
    def test_recursive_rows_preserve_filters_through_invalid_and_valid_posts(self):
        user = get_user_model().objects.create_user('category-origin')
        parent = Category.objects.create(user=user, name='Meals', transaction_type='EXPENSE')
        child = Category.objects.create(user=user, name='Meals daily', transaction_type='EXPENSE', parent_category=parent)
        self.client.force_login(user)
        origin = '/categories/?q=Meals&type=EXPENSE'
        response = self.client.get(origin)
        self.assertContains(response, 'next=%2Fcategories%2F%3Fq%3DMeals%26type%3DEXPENSE', count=3)
        for category in (parent, child):
            url = reverse('categories:update', args=[category.pk])
            response = self.client.post(url, {'name': '', 'transaction_type': 'EXPENSE', 'next': origin})
            self.assertEqual(response.context['return_url'], origin)
            self.assertEqual(response.status_code, 200)
            response = self.client.post(url, {'name': category.name, 'transaction_type': 'EXPENSE', 'parent_category': category.parent_category_id or '', 'next': origin})
            self.assertRedirects(response, origin, fetch_redirect_response=False)
