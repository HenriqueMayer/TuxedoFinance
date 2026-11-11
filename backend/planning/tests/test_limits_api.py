import json
from datetime import date

from banking.models import BankAccount
from config.testing import ApiTestCase
from ledger.categories import Category
from planning.models import SpendingLimit
from reports.tests.test_api import ReportsApiTestCase

MONTH = "/api/plan/month"
LIMIT = "/api/plan/limit"


class PlanTestCase(ReportsApiTestCase):
    """Today is 2026-11-10: November has 21 days left, with today."""

    def plan(self, month=""):
        response = self.get(MONTH, month=month)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def set_limit(self, amount, month="2026-11-01", category=None):
        payload = {"month": month, "amount": amount, "category_id": category}
        response = self.put(LIMIT, payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def limit_of(self, month):
        return self.plan(month)["limit"]


class MonthLimitTests(PlanTestCase):
    def test_a_month_without_a_limit_reads_its_flows_only(self):
        self.record(amount="100.00")
        self.record(
            title="Salário",
            amount="5000.00",
            transaction_type="INCOME",
            category_id=self.salary.pk,
        )
        plan = self.plan()
        self.assertEqual(plan["month"], "2026-11-01")
        self.assertEqual(plan["currency"], "BRL")
        self.assertTrue(plan["is_current"])
        self.assertEqual((plan["income"], plan["expenses"]), ("5000.00", "100.00"))
        self.assertEqual((plan["limit"], plan["left"], plan["per_day"]), (None, None, None))
        self.assertEqual(plan["budgets"], [])

    def test_a_limit_gives_what_is_left_and_the_amount_for_each_day(self):
        self.record(amount="900.00")
        plan = self.set_limit("3000.00")
        self.assertEqual((plan["limit"], plan["left"]), ("3000.00", "2100.00"))
        # 2100 over the 21 days from today through the end of the month.
        self.assertEqual(plan["per_day"], "100.00")
        self.assertEqual(self.plan()["limit"], "3000.00")

    def test_an_exceeded_limit_is_negative_and_has_no_amount_for_each_day(self):
        self.record(amount="100.00")
        plan = self.set_limit("60.00")
        self.assertEqual((plan["left"], plan["per_day"]), ("-40.00", None))

    def test_another_month_has_no_amount_for_each_day(self):
        self.set_limit("3000.00", month="2026-10-01")
        october = self.plan("2026-10")
        self.assertFalse(october["is_current"])
        self.assertEqual((october["left"], october["per_day"]), ("3000.00", None))

    def test_a_limit_holds_from_its_month_on_and_keeps_the_months_before(self):
        self.set_limit("3000.00", month="2026-10-01")
        self.set_limit("2500.00", month="2026-12-01")
        self.assertEqual(self.limit_of("2026-09"), None)
        self.assertEqual(self.limit_of("2026-10"), "3000.00")
        self.assertEqual(self.limit_of("2026-11"), "3000.00")
        self.assertEqual(self.limit_of("2026-12"), "2500.00")
        self.assertEqual(self.limit_of("2027-06"), "2500.00")

    def test_a_change_replaces_the_values_of_later_months(self):
        self.set_limit("3000.00", month="2026-10-01")
        self.set_limit("2500.00", month="2026-12-01")
        self.set_limit("2000.00", month="2026-11-01")
        self.assertEqual(self.limit_of("2026-10"), "3000.00")
        self.assertEqual(self.limit_of("2026-12"), "2000.00")

    def test_the_same_value_again_adds_no_record(self):
        self.set_limit("3000.00", month="2026-10-01")
        self.set_limit("3000.00", month="2026-11-01")
        self.assertEqual(SpendingLimit.objects.count(), 1)

    def test_an_empty_amount_removes_the_limit_from_that_month_on(self):
        self.set_limit("3000.00", month="2026-10-01")
        plan = self.set_limit(None)
        self.assertEqual(plan["limit"], None)
        self.assertEqual(self.limit_of("2026-10"), "3000.00")
        self.assertEqual(self.limit_of("2026-12"), None)
        # Without an earlier limit, nothing is kept.
        SpendingLimit.objects.all().delete()
        self.set_limit(None)
        self.assertEqual(SpendingLimit.objects.count(), 0)

    def test_the_limit_counts_the_currency_of_totals_only(self):
        self.record(amount="100.00")
        dollars = BankAccount.objects.create(
            user=self.user, bank=self.account.bank, name="Dollars", currency="USD"
        )
        self.record(amount="40.00", instrument=f"account:{dollars.pk}")
        plan = self.set_limit("1000.00")
        self.assertEqual(plan["expenses"], "100.00")

    def test_a_wrong_amount_or_month_is_refused(self):
        for amount in ("0", "-5.00"):
            response = self.put(LIMIT, {"month": "2026-11-01", "amount": amount})
            self.assert_errors(response, 400, "amount")
        response = self.put(LIMIT, {"month": "2026-11-15", "amount": "10.00"})
        self.assert_errors(response, 400, "month")
        self.assertEqual(SpendingLimit.objects.count(), 0)

    def test_a_refusal_is_answered_in_the_language_of_the_request(self):
        response = self.client.put(
            LIMIT,
            data=json.dumps({"month": "2026-11-15", "amount": "10.00"}),
            content_type="application/json",
            headers={"X-CSRFToken": self.csrf(), "Accept-Language": "pt-BR"},
        )
        self.assertEqual(response.json()["errors"]["month"], ["Escolha o primeiro dia de um mês."])

    def test_home_reads_the_limit_of_the_month(self):
        self.record(amount="900.00")
        self.assertIsNone(self.get("/api/reports/home").json()["limit"])
        self.set_limit("3000.00")
        self.assertEqual(
            self.get("/api/reports/home").json()["limit"],
            {
                "currency": "BRL",
                "amount": "3000.00",
                "expenses": "900.00",
                "income": "0.00",
                "left": "2100.00",
                "per_day": "100.00",
            },
        )


class CategoryBudgetTests(PlanTestCase):
    def budgets(self, month=""):
        return self.plan(month)["budgets"]

    def test_a_budget_counts_the_category_and_its_subcategories(self):
        self.record(amount="100.00")  # Mercado, under Alimentação.
        self.record(title="Padaria", amount="20.00", category_id=self.food.pk)
        self.record(title="Cinema", amount="50.00", category_id=self.fun.pk)
        plan = self.set_limit("300.00", category=self.food.pk)
        self.assertEqual(
            plan["budgets"],
            [
                {
                    "category_id": self.food.pk,
                    "name": "Alimentação",
                    "limit": "300.00",
                    "spent": "120.00",
                    "left": "180.00",
                }
            ],
        )
        self.assertIsNone(plan["limit"])  # The limit of the month is another record.

    def test_a_budget_of_a_subcategory_counts_only_that_subcategory(self):
        self.record(amount="100.00")
        self.record(title="Padaria", amount="20.00", category_id=self.food.pk)
        self.set_limit("80.00", category=self.market.pk)
        (budget,) = self.budgets()
        self.assertEqual(
            (budget["name"], budget["spent"], budget["left"]), ("Mercado", "100.00", "-20.00")
        )

    def test_a_budget_holds_from_its_month_on_and_can_be_removed(self):
        self.set_limit("300.00", month="2026-10-01", category=self.food.pk)
        self.assertEqual(self.budgets("2026-09"), [])
        self.assertEqual(len(self.budgets("2026-12")), 1)
        self.set_limit(None, category=self.food.pk)
        self.assertEqual(len(self.budgets("2026-10")), 1)
        self.assertEqual(self.budgets(), [])

    def test_categories_without_a_budget_are_suggested_with_their_average(self):
        self.record(amount="100.00")
        self.record(title="Feira", amount="90.00", date="2026-10-05")
        self.record(title="Feira", amount="60.00", date="2026-08-05")
        self.record(title="Cinema", amount="50.00", category_id=self.fun.pk)
        suggestions = self.plan()["suggestions"]
        self.assertEqual(
            suggestions,
            [
                # The average of the three months before: (90 + 0 + 60) / 3.
                {
                    "category_id": self.food.pk,
                    "name": "Alimentação",
                    "spent": "100.00",
                    "average": "50.00",
                },
                {"category_id": self.fun.pk, "name": "Lazer", "spent": "50.00", "average": "0.00"},
            ],
        )
        self.set_limit("300.00", category=self.food.pk)
        self.assertEqual([row["name"] for row in self.plan()["suggestions"]], ["Lazer"])

    def test_an_income_category_or_a_category_of_another_owner_is_refused(self):
        response = self.put(
            LIMIT, {"month": "2026-11-01", "amount": "10.00", "category_id": self.salary.pk}
        )
        self.assert_errors(response, 400, "category_id")
        foreign = Category.objects.create(user=self.other, name="Alheia")
        response = self.put(
            LIMIT, {"month": "2026-11-01", "amount": "10.00", "category_id": foreign.pk}
        )
        self.assert_errors(response, 400, "category_id")
        self.assertEqual(SpendingLimit.objects.count(), 0)


class OwnerTests(PlanTestCase):
    def test_the_limits_of_another_owner_are_not_read(self):
        SpendingLimit.objects.create(user=self.other, start_month=date(2026, 1, 1), amount="10.00")
        self.assertIsNone(self.plan()["limit"])
        self.set_limit("3000.00")
        self.assertEqual(SpendingLimit.objects.filter(user=self.other).get().amount, 10)


class SessionTests(ApiTestCase):
    signed_in = False

    def test_the_plan_needs_a_session(self):
        self.assertEqual(self.get(MONTH).status_code, 401)
        self.assertEqual(self.put(LIMIT, {"amount": "10.00"}).status_code, 401)
