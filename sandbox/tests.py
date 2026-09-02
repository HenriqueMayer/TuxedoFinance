from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils.translation import override
from django.urls import reverse

from sandbox.forms import SalarySandboxForm
from sandbox.services import (
    BudgetInput,
    CltScenario,
    CustomBudgetVariable,
    PjScenario,
    build_budget,
    calculate_clt,
    calculate_pj,
    calculate_pj_presumido,
    dividend_withholding,
    individual_inss,
    irrf_tax,
    solve_equivalent_clt,
    solve_equivalent_pj,
)
from sandbox.tax_rules import get_tax_rules


D = Decimal
User = get_user_model()


class SandboxCalculationTests(TestCase):
    def test_clt_inss_uses_progressive_2026_bands(self):
        result = calculate_clt(CltScenario(D('2902.84')))
        self.assertEqual(result.ordinary.inss, D('236.94'))

        result = calculate_clt(CltScenario(D('10000.00')))
        self.assertEqual(result.ordinary.inss, D('988.09'))
        self.assertEqual(individual_inss(D('10000.00'), get_tax_rules()), D('932.31'))

    def test_irrf_2026_reduction_and_simplified_deduction(self):
        tax_at_five_thousand, _, _ = irrf_tax(D('5000.00'), 0, D('0'), get_tax_rules(), deductible_inss=D('1000.00'))
        tax_above_reduction = calculate_clt(CltScenario(D('7600.00'))).ordinary.irrf
        self.assertEqual(tax_at_five_thousand, D('0.00'))
        self.assertGreater(tax_above_reduction, D('0.00'))

    def test_irrf_chooses_the_lowest_taxable_base(self):
        _, simplified_base, simplified_method = irrf_tax(
            D('8000'), 0, D('0'), get_tax_rules(), deductible_inss=D('200'),
        )
        _, legal_base, legal_method = irrf_tax(
            D('8000'), 10, D('0'), get_tax_rules(), deductible_inss=D('800'),
        )
        self.assertEqual(simplified_method, 'simplified')
        self.assertEqual(simplified_base, D('7392.80'))
        self.assertEqual(legal_method, 'legal')
        self.assertEqual(legal_base, D('5304.10'))

    def test_clt_annualizes_ordinary_months_vacation_and_thirteenth(self):
        result = calculate_clt(CltScenario(D('5000.00'), employer_benefits=D('300.00')))
        self.assertEqual(
            result.annual_net,
            result.ordinary.net * 11 + result.vacation.net + result.thirteenth.net,
        )
        self.assertEqual(result.annual_employer_benefits, D('3600.00'))
        self.assertEqual(result.annual_worker_value, result.annual_net + result.annual_fgts + D('3600.00'))

    def test_employer_profiles_change_recurring_cost(self):
        general = calculate_clt(CltScenario(D('5000.00'), employer_profile='general'))
        simple = calculate_clt(CltScenario(D('5000.00'), employer_profile='simple_iii_v'))
        self.assertGreater(general.annual_employer_cost, simple.annual_employer_cost)

    def test_simples_factor_r_boundary_is_truncated_before_selection(self):
        below = calculate_pj(PjScenario(D('10000'), prior_revenue=D('100000'), prior_payroll=D('27999')))
        at_boundary = calculate_pj(PjScenario(D('10000'), prior_revenue=D('100000'), prior_payroll=D('28000')))
        self.assertEqual(below.factor_r, D('0.27'))
        self.assertEqual(below.annex.split(' · ')[0], 'Anexo V')
        self.assertEqual(at_boundary.factor_r, D('0.28'))
        self.assertEqual(at_boundary.annex.split(' · ')[0], 'Anexo III')

    def test_simples_catalog_exposes_all_six_bands_for_both_annexes(self):
        for annex_target, expected in ((D('180000'), 'III'), (D('360000'), 'III'), (D('720000'), 'III'), (D('1800000'), 'III'), (D('3600000'), 'III'), (D('4800000'), 'III')):
            result = calculate_pj(PjScenario(D('1000'), prior_revenue=annex_target, prior_payroll=annex_target * D('.28')))
            self.assertEqual(result.annex.split(' · ')[0], f'Anexo {expected}')
        for annex_target in (D('180000'), D('360000'), D('720000'), D('1800000'), D('3600000'), D('4800000')):
            result = calculate_pj(PjScenario(D('1000'), prior_revenue=annex_target, prior_payroll=D('0')))
            self.assertEqual(result.annex.split(' · ')[0], 'Anexo V')

    def test_simples_startup_uses_proportional_revenue_and_factor_r(self):
        first = calculate_pj(PjScenario(D('10000'), pro_labore=D('3000'), company_age_months=1))
        second = calculate_pj(PjScenario(D('10000'), pro_labore=D('3000'), company_age_months=2, prior_revenue=D('10000'), prior_payroll=D('3000')))
        self.assertEqual(first.factor_r, D('0.30'))
        self.assertEqual(first.annex.split(' · ')[0], 'Anexo III')
        self.assertEqual(second.annual_revenue, D('110000.00'))

    def test_simples_months_12_and_13_use_their_distinct_history_rules(self):
        month_twelve = calculate_pj(PjScenario(
            D('10000'), company_age_months=12, prior_revenue=D('110000'), prior_payroll=D('30800'),
        ))
        month_thirteen = calculate_pj(PjScenario(
            D('10000'), company_age_months=13, prior_revenue=D('120000'), prior_payroll=D('33600'),
        ))
        self.assertEqual(month_twelve.factor_r, D('0.28'))
        self.assertEqual(month_thirteen.factor_r, D('0.28'))

    def test_simples_zero_denominators_and_limit_are_explicit(self):
        no_history = calculate_pj(PjScenario(D('10000'), company_age_months=13))
        payroll_only = calculate_pj(PjScenario(D('10000'), company_age_months=13, prior_payroll=D('1000')))
        over_limit = calculate_pj(PjScenario(D('500000'), months_billed=12, prior_revenue=D('4900001')))
        self.assertEqual(no_history.factor_r, D('0.01'))
        self.assertEqual(payroll_only.factor_r, D('0.28'))
        self.assertFalse(over_limit.valid)

    def test_simples_requires_manual_iss_when_sublimit_is_exceeded(self):
        form = SalarySandboxForm(data={
            'scenario_type': 'pj', 'pj_revenue': '400000', 'pj_regime': 'simples',
            'pro_labore': '5000', 'months_billed': '12', 'company_age_months': '13',
            'prior_revenue': '4000000', 'prior_payroll': '0',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('iss_outside_monthly', form.errors)

    def test_mature_simples_requires_previous_revenue_history(self):
        form = SalarySandboxForm(data={
            'scenario_type': 'pj', 'pj_revenue': '7000', 'pj_regime': 'simples',
            'pro_labore': '1621', 'months_billed': '11', 'company_age_months': '13',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('prior_revenue', form.errors)

    def test_presumido_includes_business_taxes_and_dividend_withholding(self):
        result = calculate_pj_presumido(PjScenario(D('600000'), months_billed=12, pro_labore=D('10000')))
        self.assertGreater(result.annual_business_taxes, D('0'))
        self.assertGreater(result.annual_dividend_withholding, D('0'))
        self.assertTrue(any('dividend' in warning.lower() for warning in result.warnings))

    def test_presumido_applies_2026_presumption_increase_with_distinct_csll_start(self):
        result = calculate_pj_presumido(PjScenario(D('500000'), months_billed=12, pro_labore=D('10000')))
        tax_lines = dict(result.tax_lines)
        self.assertEqual(tax_lines['IRPJ'], D('464000.00'))
        self.assertEqual(tax_lines['CSLL'], D('174960.00'))

    def test_dividend_withholding_is_strictly_above_monthly_threshold(self):
        rules = get_tax_rules()
        self.assertEqual(dividend_withholding(D('600000'), 12, rules), D('0.00'))
        self.assertEqual(dividend_withholding(D('600001'), 12, rules), D('60000.10'))
        self.assertEqual(dividend_withholding(D('600000'), 11, rules), D('60000.00'))

    def test_equivalent_pj_finds_monthly_invoice_for_annual_clt_value(self):
        clt = calculate_clt(CltScenario(D('5000')))
        equivalent = solve_equivalent_pj(clt, PjScenario(D('7000')))
        self.assertIsNotNone(equivalent.revenue_monthly)
        self.assertGreaterEqual(equivalent.achieved_annual_value, equivalent.target_annual_value)

    def test_equivalent_clt_finds_gross_salary_for_pj_net(self):
        pj = calculate_pj(PjScenario(D('10000'), company_age_months=1))
        equivalent = solve_equivalent_clt(pj, CltScenario(D('1')))
        clt = calculate_clt(CltScenario(equivalent.gross_monthly))
        self.assertGreater(equivalent.gross_monthly, D('0'))
        self.assertGreaterEqual(clt.annual_worker_value, pj.annual_net)

    def test_budget_preserves_same_assumptions_and_negative_remainder(self):
        result = build_budget(D('3000'), D('2500'), BudgetInput(D('2800'), D('500'), D('.1'), D('.1')))
        self.assertEqual(result['clt'].emergency, D('300.00'))
        self.assertEqual(result['pj'].remaining, D('-1300.00'))

    def test_budget_applies_suggested_percentages_and_custom_variables(self):
        budget = BudgetInput(
            emergency_percent=D('.10'), investments_percent=D('.20'), fixed_percent=D('.50'),
            custom_variables=(
                CustomBudgetVariable('Leisure', 'currency', D('250')),
                CustomBudgetVariable('Courses', 'percent', D('5')),
            ),
        )
        row = build_budget(D('5000'), D('5000'), budget)['clt']
        self.assertEqual(row.fixed_bills, D('2500.00'))
        self.assertEqual(row.fixed_percent_equivalent, D('50.00'))
        self.assertEqual(row.custom_expenses, D('500.00'))
        self.assertEqual(row.remaining, D('500.00'))

    def test_budget_converts_fixed_currency_amount_to_income_percentage(self):
        budget = BudgetInput(fixed_bills=D('1250'))
        row = build_budget(D('5000'), D('4000'), budget)['clt']
        self.assertEqual(row.fixed_bills, D('1250.00'))
        self.assertEqual(row.fixed_percent_equivalent, D('25.00'))


class SandboxViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sandbox', password='test')

    def test_page_requires_authentication(self):
        response = self.client.get(reverse('sandbox:clt_pj'))
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={reverse("sandbox:clt_pj")}')

    def test_get_starts_with_only_the_two_income_choices(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('sandbox:clt_pj'))
        self.assertContains(response, 'I know the gross salary')
        self.assertContains(response, 'I know the monthly invoice')
        self.assertNotContains(response, 'name="clt_gross"')
        self.assertNotContains(response, 'name="pj_revenue"')
        self.assertNotContains(response, 'Calculate scenario')
        self.assertNotContains(response, 'aria-pressed="true"')

    def test_select_reveals_only_the_chosen_path_and_contextual_plan(self):
        self.client.force_login(self.user)
        clt_response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'intent': 'select',
        })
        self.assertContains(clt_response, 'Enter your CLT income')
        self.assertContains(clt_response, 'name="clt_gross"')
        self.assertContains(clt_response, 'Set your monthly plan')
        self.assertContains(clt_response, 'Additional monthly variables')
        self.assertNotContains(clt_response, 'Employer tax profile')
        self.assertNotContains(clt_response, 'CLT income after payroll')

        pj_response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'pj', 'intent': 'select',
        })
        self.assertContains(pj_response, 'Enter your PJ income')
        self.assertContains(pj_response, 'name="pj_revenue"')
        self.assertNotContains(pj_response, 'PJ income after taxes and costs')

    def test_switch_preserves_plan_and_discards_previous_result(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:clt_pj'), {
            'current_scenario_type': 'clt', 'scenario_type': 'pj', 'intent': 'select',
            'fixed_cost_type': 'currency', 'fixed_cost_value': '1250',
            'emergency_percent': '11', 'investments_percent': '7',
            'variable_label': ['Leisure'], 'variable_type': ['currency'],
            'variable_value': ['250'], 'pj_regime': 'simples', 'pro_labore': '1621',
            'months_billed': '11', 'company_age_months': '1',
        })
        self.assertContains(response, 'value="1250"')
        self.assertContains(response, '<option value="currency" selected>R$</option>', html=True)
        self.assertContains(response, 'Leisure')
        self.assertContains(response, 'aria-pressed="true"', count=1)
        self.assertNotContains(response, 'CLT income after payroll')
        self.assertNotContains(response, 'CLT and PJ side by side')

    def test_post_renders_results_without_creating_sandbox_records(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'clt_gross': '5000', 'intent': 'calculate',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CLT income after payroll')
        self.assertContains(response, 'Net 13th salary')
        self.assertContains(response, 'Official rule sources')
        self.assertFalse(any(table.startswith('sandbox_') for table in connection.introspection.table_names()))

    def test_fragment_post_replaces_one_workspace_without_relying_on_htmx_headers(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('sandbox:clt_pj'),
            {'scenario_type': 'clt', 'clt_gross': '5000', 'intent': 'calculate', 'response_mode': 'fragment'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sandbox-workspace"', count=1)
        self.assertContains(response, 'CLT income after payroll')
        self.assertNotContains(response, '<html')
        self.assertNotContains(response, '<header')

    def test_clt_and_pj_can_be_calculated_independently(self):
        self.client.force_login(self.user)
        clt_response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'clt_gross': '6000', 'intent': 'calculate',
        })
        pj_response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'pj', 'pj_revenue': '10000', 'pj_regime': 'simples',
            'pro_labore': '3000', 'months_billed': '11', 'company_age_months': '1',
            'intent': 'calculate',
        })
        self.assertContains(clt_response, 'CLT income after payroll')
        self.assertNotContains(clt_response, 'Enter the monthly invoice.')
        self.assertContains(pj_response, 'PJ income after taxes and costs')
        self.assertNotContains(pj_response, 'Enter the gross monthly salary.')

    def test_comparison_works_from_either_known_income(self):
        self.client.force_login(self.user)
        clt_response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'clt_gross': '6000', 'intent': 'compare',
            'compare_pj_regime': 'simples', 'compare_pro_labore': '1621',
            'compare_months_billed': '11',
        })
        pj_response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'pj', 'pj_revenue': '10000', 'pj_regime': 'simples',
            'pro_labore': '3000', 'months_billed': '11', 'company_age_months': '1',
            'intent': 'compare', 'compare_employer_profile': 'general',
        })
        self.assertContains(clt_response, 'CLT and PJ side by side')
        self.assertContains(clt_response, 'Estimated PJ invoice required')
        self.assertContains(clt_response, 'See comparison with PJ')
        self.assertContains(pj_response, 'CLT and PJ side by side')
        self.assertContains(pj_response, 'Estimated gross CLT salary required')
        self.assertContains(pj_response, 'See comparison with CLT')
        self.assertContains(pj_response, 'CLT employer profile for comparison')

    def test_help_popovers_are_associated_with_fields_and_results(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'clt_gross': '5000', 'intent': 'calculate',
        })
        self.assertContains(response, 'aria-describedby="id_clt_gross-help"')
        self.assertContains(response, 'id="id_clt_gross-help"', count=1)
        self.assertContains(response, 'data-help-popover')
        self.assertContains(response, 'id="clt-ordinary-net-help"', count=1)
        self.assertContains(response, 'aria-controls="clt-ordinary-net-help"', count=1)

    def test_custom_variables_are_applied_without_persistence(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'clt_gross': '5000', 'intent': 'calculate',
            'fixed_cost_type': 'percent', 'fixed_cost_value': '50',
            'emergency_percent': '10', 'investments_percent': '20',
            'variable_label': ['Leisure', 'Courses'],
            'variable_type': ['currency', 'percent'],
            'variable_value': ['250', '5'],
        })
        self.assertContains(response, 'Leisure')
        self.assertContains(response, 'Courses')
        self.assertContains(response, '(50,00%)')
        self.assertFalse(any(table.startswith('sandbox_') for table in connection.introspection.table_names()))

    def test_fixed_cost_target_accepts_currency_and_displays_equivalent_percentage(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'clt_gross': '5000', 'intent': 'calculate',
            'fixed_cost_type': 'currency', 'fixed_cost_value': '1000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'R$ 1.000,00')
        self.assertEqual(response.context['result']['budget'].fixed_bills, D('1000.00'))
        self.assertEqual(response.context['result']['budget'].fixed_percent_equivalent, D('20.24'))
        self.assertContains(response, '(20,24%)')

    def test_fixed_cost_percentage_rejects_values_over_one_hundred(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:clt_pj'), {
            'scenario_type': 'clt', 'clt_gross': '5000', 'intent': 'calculate',
            'fixed_cost_type': 'percent', 'fixed_cost_value': '101',
        })
        self.assertContains(response, 'Enter a percentage from 0 to 100.')

    def test_page_uses_the_pt_br_catalog(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'pt-br'
        with override('pt-br'):
            response = self.client.get(reverse('sandbox:clt_pj'))
        self.assertContains(response, 'Sandbox CLT × PJ')
        self.assertContains(response, 'Sei o salário bruto')
        self.assertContains(response, 'Sei o faturamento mensal')
        self.assertNotContains(response, 'Calcular cenário')
