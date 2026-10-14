# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""The visual hierarchy is owned presentation, never a financial editor."""
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import BankMovement
from categories.models import Category
from transactions.models import Transaction


class CategoryGraphTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('graph-owner')
        self.other = get_user_model().objects.create_user('graph-private')
        Category.objects.filter(user__in=[self.user, self.other]).delete()
        self.parent = Category.objects.create(pk=1001, user=self.user, name='Home')
        self.child = Category.objects.create(pk=1002, user=self.user, name='Heating', parent_category=self.parent)
        self.leaf = Category.objects.create(pk=1003, user=self.user, name='Solar', parent_category=self.child)
        self.private = Category.objects.create(user=self.other, name='Private source')
        self.client.force_login(self.user)

    def test_filtered_graph_keeps_only_owned_ancestry_and_precise_return_context(self):
        response = self.client.get(reverse('categories:list'), {'view': 'tree', 'q': 'Solar'})
        self.assertEqual(response.context['result_count'], 1)
        nodes = response.context['category_graph']
        self.assertEqual([row['id'] for row in nodes], ['1001', '1002', '1003'])
        self.assertEqual([row['parent'] for row in nodes], [None, '1001', '1002'])
        self.assertEqual([row['context'] for row in nodes], [True, True, False])
        for node in nodes:
            parts = urlsplit(node['edit'])
            self.assertEqual(parts.path, f'/categories/{node["id"]}/edit/')
            self.assertEqual(parse_qs(parts.query)['next'], [f'/categories/?view=tree&q=Solar#category-graph-node-{node["id"]}'])
        self.assertNotContains(response, self.private.name)

    def test_graph_escapes_user_text_and_gets_cannot_change_links_or_money(self):
        self.leaf.name = '</script><svg onload="alert(1)">'
        self.leaf.save(update_fields=['name'])
        before = list(Category.objects.values())
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        self.assertContains(response, '\\u003C/script\\u003E')
        self.assertNotContains(response, '</script><svg onload')
        self.client.get(reverse('categories:list'), {'view': 'list', 'q': 'svg', 'level': 'sub'})
        self.assertEqual(list(Category.objects.values()), before)
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_legacy_foreign_parent_is_not_exposed_in_graph_or_fallback(self):
        Category.objects.filter(pk=self.parent.pk).update(parent_category=self.private)
        response = self.client.get(reverse('categories:list'), {'view': 'tree'})
        self.assertNotContains(response, self.private.name)
        self.assertEqual(response.context['category_graph'][0]['parent'], None)
