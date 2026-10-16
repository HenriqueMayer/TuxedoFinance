# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Retired view links retain a safe, owned native hierarchy."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import BankMovement
from categories.models import Category
from transactions.models import Transaction


class CategoryListWorkspaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('list-owner')
        self.other = get_user_model().objects.create_user('list-private')
        Category.objects.filter(user__in=[self.user, self.other]).delete()
        self.parent = Category.objects.create(pk=1001, user=self.user, name='Home')
        self.child = Category.objects.create(pk=1002, user=self.user, name='Heating', parent_category=self.parent)
        self.leaf = Category.objects.create(pk=1003, user=self.user, name='Solar', parent_category=self.child)
        self.private = Category.objects.create(user=self.other, name='Private source')
        self.client.force_login(self.user)

    def test_legacy_view_keeps_only_owned_ancestry_and_exact_record_ids(self):
        response = self.client.get(reverse('categories:list'), {'view': 'tree', 'q': 'Solar'})
        self.assertEqual(response.context['result_count'], 1)
        for pk in [1001, 1002, 1003]:
            self.assertContains(response, f'data-category-group="{pk}"', count=1)
            self.assertContains(response, f'/categories/{pk}/edit/')
        self.assertContains(response, 'data-category-context', count=2)
        self.assertNotContains(response, self.private.name)
        self.assertNotContains(response, 'categories-graph.js')
        self.assertNotContains(response, 'id="category-view-tree"')

    def test_user_text_stays_escaped_and_read_only_gets_preserve_links_and_money(self):
        self.leaf.name = '</script><svg onload="alert(1)">'
        self.leaf.save(update_fields=['name'])
        before = list(Category.objects.values())
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        self.assertContains(response, '&lt;/script&gt;&lt;svg onload=')
        self.assertNotContains(response, '</script><svg onload')
        self.client.get(reverse('categories:list'), {'q': 'svg', 'level': 'sub'})
        self.assertEqual(list(Category.objects.values()), before)
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_legacy_foreign_parent_is_not_exposed(self):
        Category.objects.filter(pk=self.parent.pk).update(parent_category=self.private)
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        self.assertNotContains(response, self.private.name)
        self.assertFalse(response.context['category_groups'][0]['category'].display_parent_name)
