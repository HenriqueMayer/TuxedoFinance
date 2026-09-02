from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
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

    def test_variable_parser_limits_invalid_and_excess_rows(self):
        data = _MultiValueData({
            'deduction_label': ['Tax'] * 22,
            'deduction_type': ['percent'] * 22,
            'deduction_value': ['10'] * 21 + ['101'],
        })
        variables = variables_from_data(data, 'deduction')
        self.assertEqual(len(variables), 20)
        self.assertTrue(all(variable.value == D('10') for variable in variables))


class _MultiValueData(dict):
    def getlist(self, key):
        return self.get(key, [])


class SandboxViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sandbox', password='test')

    def test_page_requires_authentication(self):
        response = self.client.get(reverse('sandbox:index'))
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={reverse("sandbox:index")}')

    def test_get_shows_one_salary_and_defaults_to_automatic_clt(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('sandbox:index'))
        self.assertContains(response, 'Salary Sandbox')
        self.assertContains(response, 'name="gross_salary"')
        self.assertContains(response, 'name="use_clt"')
        self.assertContains(response, 'name="use_clt"', count=1)
        self.assertContains(response, 'data-clt-options')
        self.assertContains(response, 'data-manual-options hidden')
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
        self.assertNotContains(response, 'Manual calculation')

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
        self.assertFalse(any(table.startswith('sandbox_') for table in connection.introspection.table_names()))

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
