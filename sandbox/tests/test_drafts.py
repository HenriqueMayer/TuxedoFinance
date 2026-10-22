"""Drafts coverage for sandbox."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from sandbox.models import ScenarioDraft


User = get_user_model()


class PlanningDraftTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('planner', password='test')
        self.other = User.objects.create_user('other-planner', password='test')
        self.client.force_login(self.user)

    def test_explicit_incomplete_save_reopen_duplicate_compare_and_delete(self):
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Incomplete month', 'gross_salary': '12.',
            'planning_month': '2026-',
            'variable_label': ['Rent'], 'variable_type': ['currency'], 'variable_value': [''],
        })
        draft = ScenarioDraft.objects.get()
        self.assertRedirects(response, reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertFalse(draft.payload['complete'])
        self.assertEqual(draft.payload['inputs']['planning_month'], ['2026-'])
        self.assertEqual(draft.payload['input_format']['date_order'], 'DMY')
        opened = self.client.get(response.url)
        self.assertContains(opened, 'value="2026-"')
        self.assertNotContains(opened, 'id="scenario-result-title"')
        self.client.post(reverse('sandbox:draft_duplicate', args=[draft.pk]))
        self.assertEqual(ScenarioDraft.objects.count(), 2)
        copy = ScenarioDraft.objects.exclude(pk=draft.pk).get()
        self.assertEqual(copy.payload, draft.payload)
        response = self.client.get(reverse('sandbox:compare'), {'draft': [draft.pk, copy.pk]})
        self.assertContains(response, 'Incomplete — open this draft')
        self.client.post(reverse('sandbox:draft_delete', args=[copy.pk]))
        self.assertFalse(ScenarioDraft.objects.filter(pk=copy.pk).exists())

    def test_drafts_are_owner_scoped_for_every_action(self):
        draft = ScenarioDraft.objects.create(user=self.other, name='Foreign secret scenario', kind='budget')
        for route in ('draft_detail', 'draft_delete', 'draft_duplicate'):
            response = self.client.post(reverse(f'sandbox:{route}', args=[draft.pk]), {'action': 'save', 'draft_name': 'Stolen'})
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(reverse('sandbox:compare'), {'draft': draft.pk}).status_code, 404)
        self.assertNotContains(self.client.get(reverse('sandbox:drafts')), 'Foreign secret scenario')

    def test_draft_comparison_and_duplicate_controls_keep_machine_ids_unlocalized(self):
        from django.utils import translation

        draft = ScenarioDraft.objects.create(pk=1001, user=self.user, name='Precise saved plan', kind='budget')
        with translation.override('pt-br'):
            response = self.client.get(reverse('sandbox:drafts'))
        self.assertContains(response, 'name="draft" value="1001"')
        self.assertContains(response, 'form="duplicate-1001"')
        self.assertContains(response, 'id="duplicate-1001"')
        self.assertNotContains(response, 'value="1.001"')
        compared = self.client.get(reverse('sandbox:compare'), {'draft': str(draft.pk)})
        self.assertEqual(compared.status_code, 200)
        self.assertEqual(compared.context['scenarios'][0]['draft'], draft)

    def test_mixed_draft_normalizes_valid_inputs_and_retains_invalid_source_format(self):
        from accounts.models import UserPreference
        self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Mixed', 'gross_salary': '05000.0',
            'planning_month': '2026-',
            'variable_label': [' Rent ', 'Food'], 'variable_type': ['currency', 'currency'],
            'variable_value': ['0010,50', 'unfinished'],
        })
        draft = ScenarioDraft.objects.get()
        self.assertEqual(draft.payload['inputs']['gross_salary'], ['5000.00'])
        self.assertEqual(draft.payload['inputs']['variable_label'], ['Rent', 'Food'])
        self.assertEqual(draft.payload['inputs']['variable_value'], ['10.50', 'unfinished'])
        self.assertEqual(draft.payload['inputs']['planning_month'], ['2026-'])
        UserPreference.objects.filter(user=self.user).update(date_format='MDY')
        response = self.client.get(reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertContains(response, 'value="2026-"')
        self.assertContains(response, 'value="unfinished"')
        self.assertEqual(draft.payload['input_format']['date_order'], 'DMY')

    def test_calculation_and_live_simulation_never_save(self):
        data = {'initial_balance': '1000', 'rate': '1', 'rate_period': 'monthly', 'months': '12',
                'start_month': '2026-09', 'currency': 'BRL', 'contribution': '100', 'withdrawal': '0',
                'response_mode': 'result'}
        response = self.client.post(reverse('sandbox:simulation'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="simulation-result"', count=1)
        self.assertNotContains(response, '<html')
        self.assertEqual(ScenarioDraft.objects.count(), 0)
        self.assertEqual(self.user.bank_movements.count(), 0)
        self.assertEqual(self.user.transactions.count(), 0)

    def test_invalid_custom_rows_are_visible_and_never_silently_dropped(self):
        for value in ('NaN', 'Infinity', '-2', 'abc', '1.001'):
            with self.subTest(value=value):
                response = self.client.post(reverse('sandbox:index'), {
                    'gross_salary': '5000', 'variable_label': ['Expense'],
                    'variable_type': ['currency'], 'variable_value': [value],
                })
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context['result'])
                self.assertContains(response, 'Row 1: enter a description')
                self.assertContains(response, f'value="{value}"')

    def test_repeated_rows_can_be_added_and_removed_by_plain_post(self):
        response = self.client.post(reverse('sandbox:index'), {'action': 'add_variable', 'gross_salary': '5000'})
        self.assertContains(response, 'name="variable_label"', count=2)  # input + inert template
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'remove_variable_0', 'gross_salary': '5000',
            'variable_label': ['Rent', 'Food'], 'variable_type': ['currency', 'currency'],
            'variable_value': ['1000', '400'],
        })
        self.assertNotContains(response, 'value="Rent"')
        self.assertContains(response, 'value="Food"')

    def test_unbalanced_repeated_inputs_render_and_reopen_without_truncation(self):
        data = {'gross_salary': '5000', 'planning_month': '2026-09',
                'variable_label': [' Rent '], 'variable_type': ['currency'],
                'variable_value': ['010.0', 'unfinished', '123.45']}
        response = self.client.post(reverse('sandbox:index'), data)
        self.assertIsNone(response.context['result'])
        self.assertContains(response, 'Enter at most 20 complete rows')
        self.assertEqual(len(response.context['variable_rows']), 3)
        self.assertContains(response, 'value="unfinished"')
        self.assertContains(response, 'value="123.45"')
        data.update(action='save', draft_name='Unbalanced input')
        response = self.client.post(reverse('sandbox:index'), data)
        draft = ScenarioDraft.objects.get()
        self.assertFalse(draft.payload['complete'])
        self.assertEqual(draft.payload['inputs']['variable_label'], ['Rent'])
        self.assertEqual(draft.payload['inputs']['variable_value'], ['10.00', 'unfinished', '123.45'])
        opened = self.client.get(response.url)
        self.assertEqual(len(opened.context['variable_rows']), 3)
        self.assertContains(opened, 'value="unfinished"')

    def test_calculation_is_always_brl_despite_presentation_currency(self):
        from accounts.models import UserPreference
        UserPreference.objects.update_or_create(user=self.user, defaults={'base_currency': 'USD'})
        response = self.client.post(reverse('sandbox:index'), {'gross_salary': '5000'})
        self.assertContains(response, 'R$ 5.000,00')
        self.assertEqual(response.context['CURRENCY_SYMBOL'], 'R$')
