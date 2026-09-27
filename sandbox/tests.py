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

    def test_get_shows_the_simple_month_plan_and_optional_save(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('sandbox:index'))
        self.assertContains(response, 'Salary Sandbox')
        self.assertContains(response, 'name="gross_salary"')
        self.assertContains(response, 'name="planning_month"')
        self.assertEqual(response.context['variable_rows'], [
            {'label': 'Emergency reserve', 'value_type': 'currency', 'value': '0.00'},
            {'label': 'Investment', 'value_type': 'currency', 'value': '0.00'},
        ])
        self.assertContains(response, 'type="month"')
        self.assertContains(response, 'Existing expense forecast')
        self.assertContains(response, 'Additional fixed expenses')
        self.assertContains(response, 'Save this plan (optional)')
        self.assertNotContains(response, 'name="use_clt"')
        self.assertNotContains(response, 'name="deduction_label"')
        self.assertNotContains(response, 'name="fixed_cost_value"')

    def test_removed_default_rows_stay_removed_across_month_changes_and_drafts(self):
        self.client.force_login(self.user)
        data = {'gross_salary': '5000', 'planning_month': '2026-10',
                'variable_label': ['Emergency reserve', 'Investment'],
                'variable_type': ['currency', 'currency'], 'variable_value': ['0.00', '0.00']}
        response = self.client.post(reverse('sandbox:index'), {**data, 'action': 'remove_variable_0'})
        self.assertEqual([row['label'] for row in response.context['variable_rows']], ['Investment'])
        remaining = {**data, 'variable_label': ['Investment'],
                     'variable_type': ['percent'], 'variable_value': ['10']}
        response = self.client.post(reverse('sandbox:index'), {**remaining, 'action': 'next_month'})
        self.assertEqual([row['label'] for row in response.context['variable_rows']], ['Investment'])
        response = self.client.post(reverse('sandbox:index'), {
            **remaining, 'action': 'save', 'draft_name': 'Investment only',
        }, follow=True)
        self.assertEqual([row['label'] for row in response.context['variable_rows']], ['Investment'])
        self.assertEqual(response.context['result']['budget'].custom_expenses, D('500'))
        response = self.client.post(reverse('sandbox:index'), {
            **remaining, 'variable_value': ['invalid'], 'action': 'calculate',
        })
        self.assertEqual([row['label'] for row in response.context['variable_rows']], ['Investment'])
        self.assertEqual(response.context['variable_rows'][0]['value'], 'invalid')

    def test_post_uses_clt_net_salary_and_added_fixed_expenses(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '6000',
            'planning_month': '2026-10',
            'variable_label': ['Rent', 'Utilities'],
            'variable_type': ['currency', 'currency'],
            'variable_value': ['1500', '250'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Monthly estimate')
        self.assertContains(response, 'Rent')
        self.assertContains(response, 'Utilities')
        self.assertEqual(response.context['result']['budget'].remaining, D('3223.39'))
        self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_monthly_plan_applies_clt_bands_before_gross_based_percent_expenses(self):
        self.client.force_login(self.user)
        for gross, inss, irrf, net in [
            ('1621', '121.58', '0.00', '1499.42'),
            ('2902.84', '236.94', '0.00', '2665.90'),
            ('4354.27', '411.11', '0.00', '3943.16'),
            ('5000', '501.51', '0.00', '4498.49'),
            ('6000', '641.51', '385.10', '4973.39'),
            ('8000', '921.51', '1037.85', '6040.64'),
            ('10000', '988.09', '1569.55', '7442.36'),
        ]:
            with self.subTest(gross=gross):
                response = self.client.post(reverse('sandbox:index'), {
                    'gross_salary': gross, 'planning_month': '2026-10',
                    'variable_label': ['Reserve'], 'variable_type': ['percent'],
                    'variable_value': ['10'],
                })
                result = response.context['result']
                self.assertEqual(result['payroll'].inss, D(inss))
                self.assertEqual(result['payroll'].irrf, D(irrf))
                self.assertEqual(result['budget'].income, D(net))
                self.assertEqual(result['budget'].custom_expenses, (D(gross) / 10).quantize(D('.01')))
                self.assertEqual(result['budget'].remaining, D(net) - result['budget'].custom_expenses)
                self.assertContains(response, 'Net in an ordinary month')

    def test_legacy_gross_plan_is_preserved_until_recalculated(self):
        self.client.force_login(self.user)
        self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Legacy', 'gross_salary': '5000',
            'planning_month': '2026-10',
        })
        draft = ScenarioDraft.objects.get()
        draft.payload['calculation_version'] = 1
        draft.save()
        opened = self.client.get(reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertEqual(opened.context['result']['budget'].income, D('5000'))
        self.assertContains(opened, 'Saved plan without CLT deductions')
        compared = self.client.get(reverse('sandbox:compare'), {'draft': draft.pk})
        self.assertEqual(compared.context['scenarios'][0]['result']['budget'].income, D('5000'))
        calculated = self.client.post(reverse('sandbox:draft_detail', args=[draft.pk]), {
            'action': 'calculate', 'gross_salary': '5000', 'planning_month': '2026-10',
        })
        self.assertEqual(calculated.context['result']['budget'].income, D('4498.49'))
        draft.refresh_from_db()
        self.assertEqual(draft.payload['calculation_version'], 1)
        self.client.post(reverse('sandbox:draft_detail', args=[draft.pk]), {
            'action': 'save', 'draft_name': 'Updated', 'gross_salary': '5000',
            'planning_month': '2026-10',
        })
        draft.refresh_from_db()
        self.assertEqual(draft.payload['calculation_version'], 2)
        compared = self.client.get(reverse('sandbox:compare'), {'draft': draft.pk})
        self.assertEqual(compared.context['scenarios'][0]['result']['budget'].income, D('4498.49'))


    def test_tax_brackets_follow_current_inputs_and_adjusted_irrf_base(self):
        self.client.force_login(self.user)
        data = {'action': 'tax_bands', 'gross_salary': '6000', 'planning_month': '2026-10',
                'clt_dependents': '2', 'clt_pension': '500', 'clt_transport': '100',
                'clt_food': '50', 'clt_health': '100', 'clt_other': '25'}
        response = self.client.post(reverse('sandbox:index'), data)
        result = response.context['result']
        self.assertTrue(response.context['tax_bands_open'])
        self.assertTrue(response.context['clt_settings_open'])
        self.assertEqual(result['payroll'].irrf_base, D('4479.31'))
        self.assertEqual(result['payroll'].deductions, D('775'))
        self.assertEqual(result['payroll'].net, D('4430.89'))
        self.assertEqual([r['rate'] for r in result['tax_bands']['inss'] if r['selected']], [D('14')])
        self.assertEqual([r['rate'] for r in result['tax_bands']['irrf'] if r['selected']], [D('22.5')])
        self.assertEqual(result['tax_bands']['reduction_band'], 'partial')
        self.assertContains(response, 'aria-current="true"', count=3)
        self.assertEqual(ScenarioDraft.objects.count(), 0)
        saved = self.client.post(reverse('sandbox:index'), {
            **data, 'action': 'save', 'draft_name': 'Adjusted CLT',
        }, follow=True)
        self.assertEqual(saved.context['result']['payroll'].net, D('4430.89'))
        self.assertEqual(saved.context['form']['clt_dependents'].value(), '2')
        draft = ScenarioDraft.objects.get()
        compared = self.client.get(reverse('sandbox:compare'), {'draft': draft.pk})
        self.assertEqual(compared.context['scenarios'][0]['result']['payroll'].net, D('4430.89'))
        moved = self.client.post(reverse('sandbox:index'), {**data, 'action': 'next_month'})
        self.assertEqual(moved.context['form']['clt_pension'].value(), '500')
        for name, value in [('clt_dependents', '-1'), ('clt_dependents', '1.5'),
                            ('clt_health', 'NaN'), ('clt_pension', '-1')]:
            with self.subTest(name=name, value=value):
                invalid = self.client.post(reverse('sandbox:index'), {**data, name: value})
                self.assertIsNone(invalid.context['result'])
                self.assertTrue(invalid.context['clt_settings_open'])
                self.assertEqual(invalid.context['form'][name].value(), value)

    def test_tax_bracket_boundaries_ceiling_and_reduction(self):
        from sandbox.services import payroll_brackets
        rules = get_tax_rules()
        for gross, rate, reduction in [('1621', '7.5', 'zero'), ('1621.01', '9', 'zero'),
                                       ('5000', '14', 'zero'), ('5000.01', '14', 'partial'),
                                       ('7350', '14', 'partial'), ('7350.01', '14', 'none'),
                                       ('10000', '14', 'none')]:
            with self.subTest(gross=gross):
                brackets = payroll_brackets(calculate_clt(CltScenario(D(gross))).ordinary, rules)
                self.assertEqual([r['rate'] for r in brackets['inss'] if r['selected']], [D(rate)])
                self.assertEqual(brackets['reduction_band'], reduction)
                self.assertEqual(brackets['above_ceiling'], D(gross) > D('8475.55'))

    def test_fragment_post_replaces_only_one_workspace(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '5000',
            'planning_month': '2026-10',
            'response_mode': 'fragment',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sandbox-workspace"', count=1)
        self.assertContains(response, 'Monthly estimate')
        self.assertNotContains(response, '<html')
        self.assertNotContains(response, '<header')

    def test_result_has_accessible_help_and_no_persistence(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '5000',
            'planning_month': '2026-10',
        })
        self.assertContains(response, 'aria-describedby="id_gross_salary-help"')
        self.assertContains(response, 'id="id_gross_salary-help"', count=1)
        self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_forecast_action_does_not_require_salary(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'forecast', 'planning_month': '2026-10',
        })
        self.assertNotContains(response, 'Enter the gross monthly salary.')
        self.assertEqual(response.context['forecast']['month'].isoformat(), '2026-10-01')

    def test_added_expenses_accept_percentage_payloads(self):
        form = SalarySandboxForm(data={
            'gross_salary': '5000', 'planning_month': '2026-10',
            'variable_label': ['Tax'], 'variable_type': ['percent'], 'variable_value': ['10'],
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_percentage_expenses_round_and_survive_draft_reopening(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:index'), {
            'gross_salary': '1234.56', 'planning_month': '2026-10',
            'variable_label': ['Rent', 'Savings'], 'variable_type': ['currency', 'percent'],
            'variable_value': ['100', '12.5'], 'action': 'save', 'draft_name': 'Mixed expenses',
        }, follow=True)
        self.assertEqual(response.context['result']['budget'].custom_expenses, D('254.32'))
        self.assertEqual(response.context['result']['budget'].remaining, D('887.65'))
        self.assertEqual(response.context['variable_rows'][1]['value_type'], 'percent')
        self.assertEqual(response.context['variable_rows'][1]['value'], '12.50')

    def test_percentage_expenses_reject_out_of_range_and_preserve_input(self):
        self.client.force_login(self.user)
        for value in ('101', '-1', 'NaN', '1.001'):
            with self.subTest(value=value):
                response = self.client.post(reverse('sandbox:index'), {
                    'gross_salary': '5000', 'planning_month': '2026-10',
                    'variable_label': ['Tax'], 'variable_type': ['percent'], 'variable_value': [value],
                })
                self.assertIsNone(response.context['result'])
                self.assertEqual(response.context['variable_rows'][0]['value'], value)
                self.assertContains(response, '0–100')

    def test_month_arrows_preserve_rows_and_cross_year_without_saving(self):
        self.client.force_login(self.user)
        for action, month, expected in (('next_month', '2026-12', '2027-01'),
                                         ('previous_month', '2026-01', '2025-12')):
            response = self.client.post(reverse('sandbox:index'), {
                'action': action, 'planning_month': month, 'gross_salary': '5000',
                'variable_label': ['Tax'], 'variable_type': ['percent'], 'variable_value': ['10'],
            })
            self.assertEqual(response.context['form']['planning_month'].value(), expected)
            self.assertEqual(response.context['form']['gross_salary'].value(), '5000')
            self.assertEqual(response.context['variable_rows'][0]['value_type'], 'percent')
            self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_invalid_month_text_remains_editable(self):
        from sandbox.forms import YieldSimulationForm
        for form_class, name in ((SalarySandboxForm, 'planning_month'), (YieldSimulationForm, 'start_month')):
            with self.subTest(name=name):
                form = form_class(data={name: 'invalid-month'})
                self.assertIn('invalid-month', str(form[name]))
                self.assertIn('type="text"', str(form[name]))

    def test_page_uses_the_pt_br_catalog(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'pt-br'
        with override('pt-br'):
            response = self.client.get(reverse('sandbox:index'))
        self.assertContains(response, 'Sandbox de Salário')
        self.assertContains(response, 'Previsão de despesas existente')
        self.assertContains(response, 'Despesas fixas adicionais')
        self.assertContains(response, 'value="Reserva de emergência"')
        self.assertContains(response, 'value="Investimento"')
        self.assertContains(response, 'Salvar este plano (opcional)')
        self.assertNotContains(response, 'Calcular descontos CLT')
        with override('pt-br'):
            calculated = self.client.post(reverse('sandbox:index'), {
                'gross_salary': '6000', 'planning_month': '2026-10',
            })
        self.assertContains(calculated, 'Líquido em um mês comum')
        self.assertContains(calculated, 'R$ 4.973,39')
        self.assertContains(calculated, 'regras tributárias de 2026')
        with override('pt-br'):
            tables = self.client.post(reverse('sandbox:index'), {
                'action': 'tax_bands', 'gross_salary': '6000', 'planning_month': '2026-10',
            })
        self.assertContains(tables, 'Consultar faixas de INSS e IRRF')
        self.assertContains(tables, 'Ajustar parâmetros CLT')
        self.assertContains(tables, 'Sua faixa', count=3)
        self.assertContains(tables, 'Redução parcial do imposto de renda.')
        self.assertContains(tables, '6% do bruto')




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

        reference_snapshot = commitment_snapshot(
            self.user, date(2026, 9, 1), month_basis='reference_month',
        )
        from sandbox.planning import snapshot_total
        self.assertEqual(snapshot_total(reference_snapshot, '2026-09'), D('83.34'))
        self.assertEqual(snapshot_total(reference_snapshot, '2026-10'), D('33.33'))
        self.assertEqual(snapshot_total(reference_snapshot, '2026-11'), D('33.33'))
        self.assertEqual(snapshot_total(reference_snapshot, '2026-12'), D('0'))

    def test_reference_month_matches_report_across_card_due_months(self):
        from datetime import date
        from dashboard.services import get_instrument_activity
        from transactions.models import Transaction
        self.purchase.delete()
        for title, amount, month, card in [
            ('September Black', '3732.71', 9, True),
            ('September Roxinho', '613.84', 9, True),
            ('September Visa', '499.36', 9, True),
            ('September account', '75', 9, False),
            ('October Black', '1275.30', 10, True),
            ('October Roxinho', '613.84', 10, True),
        ]:
            Transaction.objects.create(
                user=self.user, title=title, amount=D(amount), transaction_type='EXPENSE',
                category=self.category, payment_channel='CREDIT_CARD' if card else 'ACCOUNT',
                credit_card=self.card if card else None, bank_account=None if card else self.account,
                date=date(2026, month, 5),
            )
        for month, expected, count in [(9, '4920.91', 4), (10, '1889.14', 2), (11, '0', 0)]:
            with self.subTest(month=month):
                response = self.client.post(reverse('sandbox:index'), {
                    'action': 'forecast', 'planning_month': f'2026-{month:02}',
                })
                forecast = response.context['forecast']
                self.assertEqual(forecast['total'], D(expected))
                self.assertEqual(forecast['count'], count)
                report = get_instrument_activity(self.user, 2026, month)
                self.assertEqual(forecast['total'], report['expense_total'])

    def test_legacy_saved_snapshot_keeps_payment_basis(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot
        self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Legacy', 'planning_month': '2026-10',
            'gross_salary': '5000',
        })
        draft = ScenarioDraft.objects.get()
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        snapshot.pop('month_basis')
        draft.payload['calculation_version'] = 1
        draft.payload['snapshot'] = snapshot
        draft.save()
        opened = self.client.get(reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertEqual(opened.context['forecast']['total'], D('33.34'))
        compared = self.client.get(reverse('sandbox:compare'), {'draft': draft.pk})
        self.assertEqual(compared.context['scenarios'][0]['result']['budget'].fixed_bills, D('33.34'))

    def test_selected_month_forecast_is_used_automatically(self):
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'forecast', 'planning_month': '2026-10',
        })
        self.assertEqual(response.context['forecast']['total'], D('33.33'))
        self.assertEqual(response.context['forecast']['count'], 1)
        self.assertContains(response, 'R$ 33,33')
        self.assertIsNone(response.context['result'])

        response = self.client.post(reverse('sandbox:index'), {
            'action': 'calculate', 'planning_month': '2026-10', 'gross_salary': '5000',
            'variable_label': ['Rent'], 'variable_type': ['currency'], 'variable_value': ['450'],
        })
        self.assertEqual(response.context['result']['budget'].fixed_bills, D('33.33'))
        self.assertEqual(response.context['result']['budget'].custom_expenses, D('450.00'))
        self.assertEqual(response.context['result']['budget'].remaining, D('4015.16'))
        self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_forecast_changes_with_the_selected_month(self):
        october = self.client.post(reverse('sandbox:index'), {
            'action': 'forecast', 'planning_month': '2026-10',
        })
        december = self.client.post(reverse('sandbox:index'), {
            'action': 'forecast', 'planning_month': '2026-12',
        })
        self.assertEqual(october.context['forecast']['total'], D('33.33'))
        self.assertEqual(december.context['forecast']['total'], D('0.00'))

    def test_optional_save_keeps_a_stable_forecast_snapshot(self):
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'October', 'planning_month': '2026-10',
            'gross_salary': '5000',
        })
        draft = ScenarioDraft.objects.get()
        self.assertRedirects(response, reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertTrue(draft.payload['complete'])
        self.assertTrue(draft.payload['snapshot']['rows'])
        self.purchase.amount = D('300')
        self.purchase.save()
        reopened = self.client.get(reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertEqual(reopened.context['result']['budget'].fixed_bills, D('33.33'))
        self.assertEqual(reopened.context['result']['budget'].remaining, D('4465.16'))
        self.assertTrue(reopened.context['draft_save_open'])
        compared = self.client.get(reverse('sandbox:compare'), {'draft': draft.pk})
        self.assertEqual(compared.context['scenarios'][0]['result']['budget'].fixed_bills, D('33.33'))

    def test_missing_fx_marks_forecast_incomplete_and_blocks_calculation(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot, snapshot_total
        self.account.currency = 'USD'
        self.account.save()
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        self.assertIsNone(snapshot['rows'][0]['amount'])
        with self.assertRaises(ValidationError):
            snapshot_total(snapshot, '2026-10')
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'calculate', 'planning_month': '2026-10', 'gross_salary': '5000',
        })
        self.assertIsNone(response.context['forecast']['total'])
        self.assertIsNone(response.context['result'])
        self.assertContains(response, 'Incomplete forecast')
        self.assertContains(response, 'exchange rate')


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
