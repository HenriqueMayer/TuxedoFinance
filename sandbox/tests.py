from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from sandbox.forms import SalarySandboxForm, variables_from_data
from sandbox.services import (
    BudgetInput,
    CltScenario,
    CustomVariable,
    build_budget,
    calculate_clt,
    calculate_manual,
    irrf_tax,
)
from sandbox.tax_rules import get_tax_rules
from sandbox.models import ScenarioDraft


D = Decimal
User = get_user_model()


class SandboxCalculationTests(TestCase):
    def test_clt_inss_uses_progressive_2026_bands_and_ceiling(self):
        self.assertEqual(calculate_clt(CltScenario(D('2902.84'))).ordinary.inss, D('236.94'))
        self.assertEqual(calculate_clt(CltScenario(D('10000.00'))).ordinary.inss, D('988.09'))

    def test_irrf_2026_reduction_and_best_deduction(self):
        tax_at_five_thousand, _, _ = irrf_tax(
            D('5000.00'), 0, D('0'), get_tax_rules(), deductible_inss=D('1000.00'),
        )
        _, simplified_base, simplified_method = irrf_tax(
            D('8000'), 0, D('0'), get_tax_rules(), deductible_inss=D('200'),
        )
        _, legal_base, legal_method = irrf_tax(
            D('8000'), 10, D('0'), get_tax_rules(), deductible_inss=D('800'),
        )
        self.assertEqual(tax_at_five_thousand, D('0.00'))
        self.assertEqual((simplified_base, simplified_method), (D('7392.80'), 'simplified'))
        self.assertEqual((legal_base, legal_method), (D('5304.10'), 'legal'))

    def test_clt_projects_vacation_thirteenth_and_fgts(self):
        result = calculate_clt(CltScenario(D('5000.00')))
        self.assertEqual(
            result.annual_net,
            result.ordinary.net * 11 + result.vacation.net + result.thirteenth.net,
        )
        self.assertGreater(result.vacation.net, result.ordinary.net)
        self.assertEqual(result.annual_fgts, D('5333.33'))

    def test_manual_calculation_applies_currency_and_percentage_deductions(self):
        result = calculate_manual(D('6000'), (
            CustomVariable('Tax', 'percent', D('10')),
            CustomVariable('Health', 'currency', D('200')),
        ))
        self.assertEqual(result.monthly_deductions, D('800.00'))
        self.assertEqual(result.monthly_net, D('5200.00'))
        self.assertEqual(result.annual_net, D('62400.00'))

    def test_manual_calculation_preserves_negative_net(self):
        result = calculate_manual(D('1000'), (CustomVariable('Costs', 'currency', D('1200')),))
        self.assertEqual(result.monthly_net, D('-200.00'))
        self.assertEqual(result.annual_net, D('-2400.00'))

    def test_budget_applies_expenses_and_reports_fixed_cost_percentage(self):
        budget = BudgetInput(
            fixed_bills=D('1250'),
            emergency_percent=D('.10'),
            investments_percent=D('.20'),
            custom_variables=(CustomVariable('Leisure', 'currency', D('250')),),
        )
        row = build_budget(D('5000'), budget)
        self.assertEqual(row.fixed_percent_equivalent, D('25.00'))
        self.assertEqual(row.remaining, D('2000.00'))

    def test_budget_does_not_create_negative_percentage_expenses(self):
        row = build_budget(D('-200'), BudgetInput(
            emergency_percent=D('.10'),
            fixed_percent=D('.50'),
            custom_variables=(CustomVariable('Leisure', 'percent', D('10')),),
        ))
        self.assertEqual(row.fixed_bills, D('0.00'))
        self.assertEqual(row.emergency, D('0.00'))
        self.assertEqual(row.remaining, D('-200.00'))

    def test_variable_parser_rejects_excess_rows_instead_of_dropping_them(self):
        data = _MultiValueData({
            'deduction_label': ['Tax'] * 22,
            'deduction_type': ['percent'] * 22,
            'deduction_value': ['10'] * 21 + ['101'],
        })
        with self.assertRaises(ValidationError):
            variables_from_data(data, 'deduction')


class _MultiValueData(dict):
    def getlist(self, key):
        return self.get(key, [])


class SandboxViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sandbox', password='test')

    def test_page_requires_authentication(self):
        response = self.client.get(reverse('sandbox:index'))
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={reverse("sandbox:index")}')

    def test_get_requires_opt_in_to_clt_and_keeps_native_fields_available(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('sandbox:index'))
        self.assertContains(response, 'Salary Sandbox')
        self.assertContains(response, 'name="gross_salary"')
        self.assertContains(response, 'name="use_clt"')
        self.assertContains(response, 'name="use_clt"', count=1)
        self.assertContains(response, 'data-clt-options')
        self.assertNotContains(response, 'data-manual-options hidden')
        self.assertFalse(response.context['form']['use_clt'].value())
        self.assertNotContains(response, 'PJ regime')
        self.assertNotContains(response, 'comparison')

    def test_automatic_clt_post_renders_deductions_and_annual_projection(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '6000',
            'use_clt': 'on',
            'fixed_cost_type': 'percent',
            'fixed_cost_value': '50',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Automatic CLT calculation')
        self.assertContains(response, 'Net 13th salary')
        self.assertContains(response, 'Vacation net with one-third')
        self.assertContains(response, 'FGTS')
        self.assertContains(response, 'Net in an ordinary month')
        self.assertNotContains(response, 'Manual calculation')
        self.assertEqual(
            response.context['result']['budget'].income,
            response.context['result']['clt'].ordinary.net,
        )

    def test_manual_post_uses_entered_deductions_and_monthly_plan(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '6000',
            'deduction_label': ['Tax', 'Health'],
            'deduction_type': ['percent', 'currency'],
            'deduction_value': ['10', '200'],
            'fixed_cost_type': 'currency',
            'fixed_cost_value': '1500',
            'emergency_percent': '10',
            'investments_percent': '20',
            'variable_label': ['Leisure'],
            'variable_type': ['currency'],
            'variable_value': ['250'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manual calculation')
        self.assertContains(response, 'R$ 5.200,00')
        self.assertContains(response, 'R$ 62.400,00')
        self.assertContains(response, 'Tax')
        self.assertContains(response, 'Health')
        self.assertContains(response, 'Leisure')
        self.assertEqual(response.context['result']['budget'].remaining, D('1890.00'))

    def test_fragment_post_replaces_only_one_workspace(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '5000',
            'use_clt': 'on',
            'response_mode': 'fragment',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sandbox-workspace"', count=1)
        self.assertContains(response, 'Automatic CLT calculation')
        self.assertNotContains(response, '<html')
        self.assertNotContains(response, '<header')

    def test_result_has_accessible_help_and_no_persistence(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '5000',
            'use_clt': 'on',
        })
        self.assertContains(response, 'aria-describedby="id_gross_salary-help"')
        self.assertContains(response, 'id="id_gross_salary-help"', count=1)
        self.assertContains(response, 'aria-controls="clt-ordinary-net-help"', count=1)
        self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_fixed_percentage_validation_is_conditional_on_unit(self):
        percentage = SalarySandboxForm(data={
            'gross_salary': '5000',
            'fixed_cost_type': 'percent',
            'fixed_cost_value': '101',
        })
        currency = SalarySandboxForm(data={
            'gross_salary': '5000',
            'fixed_cost_type': 'currency',
            'fixed_cost_value': '1500',
        })
        self.assertFalse(percentage.is_valid())
        self.assertTrue(currency.is_valid())

    def test_page_uses_the_pt_br_catalog(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'pt-br'
        with override('pt-br'):
            response = self.client.get(reverse('sandbox:index'))
        self.assertContains(response, 'Sandbox de Salário')
        self.assertContains(response, 'Calcular descontos CLT automaticamente')
        self.assertContains(response, 'Descontos e impostos manuais')
        self.assertNotContains(response, 'comparação')


class PlanningDraftTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('planner', password='test')
        self.other = User.objects.create_user('other-planner', password='test')
        self.client.force_login(self.user)

    def test_explicit_incomplete_save_reopen_duplicate_compare_and_delete(self):
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Incomplete month', 'gross_salary': '12.',
            'planning_month': '2026-', 'expense_basis': 'free',
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

    def test_mixed_draft_normalizes_valid_inputs_and_retains_invalid_source_format(self):
        from accounts.models import UserPreference
        self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Mixed', 'gross_salary': '05000.0',
            'planning_month': '2026-', 'expense_basis': 'free',
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
        data = {'gross_salary': '5000', 'planning_month': '2026-09', 'expense_basis': 'free',
                'variable_label': [' Rent '], 'variable_type': ['currency'],
                'variable_value': ['010.0', 'unfinished', '123.45'],
                'deduction_label': ['Tax', 'Missing amount'], 'deduction_type': ['currency'],
                'deduction_value': ['15']}
        response = self.client.post(reverse('sandbox:index'), data)
        self.assertIsNone(response.context['result'])
        self.assertContains(response, 'Enter at most 20 complete rows')
        self.assertEqual(len(response.context['variable_rows']), 3)
        self.assertContains(response, 'value="unfinished"')
        self.assertContains(response, 'value="123.45"')
        self.assertContains(response, 'value="Missing amount"')
        data.update(action='save', draft_name='Unbalanced input')
        response = self.client.post(reverse('sandbox:index'), data)
        draft = ScenarioDraft.objects.get()
        self.assertFalse(draft.payload['complete'])
        self.assertEqual(draft.payload['inputs']['variable_label'], ['Rent'])
        self.assertEqual(draft.payload['inputs']['variable_value'], ['10.00', 'unfinished', '123.45'])
        self.assertEqual(draft.payload['inputs']['deduction_label'], ['Tax', 'Missing amount'])
        opened = self.client.get(response.url)
        self.assertEqual(len(opened.context['variable_rows']), 3)
        self.assertContains(opened, 'value="unfinished"')
        self.assertContains(opened, 'value="Missing amount"')

    def test_calculation_is_always_brl_despite_presentation_currency(self):
        from accounts.models import UserPreference
        UserPreference.objects.update_or_create(user=self.user, defaults={'base_currency': 'USD'})
        response = self.client.post(reverse('sandbox:index'), {'gross_salary': '5000'})
        self.assertContains(response, 'R$ 5.000,00')
        self.assertEqual(response.context['CURRENCY_SYMBOL'], 'R$')


class CommitmentProjectionTests(TestCase):
    def setUp(self):
        from datetime import date
        from banking.models import Bank, BankAccount, CreditCard
        from categories.models import Category
        from transactions.models import Transaction
        self.user = User.objects.create_user('commitments', password='test')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Checking', currency='BRL')
        self.card = CreditCard.objects.create(user=self.user, account=self.account, name='Card', closing_day=24, due_day=1)
        self.category = Category.objects.filter(user=self.user).first()
        self.purchase = Transaction.objects.create(user=self.user, title='Three payments', amount=D('100'),
            transaction_type='EXPENSE', category=self.category, payment_channel='CREDIT_CARD',
            credit_card=self.card, installments=3, date=date(2026, 8, 25))

    def test_normal_recurring_volume_supports_real_encoded_post_over_one_thousand_fields(self):
        from datetime import date
        from urllib.parse import urlencode
        from transactions.models import Transaction
        from sandbox.planning import commitment_snapshot
        from sandbox.views import _snapshot_token
        Transaction.objects.bulk_create([
            Transaction(user=self.user, title=f'Recurring {index}', amount=D('10'),
                transaction_type='EXPENSE', category=self.category, payment_channel='ACCOUNT',
                bank_account=self.account, is_fixed=True, date=date(2026, 10, 2))
            for index in range(30)
        ])
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        data = {'action': 'save', 'draft_name': 'Recurring obligations', 'gross_salary': '5000',
                'planning_month': '2026-10', 'expense_basis': 'recorded',
                'snapshot_token': _snapshot_token(snapshot)}
        for index in range(len(snapshot['rows'])):
            data.update({f'commitment_present_{index}': '1', f'commitment_include_{index}': 'on',
                         f'commitment_amount_{index}': ''})
        self.assertGreater(len(data), 1000)
        response = self.client.post(reverse('sandbox:index'), urlencode(data),
                                    content_type='application/x-www-form-urlencoded')
        draft = ScenarioDraft.objects.get()
        self.assertRedirects(response, reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertTrue(draft.payload['complete'])
        self.assertEqual(len(draft.payload['snapshot']['rows']), len(snapshot['rows']))

    def test_capture_and_merge_limits_preserve_previous_snapshot_without_truncation(self):
        from datetime import date
        from unittest.mock import patch
        from sandbox.planning import commitment_snapshot
        from sandbox.views import _snapshot_token
        previous = commitment_snapshot(self.user, date(2026, 10, 1))
        data = {'action': 'refresh', 'gross_salary': '5000', 'planning_month': '2026-10',
                'expense_basis': 'recorded', 'snapshot_token': _snapshot_token(previous)}
        with patch('sandbox.planning.MAX_COMMITMENTS', 2):
            response = self.client.post(reverse('sandbox:index'), data)
        self.assertContains(response, 'A snapshot supports at most 2 commitments')
        self.assertEqual(response.context['snapshot'], previous)
        self.assertIsNone(response.context['refresh_preview'])
        self.purchase.delete()
        # Removed records retained in the scenario also count toward the limit.
        with patch('sandbox.planning.MAX_COMMITMENTS', 2):
            response = self.client.post(reverse('sandbox:index'), data)
        self.assertContains(response, 'A snapshot supports at most 2 commitments')
        self.assertEqual(response.context['snapshot'], previous)
        self.assertIsNone(response.context['refresh_preview'])

    def test_payment_month_remainders_card_costs_and_no_invoice_duplication_or_writes(self):
        from datetime import date
        from banking.models import CardInvoice, LoyaltyEntry, LoyaltyProgram
        from sandbox.planning import commitment_snapshot
        CardInvoice.objects.create(user=self.user, card=self.card, reference_month=date(2026, 9, 1), due_date=date(2026, 10, 1), amount=999)
        program = LoyaltyProgram.objects.create(user=self.user, name='Miles', unit_name='points')
        LoyaltyEntry.objects.create(user=self.user, program=program, direction='CREDIT', kind='PURCHASE', amount=100,
            cash_amount=50, funding_credit_card=self.card, date=date(2026, 9, 5))
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        installments = [row for row in snapshot['rows'] if row['kind'] == 'installment']
        self.assertEqual([row['amount'] for row in installments], ['33.34', '33.33', '33.33'])
        self.assertEqual([row['payment_date'] for row in installments], ['2026-10-01', '2026-11-01', '2026-12-01'])
        self.assertEqual(len(snapshot['rows']), 4)
        self.assertEqual(sum(D(row['amount']) for row in snapshot['rows']), D('150'))
        self.assertEqual(self.user.bank_movements.count(), 0)
        self.assertEqual(CardInvoice.objects.get().amount, D('999'))

    def test_refresh_keeps_overrides_exclusions_and_removed_sources(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot, merge_snapshot
        previous = commitment_snapshot(self.user, date(2026, 10, 1))
        previous['rows'][0]['override'] = '25.00'
        previous['rows'][1]['included'] = False
        self.purchase.amount = D('120')
        self.purchase.save()
        refreshed = merge_snapshot(previous, commitment_snapshot(self.user, date(2026, 10, 1)))
        self.assertEqual(refreshed['rows'][0]['override'], '25.00')
        self.assertEqual(refreshed['rows'][0]['amount'], '40.00')
        self.assertFalse(refreshed['rows'][1]['included'])
        self.purchase.delete()
        refreshed = merge_snapshot(refreshed, commitment_snapshot(self.user, date(2026, 10, 1)))
        self.assertEqual(len(refreshed['rows']), 3)
        self.assertTrue(all(row['source_removed'] for row in refreshed['rows']))

    def test_capture_review_explicit_save_and_stable_reopen(self):
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'refresh', 'planning_month': '2026-10', 'expense_basis': 'recorded', 'gross_salary': '5000',
        })
        self.assertContains(response, 'Review commitment refresh')
        self.assertIsNone(response.context['snapshot'])
        preview_token = response.context['preview_token']
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'apply_refresh', 'planning_month': '2026-10', 'expense_basis': 'recorded',
            'gross_salary': '5000', 'preview_token': preview_token,
        })
        token = response.context['snapshot_token']
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'October', 'planning_month': '2026-10', 'expense_basis': 'recorded',
            'gross_salary': '5000', 'fixed_cost_type': 'percent', 'fixed_cost_value': '50',
            'snapshot_token': token,
        })
        draft = ScenarioDraft.objects.get()
        self.purchase.amount = D('300')
        self.purchase.save()
        response = self.client.get(reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertEqual(response.context['result']['budget'].fixed_bills, D('33.34'))
        self.assertEqual(response.context['result']['budget'].remaining, D('4966.66'))
        self.assertEqual(self.user.bank_movements.count(), 0)

    def test_missing_fx_blocks_selected_commitment_until_overridden(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot, snapshot_total
        self.account.currency = 'USD'
        self.account.save()
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        self.assertIsNone(snapshot['rows'][0]['amount'])
        with self.assertRaises(ValidationError):
            snapshot_total(snapshot, '2026-10')
        snapshot['rows'][0]['override'] = '170.00'
        self.assertEqual(snapshot_total(snapshot, '2026-10'), D('170.00'))

    def test_date_or_billing_changes_keep_the_same_obligation_identity(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot, merge_snapshot
        previous = commitment_snapshot(self.user, date(2026, 9, 1))
        previous['rows'][0]['override'] = '25.00'
        previous['rows'][0]['included'] = False
        self.purchase.billing_override = 0
        self.purchase.save()
        refreshed = merge_snapshot(previous, commitment_snapshot(self.user, date(2026, 9, 1)))
        self.assertEqual(len(refreshed['rows']), 3)
        self.assertEqual(refreshed['rows'][0]['override'], '25.00')
        self.assertFalse(refreshed['rows'][0]['included'])
        self.assertEqual(refreshed['rows'][0]['payment_date'], '2026-09-01')
        self.purchase.installments = 1
        self.purchase.save()
        previous = commitment_snapshot(self.user, date(2026, 9, 1))
        previous['rows'][0]['override'] = '75.00'
        previous['rows'][0]['included'] = False
        self.purchase.date = date(2026, 10, 5)
        self.purchase.save()
        refreshed = merge_snapshot(previous, commitment_snapshot(self.user, date(2026, 9, 1)))
        self.assertEqual(len(refreshed['rows']), 1)
        self.assertFalse(refreshed['rows'][0]['included'])
        self.assertEqual(refreshed['rows'][0]['override'], '75.00')
        self.assertEqual(refreshed['rows'][0]['payment_date'], '2026-11-01')

    def test_foreign_snapshot_signature_is_not_accepted(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot
        from sandbox.views import _snapshot_token
        token = _snapshot_token(commitment_snapshot(self.user, date(2026, 10, 1)))
        other = User.objects.create_user('snapshot-other', password='test')
        self.client.force_login(other)
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Foreign', 'snapshot_token': token, 'gross_salary': '5000',
        })
        self.assertContains(response, 'snapshot is invalid')
        self.assertEqual(ScenarioDraft.objects.count(), 0)


class YieldSimulationTests(TestCase):
    def test_month_end_cashflows_and_effective_annual_rate(self):
        from datetime import date
        from sandbox.planning import simulate_yield
        result = simulate_yield(initial=D('100'), start_month=date(2026, 12, 1), months=2, rate=D('1'),
            rate_period='monthly', contribution=D('100'), withdrawal=D('0'), overrides={})
        self.assertEqual([row['closing'] for row in result['rows']], [D('201.00'), D('303.01')])
        self.assertEqual(result['rows'][1]['month'], date(2027, 1, 1))
        annual = simulate_yield(initial=D('1000'), start_month=date(2026, 1, 1), months=12, rate=D('12'),
            rate_period='annual', contribution=D('0'), withdrawal=D('0'), overrides={})
        self.assertLess(abs(annual['ending'] - D('1120')), D('.10'))
        self.assertLess(annual['monthly_rate'], D('1'))

    def test_negative_rate_explicit_zero_override_and_overdraw_rejection(self):
        from datetime import date
        from sandbox.planning import simulate_yield
        result = simulate_yield(initial=D('100'), start_month=date(2026, 1, 1), months=1, rate=D('-10'),
            rate_period='monthly', contribution=D('100'), withdrawal=D('0'), overrides={0: (D('0'), D('0'))})
        self.assertEqual(result['ending'], D('90'))
        with self.assertRaises(ValidationError):
            simulate_yield(initial=D('100'), start_month=date(2026, 1, 1), months=1, rate=D('0'),
                rate_period='monthly', contribution=D('0'), withdrawal=D('101'), overrides={})

    def test_form_rejects_incomplete_nonfinite_rate_and_invalid_override(self):
        from sandbox.forms import YieldSimulationForm
        defaults = {'currency': 'BRL', 'start_month': '2026-09', 'months': '12', 'initial_balance': '1000',
            'rate': '1', 'rate_period': 'monthly', 'contribution': '0', 'withdrawal': '0'}
        for change in ({'rate': 'NaN'}, {'rate': '-100'}, {'months': '121'}, {'initial_balance': ''}, {'withdrawal_0': 'Infinity'}):
            with self.subTest(change=change):
                self.assertFalse(YieldSimulationForm({**defaults, **change}).is_valid())
