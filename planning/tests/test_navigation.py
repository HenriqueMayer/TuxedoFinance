# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit planning and simulation destinations retain native page ownership."""
from html.parser import HTMLParser
from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import override

from banking.models import BankMovement
from planning.tests.fixtures import PlanningFixture
from sandbox.models import ScenarioDraft


class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.groups = {}
        self.current = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'nav':
            self.current = next((key for key in ('data-planning-navigation', 'data-simulation-navigation') if key in attrs), None)
            if self.current:
                self.groups.setdefault(self.current, []).append([])
        elif tag == 'a' and self.current:
            self.groups[self.current][-1].append(attrs)

    def handle_endtag(self, tag):
        if tag == 'nav':
            self.current = None


class PlanningNavigationTests(PlanningFixture):
    def setUp(self):
        self.client.force_login(self.user)
        self.goal_record = self.goal()
        self.draft = ScenarioDraft.objects.create(user=self.user, name='Navigation draft', kind='budget', payload={})

    def navigation(self, route, args=None):
        with override('en'):
            response = self.client.get(reverse(route, args=args))
        self.assertEqual(response.status_code, 200)
        parser = NavigationParser()
        parser.feed(response.content.decode())
        primary = parser.groups['data-planning-navigation']
        self.assertEqual(len(primary), 1)
        self.assertEqual([link['href'] for link in primary[0]], [
            reverse(name) for name in ('planning:index', 'planning:goals', 'sandbox:index', 'planning:signals')
        ])
        return parser.groups

    def test_month_goal_and_alert_editors_keep_the_owning_primary_destination(self):
        for route, args, active in [
            ('planning:index', None, 'planning:index'),
            ('planning:budget_create', None, 'planning:index'),
            ('planning:goals', None, 'planning:goals'),
            ('planning:goal_create', None, 'planning:goals'),
            ('planning:goal_detail', [self.goal_record.pk], 'planning:goals'),
            ('planning:signals', None, 'planning:signals'),
            ('planning:signals_settings', None, 'planning:signals'),
        ]:
            with self.subTest(route=route):
                groups = self.navigation(route, args)
                self.assertEqual([link['href'] for link in groups['data-planning-navigation'][0]
                                  if link.get('aria-current') == 'page'], [reverse(active)])
                self.assertNotIn('data-simulation-navigation', groups)

    def test_simulation_and_saved_draft_pages_have_one_primary_and_one_secondary_navigation(self):
        for route, args, active in [
            ('sandbox:index', None, 'sandbox:index'),
            ('sandbox:simulation', None, 'sandbox:simulation'),
            ('sandbox:drafts', None, 'sandbox:drafts'),
            ('sandbox:compare', None, 'sandbox:drafts'),
            ('sandbox:draft_detail', [self.draft.pk], 'sandbox:drafts'),
            ('sandbox:draft_delete', [self.draft.pk], 'sandbox:drafts'),
        ]:
            with self.subTest(route=route):
                groups = self.navigation(route, args)
                self.assertEqual([link['href'] for link in groups['data-planning-navigation'][0]
                                  if link.get('aria-current') == 'page'], [reverse('sandbox:index')])
                secondary = groups['data-simulation-navigation']
                self.assertEqual(len(secondary), 1)
                self.assertEqual([link['href'] for link in secondary[0]], [reverse(name) for name in (
                    'sandbox:index', 'sandbox:simulation', 'sandbox:drafts')])
                self.assertEqual([link['href'] for link in secondary[0]
                                  if link.get('aria-current') == 'page'], [reverse(active)])
        self.assertEqual(ScenarioDraft.objects.filter(user=self.user).count(), 1)
        self.assertFalse(BankMovement.objects.exists())

    def test_legacy_tools_redirect_is_local_and_preserves_encoded_query_values(self):
        path = reverse('planning:tools')
        self.assertRedirects(self.client.get(path), reverse('sandbox:index'))
        query = urlencode([('month', '2030-03'), ('q', 'A & B'), ('draft', '11'), ('draft', '12')])
        response = self.client.get(f'{path}?{query}')
        self.assertRedirects(response, reverse('sandbox:index') + '?' + query, fetch_redirect_response=False)
        self.assertEqual(ScenarioDraft.objects.filter(user=self.user).count(), 1)
        self.assertFalse(BankMovement.objects.exists())

    def test_legacy_tools_and_saved_draft_navigation_remain_authenticated_and_owned(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('sandbox:draft_delete', args=[self.draft.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('sandbox:draft_detail', args=[self.draft.pk])).status_code, 404)
        self.client.logout()
        for route in ('planning:tools', 'sandbox:index', 'sandbox:drafts'):
            self.assertEqual(self.client.get(reverse(route)).status_code, 302)
            self.assertIn(reverse('accounts:login'), self.client.get(reverse(route)).url)
