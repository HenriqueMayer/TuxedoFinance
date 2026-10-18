"""Workspace coverage for sandbox."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override
from sandbox.forms import SalarySandboxForm
from sandbox.services import CltScenario, calculate_clt
from sandbox.tax_rules import get_tax_rules
from sandbox.models import ScenarioDraft


D = Decimal


User = get_user_model()


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
