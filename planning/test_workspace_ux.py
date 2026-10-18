# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from accounts.models import UserPreference
from banking.models import BankMovement
from planning.forms import GoalAllocationForm, GoalCreationForm
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalDecision
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
        self.assertContains(response, 'id="budgets"')
        for name in ['planning:goals', 'planning:tools']:
            self.assertContains(response, reverse(name))
        self.assertNotContains(response, reverse('sandbox:simulation'))
        self.assertContains(self.client.get(reverse('planning:tools')), reverse('sandbox:simulation'))
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

    def test_creation_and_standalone_reservation_show_the_same_remaining_capacity(self):
        self.reserve(amount='250')
        self.reserve(amount='100', bank_account=None, product=self.product, asset=self.asset)
        goal = self.goal('Next goal')
        created = GoalCreationForm(user=self.user)
        standalone = GoalAllocationForm(user=self.user, goal=goal)
        self.assertEqual(created.fields['source'].choices, standalone.fields['source'].choices)
        choices = dict(standalone.fields['source'].choices)
        self.assertIn('BRL 750.00', choices[f'account:{self.account.pk}'])
        self.assertIn('BRL 400.00', choices[f'pot:{self.product.pk}:{self.asset.pk}'])
        # A manual reserve already describes this cash; it is not deducted again.
        self.assertFalse(BankMovement.objects.exists())

    def test_editing_capacity_excludes_its_saved_claim_but_keeps_other_goals(self):
        self.reserve(amount='250')
        edited = self.reserve(amount='100')
        form = GoalAllocationForm(user=self.user, goal=edited.goal, instance=edited)
        self.assertIn('BRL 750.00', dict(form.fields['source'].choices)[edited.source_key])
        bound = GoalAllocationForm({'source': edited.source_key, 'amount': '750.01'},
                                   user=self.user, goal=edited.goal, instance=edited)
        self.assertFalse(bound.is_valid())
        self.assertIn('Available: BRL 750.00', str(bound.errors))
        self.assertEqual(bound['amount'].value(), '750.01')
        edited.refresh_from_db()
        self.assertEqual(edited.amount, Decimal('100'))
        self.assertFalse(BankMovement.objects.exists())

    def test_goal_summary_uses_the_preferred_date_independently_of_language(self):
        goal = self.goal(target_date=date(2031, 12, 24))
        preference = UserPreference.for_user(self.user)
        self.client.cookies['django_language'] = 'pt-br'
        for order, expected, other in [('DMY', '24/12/2031', '12/24/2031'), ('MDY', '12/24/2031', '24/12/2031')]:
            preference.date_format = order
            preference.save(update_fields=['date_format'])
            response = self.client.get(reverse('planning:goal_detail', args=[goal.pk]))
            self.assertContains(response, expected)
            self.assertNotContains(response, other)

    def test_reservation_sources_open_the_exact_owned_balance_without_editing_it(self):
        goal = self.goal()
        self.reserve(goal=goal)
        self.reserve(goal=goal, amount='100', bank_account=None, product=self.product, asset=self.asset)
        sources = goal_sources(self.user)
        bank_url = reverse('banking:detail', args=[self.bank.pk]) + f'#account-row-{self.account.pk}'
        pot_url = reverse('investments:position_detail', args=[self.product.pk, self.asset.pk])
        self.assertEqual(sources[f'account:{self.account.pk}']['url'], bank_url)
        self.assertEqual(sources[f'pot:{self.product.pk}:{self.asset.pk}']['url'], pot_url)
        response = self.client.get(reverse('planning:goal_detail', args=[goal.pk]))
        self.assertContains(response, f'href="{bank_url}" hx-swap="innerHTML show:none"')
        self.assertContains(response, f'href="{pot_url}"')
        self.assertEqual(self.client.get(pot_url).status_code, 200)
        self.assertNotIn(f'account:{self.private_account.pk}', sources)
        self.assertFalse(BankMovement.objects.exists())

    def test_signal_settings_and_reviews_keep_the_validated_reviewed_origin(self):
        self.expense(title='Review source')
        self.expense(title='Review source')
        origin = reverse('planning:signals') + '?reviewed=1'
        settings_url = reverse('planning:signals_settings')
        payload = {'duplicates_enabled': 'on', 'subscriptionincrease_enabled': 'on',
                   'budgetoverspend_enabled': 'on', 'futurecashshortage_enabled': 'on',
                   'duplicate_days': '3', 'subscription_increase_percent': '10',
                   'forecast_days': '30', 'next': origin}
        response = self.client.get(settings_url, {'next': origin})
        self.assertEqual(response.context['cancel_url'], origin)
        response = self.client.post(settings_url, {**payload, 'duplicate_days': '99'})
        self.assertEqual(response.context['return_url'], origin)
        self.assertEqual(response.context['form']['duplicate_days'].value(), '99')
        self.assertRedirects(self.client.post(settings_url, payload), origin)
        response = self.client.get(origin)
        key = next(row['key'] for row in response.context['signals'] if row['kind'] == 'duplicates')
        review_url = reverse('planning:signal_decision')
        self.assertRedirects(self.client.post(review_url, {'key': key, 'action': 'ACK', 'next': origin}), origin)
        self.assertTrue(SignalDecision.objects.filter(user=self.user, key=key).exists())
        self.assertContains(self.client.get(origin), f'name="next" value="{origin}"')
        self.assertRedirects(self.client.post(review_url, {'key': key, 'action': 'REOPEN', 'next': origin}), origin)
        self.assertFalse(SignalDecision.objects.filter(user=self.user, key=key).exists())
        self.assertRedirects(self.client.post(settings_url, {**payload, 'next': '//outside.example/'}), reverse('planning:signals'))
        self.assertRedirects(self.client.post(review_url, {'key': key, 'action': 'DISMISS', 'next': 'https://outside.example/'}), reverse('planning:signals'))
        self.assertFalse(BankMovement.objects.exists())
