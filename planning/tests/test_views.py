# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Views coverage for planning."""

from datetime import date
from decimal import Decimal
from django.urls import reverse
from banking.models import BankMovement
from planning.models import FinancialGoal
from planning.tests.fixtures import PlanningFixture


class PlanningViewTests(PlanningFixture):
    def test_forms_routes_ownership_and_nonmutating_gets(self):
        own = self.goal()
        private = FinancialGoal.objects.create(user=self.other, name='Private goal', currency='BRL', target_amount='100')
        self.assertEqual(self.client.get(reverse('planning:goals')).status_code, 302)
        self.client.force_login(self.user)
        for route in ['index', 'tools', 'goals', 'signals', 'budget_create', 'goal_create', 'signals_settings']:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(f'planning:{route}')).status_code, 200)
        self.assertEqual(self.client.get(reverse('planning:goal_detail', args=[private.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('planning:goal_archive', args=[private.pk])).status_code, 404)
        response = self.client.get(reverse('planning:allocation_create', args=[own.pk]))
        self.assertContains(response, 'data-search-select')
        self.assertContains(response, 'novalidate')
        self.assertNotContains(response, 'Private cash')
        self.assertEqual(self.client.get(reverse('planning:budget_copy')).status_code, 405)
        self.assertFalse(BankMovement.objects.exists())

    def test_goal_and_reservation_post_retains_invalid_and_valid_values(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('planning:goal_create'), {'name': 'Study', 'target_amount': '200', 'currency': 'BRL', 'target_date': '31/12/2027'})
        self.assertEqual(response.status_code, 302)
        goal = FinancialGoal.objects.get(name='Study')
        self.assertEqual(goal.target_date, date(2027, 12, 31))
        response = self.client.post(reverse('planning:allocation_create', args=[goal.pk]), {'source': f'account:{self.account.pk}', 'amount': '1500'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, 'value="1500"')
        response = self.client.post(reverse('planning:allocation_create', args=[goal.pk]), {'source': f'account:{self.account.pk}', 'amount': '200'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(goal.allocations.get().amount, Decimal('200'))

    def test_budget_invalid_filter_recovery_and_copy_invalid_month(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('planning:index'), {'month': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="invalid"')
        self.assertContains(response, 'role="alert"')
        response = self.client.post(reverse('planning:budget_copy'), {'month': 'invalid'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'value="invalid"', status_code=400)
