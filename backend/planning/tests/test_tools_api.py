from decimal import Decimal

from django.test import SimpleTestCase

from config.testing import ApiTestCase
from planning.tax_rules import rules_for
from planning.tools import irrf_tax, salary

D = Decimal
SALARY = "/api/plan/tools/salary"
GROWTH = "/api/plan/tools/growth"


class SalaryRuleTests(SimpleTestCase):
    def test_inss_uses_the_progressive_2026_bands_and_their_ceiling(self):
        self.assertEqual(salary(D("2902.84"), 2026)["month"]["inss"], D("236.94"))
        self.assertEqual(salary(D("10000.00"), 2026)["month"]["inss"], D("988.09"))

    def test_irrf_uses_the_2026_reduction_and_the_lower_base(self):
        rules = rules_for(2026)
        tax, _base, _method = irrf_tax(D("5000.00"), 0, D("0"), rules, deductible_inss=D("1000.00"))
        self.assertEqual(tax, D("0.00"))
        _tax, base, method = irrf_tax(D("8000"), 0, D("0"), rules, deductible_inss=D("200"))
        self.assertEqual((base, method), (D("7392.80"), "simplified"))
        _tax, base, method = irrf_tax(D("8000"), 10, D("0"), rules, deductible_inss=D("800"))
        self.assertEqual((base, method), (D("5304.10"), "legal"))

    def test_the_year_has_the_vacation_the_13th_salary_and_the_fgts(self):
        result = salary(D("5000.00"), 2026)
        self.assertEqual(
            result["annual_net"],
            result["month"]["net"] * 11 + result["vacation"]["net"] + result["thirteenth"]["net"],
        )
        self.assertGreater(result["vacation"]["net"], result["month"]["net"])
        self.assertEqual(result["annual_fgts"], D("5333.33"))

    def test_the_deductions_of_the_employee_lower_the_month_only(self):
        plain = salary(D("5000.00"), 2026)
        result = salary(D("5000.00"), 2026, transport=D("400.00"), health=D("150.00"))
        # Transport is paid up to 6% of the gross salary: 300.00.
        self.assertEqual(result["month"]["deductions"], D("450.00"))
        self.assertEqual(result["month"]["net"], plain["month"]["net"] - D("450.00"))
        self.assertEqual(result["thirteenth"], plain["thirteenth"])

    def test_a_year_without_a_table_uses_the_latest_one_and_says_so(self):
        result = salary(D("5000.00"), 2031)
        self.assertEqual((result["year"], result["assumed"]), (2026, True))
        self.assertFalse(salary(D("5000.00"), 2026)["assumed"])


class ToolsApiTests(ApiTestCase):
    def test_the_salary_calculator_answers_with_the_net_pay(self):
        response = self.post(SALARY, {"gross": "5000.00"})
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(result["month"]["gross"], "5000.00")
        self.assertEqual(result["month"]["irrf"], "0.00")
        self.assertEqual(
            Decimal(result["month"]["net"]),
            Decimal("5000.00") - Decimal(result["month"]["inss"]),
        )
        self.assertEqual(result["annual_fgts"], "5333.33")
        self.assert_errors(self.post(SALARY, {"gross": "0"}), 422, "gross")
        self.assert_errors(
            self.post(SALARY, {"gross": "5000", "dependents": -1}), 422, "dependents"
        )

    def test_growth_adds_the_yield_and_then_the_contribution(self):
        response = self.post(
            GROWTH,
            {
                "initial": "100",
                "contribution": "100",
                "rate": "1",
                "rate_period": "monthly",
                "months": 2,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual([row["balance"] for row in result["rows"]], ["201.00", "303.01"])
        self.assertEqual(
            (result["ending"], result["contributed"], result["total_yield"]),
            ("303.01", "300.00", "3.01"),
        )

    def test_an_annual_rate_compounds_to_the_year(self):
        response = self.post(
            GROWTH,
            {
                "initial": "1000",
                "contribution": "0",
                "rate": "12",
                "rate_period": "annual",
                "months": 12,
            },
        )
        result = response.json()
        self.assertLess(abs(Decimal(result["ending"]) - Decimal("1120")), Decimal("0.10"))
        self.assertLess(Decimal(result["monthly_rate"]), Decimal("1"))

    def test_growth_refuses_values_out_of_range(self):
        base = {
            "initial": "100",
            "contribution": "0",
            "rate": "1",
            "rate_period": "monthly",
            "months": 12,
        }
        self.assert_errors(self.post(GROWTH, {**base, "months": 601}), 400, "months")
        self.assert_errors(self.post(GROWTH, {**base, "rate": "-100"}), 400, "rate")
        self.assert_errors(self.post(GROWTH, {**base, "initial": "-1"}), 422, "initial")


class SessionTests(ApiTestCase):
    signed_in = False

    def test_the_calculators_need_a_session(self):
        self.assertEqual(self.post(SALARY, {"gross": "5000"}).status_code, 401)
        self.assertEqual(self.post(GROWTH, {"months": 1}).status_code, 401)
