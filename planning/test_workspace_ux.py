# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from banking.models import BankMovement
from planning.forms import GoalAllocationForm
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation
from planning.services import goal_sources
from planning.tests import PlanningFixture


class PlanningWorkspaceUXTests(PlanningFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def payload(self, **changes):
        return {'name': 'Connected target', 'target_amount': '2000', 'currency': 'BRL',
            'reserve_now': 'on', 'source': f'account:{self.account.pk}', 'reserved_amount': '200', **changes}

    def test_overview_exposes_owned_budgets_goals_and_secondary_simulations(self):
        CategoryBudget.objects.create(user=self.user, category=self.category, month=self.month, amount='100', currency='BRL')
        self.goal()
        FinancialGoal.objects.create(user=self.other, name='Private target', target_amount='100', currency='BRL')
        response = self.client.get(reverse('planning:index'))
        self.assertEqual((response.context['budget_count'], response.context['goal_count']), (1, 1))
        self.assertContains(response, reverse('planning:budgets'))
        for name in ['planning:goals', 'sandbox:index', 'sandbox:simulation', 'sandbox:drafts']:
            self.assertContains(response, reverse(name))
        self.assertNotContains(response, 'Private target')

    def test_overview_new_budget_keeps_its_selected_month(self):
        response = self.client.get(reverse('planning:index'), {'month': '2030-03'})
        self.assertContains(response, reverse('planning:budget_create') + '?month=2030-03')

    def test_bare_budget_edit_cancel_keeps_original_month_even_on_invalid_post(self):
        budget = CategoryBudget.objects.create(user=self.user, category=self.category, month=date(2024, 2, 1), amount='100', currency='BRL')
        path = reverse('planning:budget_update', args=[budget.pk])
        expected = reverse('planning:budgets') + '?month=2024-02'
        response = self.client.get(path)
        self.assertEqual(response.context['cancel_url'], expected)
        response = self.client.post(path, {'month': '2030-03', 'category': self.category.pk, 'amount': '-1', 'currency': 'BRL'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cancel_url'], expected)
        self.assertEqual(response.context['form']['month'].value(), '2030-03')
        budget.refresh_from_db()
        self.assertEqual(budget.month, date(2024, 2, 1))
        origin = reverse('planning:index') + '?month=2024-02'
        response = self.client.get(path, {'next': origin})
        self.assertEqual(response.context['cancel_url'], origin)

    def test_unavailable_reservation_source_is_rendered_but_cannot_be_funded(self):
        allocation = self.reserve(amount='100', bank_account=None, product=self.product, asset=self.asset)
        with patch('planning.forms.goal_sources', return_value={}):
            form = GoalAllocationForm(user=self.user, goal=allocation.goal, instance=allocation)
            self.assertIn((allocation.source_key, allocation.source_label), list(form.fields['source'].widget.choices))
            self.assertIn(f'value="{allocation.source_key}" selected', form['source'].as_widget())
            bound = GoalAllocationForm({'source': allocation.source_key, 'amount': '200'}, user=self.user, goal=allocation.goal, instance=allocation)
            self.assertFalse(bound.is_valid())
            self.assertIn('source', bound.errors)
        allocation.refresh_from_db()
        self.assertEqual(allocation.amount, Decimal('100'))
        self.assertFalse(BankMovement.objects.exists())

    def test_goal_and_real_bank_or_pot_reservation_save_in_one_native_submission(self):
        for source in [f'account:{self.account.pk}', f'pot:{self.product.pk}:{self.asset.pk}']:
            response = self.client.post(reverse('planning:goal_create'), self.payload(name=source, source=source))
            goal = FinancialGoal.objects.get(name=source)
            self.assertRedirects(response, reverse('planning:goal_detail', args=[goal.pk]))
            self.assertEqual(goal.allocations.get().amount, Decimal('200'))
        self.assertEqual(BankMovement.objects.count(), 0)
        self.account.refresh_from_db()
        self.assertEqual(self.account.opening_balance, Decimal('1000'))

    def test_goal_creation_rolls_back_when_capacity_changes_at_commit(self):
        exhausted = goal_sources(self.user)
        exhausted[f'account:{self.account.pk}']['balance'] = Decimal('0')
        with patch('planning.services.goal_sources', return_value=exhausted):
            response = self.client.post(reverse('planning:goal_create'), self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'reservation exceeds')
        self.assertContains(response, 'value="200"')
        self.assertFalse(FinancialGoal.objects.filter(name='Connected target').exists())
        self.assertFalse(GoalAllocation.objects.exists())

    def test_invalid_and_foreign_reservations_do_not_leave_a_target(self):
        for overrides in [{'reserved_amount': '1500'}, {'source': f'account:{self.private_account.pk}'}, {'source': '', 'reserved_amount': ''}]:
            response = self.client.post(reverse('planning:goal_create'), self.payload(**overrides))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'role="alert"')
            self.assertFalse(FinancialGoal.objects.filter(name='Connected target').exists())
        self.assertFalse(GoalAllocation.objects.exists())

    def test_unchecked_reservation_ignores_inactive_controls_and_safe_origin_returns(self):
        origin = reverse('planning:goals') + '?archived=1#goals'
        response = self.client.post(reverse('planning:goal_create'), self.payload(reserve_now='', source='foreign', reserved_amount='invalid', next=origin))
        self.assertRedirects(response, origin)
        self.assertFalse(GoalAllocation.objects.exists())
        self.assertEqual(FinancialGoal.objects.get().target_amount, Decimal('2000'))
        response = self.client.post(reverse('planning:goal_create'), self.payload(name='Unsafe origin', reserve_now='', next='//external.example/path'))
        goal = FinancialGoal.objects.get(name='Unsafe origin')
        self.assertRedirects(response, reverse('planning:goal_detail', args=[goal.pk]))

    def test_source_choices_report_remaining_shared_capacity(self):
        self.reserve(amount='250')
        response = self.client.get(reverse('planning:goal_create'))
        self.assertContains(response, 'BRL 750.00')
        self.assertNotContains(response, 'Private cash')
        self.assertFalse(response.context['form']['reserve_now'].value())
