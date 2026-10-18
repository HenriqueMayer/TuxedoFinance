"""Calculations coverage for sandbox."""

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from sandbox.forms import variables_from_data
from sandbox.services import BudgetInput, CltScenario, CustomVariable, build_budget, calculate_clt, calculate_manual, irrf_tax
from sandbox.tax_rules import get_tax_rules


D = Decimal


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
