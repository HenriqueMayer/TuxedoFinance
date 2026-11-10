from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from banking.models import BankAccount, ExchangeRate
from config.testing import ApiTestCase
from investments.models import Asset
from planning.models import FinancialGoal, GoalAllocation
from reports.tests.test_api import ReportsApiTestCase

GOALS = "/api/plan/goals"


class GoalTestCase(ReportsApiTestCase):
    """Today is 2026-11-10. The account holds 1000.00."""

    def setUp(self):
        super().setUp()
        self.source = f"account:{self.account.pk}"

    def read(self):
        response = self.get(GOALS)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def goals(self):
        return self.read()["goals"]

    def goal(self, pk):
        return next(row for row in self.goals() if row["id"] == pk)

    def create(self, **changes):
        payload = {"name": "Viagem", "target_amount": "5000.00", **changes}
        response = self.post(GOALS, payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["id"]

    def reserve(self, pk, amount, source=None):
        return self.put(
            f"{GOALS}/{pk}/reservations", {"source": source or self.source, "amount": amount}
        )

    def reserved(self, pk, amount, source=None):
        response = self.reserve(pk, amount, source)
        self.assertEqual(response.status_code, 200, response.content)
        return self.goal(pk)

    def invest(self, **changes):
        payload = {
            "name": "Reserva",
            "institution_id": self.account.bank_id,
            "opening_balance": "2000.00",
            "opening_date": "2026-11-01",
            **changes,
        }
        response = self.post("/api/investments/positions", payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["id"]


class GoalTests(GoalTestCase):
    def test_a_new_goal_has_nothing_saved(self):
        pk = self.create()
        goal = self.goal(pk)
        self.assertEqual(
            {name: goal[name] for name in ("name", "target_amount", "currency", "target_date")},
            {"name": "Viagem", "target_amount": "5000.00", "currency": "BRL", "target_date": None},
        )
        self.assertEqual(
            (goal["saved"], goal["remaining"], goal["percent"]), ("0.00", "5000.00", 0)
        )
        self.assertEqual((goal["status"], goal["monthly_needed"]), ("open", None))
        self.assertEqual(goal["reservations"], [])
        self.assertTrue(goal["complete"])

    def test_a_reservation_of_an_account_balance_counts_as_saved(self):
        pk = self.create()
        goal = self.reserved(pk, "400.00")
        self.assertEqual(
            (goal["saved"], goal["remaining"], goal["percent"]), ("400.00", "4600.00", 8)
        )
        self.assertEqual(
            goal["reservations"],
            [
                {
                    "source": self.source,
                    "label": "Nubank · Conta",
                    "currency": "BRL",
                    "amount": "400.00",
                    "backed": "400.00",
                }
            ],
        )
        (source,) = self.read()["sources"]
        self.assertEqual(
            source,
            {
                "key": self.source,
                "label": "Nubank · Conta",
                "currency": "BRL",
                "balance": "1000.00",
                "free": "600.00",
            },
        )

    def test_a_second_amount_for_the_same_source_replaces_the_first(self):
        pk = self.create()
        self.reserved(pk, "400.00")
        goal = self.reserved(pk, "250.00")
        self.assertEqual(goal["saved"], "250.00")
        self.assertEqual(GoalAllocation.objects.count(), 1)

    def test_zero_removes_the_reservation(self):
        pk = self.create()
        self.reserved(pk, "400.00")
        goal = self.reserved(pk, "0")
        self.assertEqual((goal["saved"], goal["reservations"]), ("0.00", []))

    def test_goals_cannot_reserve_more_than_the_balance(self):
        first, second = self.create(), self.create(name="Carro")
        self.reserved(first, "400.00")
        self.assert_errors(self.reserve(second, "700.00"), 400, "amount")
        self.assert_errors(self.reserve(first, "1000.01"), 400, "amount")
        self.assertEqual(self.reserved(second, "600.00")["saved"], "600.00")
        self.assertEqual(self.read()["sources"][0]["free"], "0.00")

    def test_a_balance_that_falls_is_shared_between_its_goals(self):
        first, second = self.create(), self.create(name="Carro")
        self.reserved(first, "400.00")
        self.reserved(second, "600.00")
        self.record(amount="500.00")  # The account now holds 500.00.
        self.assertEqual(self.goal(first)["saved"], "200.00")
        self.assertEqual(self.goal(second)["saved"], "300.00")
        (reservation,) = self.goal(first)["reservations"]
        self.assertEqual((reservation["amount"], reservation["backed"]), ("400.00", "200.00"))

    def test_a_balance_investment_is_a_source_and_units_are_not(self):
        position = self.invest()
        self.invest(
            name="Ações",
            valuation_mode="UNITS",
            opening_balance="0",
            opening_quantity="2",
            opening_unit_price="100.00",
        )
        keys = [source["key"] for source in self.read()["sources"]]
        self.assertEqual(keys, [self.source, f"investment:{position}"])
        pk = self.create()
        goal = self.reserved(pk, "1500.00", f"investment:{position}")
        self.assertEqual(goal["saved"], "1500.00")
        self.assertEqual(goal["reservations"][0]["label"], "Nubank · Reserva")
        self.assert_errors(self.reserve(pk, "2000.01", f"investment:{position}"), 400, "amount")
        self.assertEqual(self.reserved(pk, "2000.00", f"investment:{position}")["percent"], 40)

    def test_a_target_date_gives_the_amount_for_each_month(self):
        pk = self.create(target_date="2027-04-30")
        goal = self.reserved(pk, "400.00")
        # 4600 over the six months from November through April, rounded up.
        self.assertEqual((goal["status"], goal["monthly_needed"]), ("dated", "766.67"))

    def test_a_goal_is_reached_or_overdue(self):
        reached = self.create(name="Curso", target_amount="300.00", target_date="2026-01-31")
        self.assertEqual(self.goal(reached)["status"], "overdue")
        goal = self.reserved(reached, "300.00")
        self.assertEqual(
            (goal["status"], goal["remaining"], goal["percent"]), ("reached", "0.00", 100)
        )
        self.assertIsNone(goal["monthly_needed"])

    def test_a_reservation_in_another_currency_needs_an_exchange_rate(self):
        dollars = BankAccount.objects.create(
            user=self.user,
            bank=self.account.bank,
            name="Dollars",
            currency="USD",
            opening_balance=Decimal("100.00"),
        )
        pk = self.create()
        goal = self.reserved(pk, "100.00", f"account:{dollars.pk}")
        self.assertEqual((goal["saved"], goal["complete"]), ("0.00", False))
        self.assertEqual(goal["missing_currencies"], ["USD"])
        ExchangeRate.objects.create(
            user=self.user,
            from_currency="USD",
            to_currency="BRL",
            rate=Decimal("5"),
            effective_date=date(2026, 11, 1),
        )
        goal = self.goal(pk)
        self.assertEqual((goal["saved"], goal["complete"]), ("500.00", True))

    def test_a_goal_changes_and_an_archived_goal_frees_its_balance(self):
        pk = self.create()
        self.reserved(pk, "400.00")
        response = self.put(
            f"{GOALS}/{pk}",
            {"name": "Japão", "target_amount": "8000.00", "target_date": "2027-10-31"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        goal = self.goal(pk)
        self.assertEqual(
            (goal["name"], goal["target_amount"], goal["percent"]), ("Japão", "8000.00", 5)
        )
        response = self.put(
            f"{GOALS}/{pk}", {"name": "Japão", "target_amount": "8000.00", "is_archived": True}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.goal(pk)["is_archived"])
        self.assertEqual(self.read()["sources"][0]["free"], "1000.00")
        self.assert_errors(self.reserve(pk, "10.00"), 400, "__all__")

    def test_a_deleted_goal_takes_its_reservations(self):
        pk = self.create()
        self.reserved(pk, "400.00")
        self.assertEqual(self.delete(f"{GOALS}/{pk}").status_code, 204)
        self.assertEqual(self.goals(), [])
        self.assertEqual(GoalAllocation.objects.count(), 0)

    def test_wrong_values_are_refused(self):
        self.assert_errors(self.post(GOALS, {"name": " ", "target_amount": "10.00"}), 400, "name")
        self.assert_errors(
            self.post(GOALS, {"name": "Viagem", "target_amount": "0"}), 400, "target_amount"
        )
        pk = self.create()
        self.assert_errors(self.reserve(pk, "-1.00"), 400, "amount")
        self.assert_errors(self.reserve(pk, "10.00", "account:999999"), 400, "source")
        self.assert_errors(self.reserve(pk, "10.00", "wallet"), 400, "source")
        self.assertEqual(FinancialGoal.objects.count(), 1)

    def test_home_lists_the_active_goals(self):
        pk = self.create(target_date="2027-04-30")
        self.reserved(pk, "400.00")
        archived = self.create(name="Antiga")
        self.put(
            f"{GOALS}/{archived}", {"name": "Antiga", "target_amount": "10.00", "is_archived": True}
        )
        self.assertEqual(
            self.get("/api/reports/home").json()["goals"],
            [
                {
                    "id": pk,
                    "name": "Viagem",
                    "currency": "BRL",
                    "target_amount": "5000.00",
                    "target_date": "2027-04-30",
                    "saved": "400.00",
                    "remaining": "4600.00",
                    "percent": 8,
                    "status": "dated",
                    "monthly_needed": "766.67",
                }
            ],
        )


class ReservedSourceTests(GoalTestCase):
    def test_a_reserved_investment_keeps_its_currency_and_its_kind(self):
        position = self.invest()
        pk = self.create()
        self.reserved(pk, "10.00", f"investment:{position}")
        self.put(
            f"{GOALS}/{pk}", {"name": "Viagem", "target_amount": "5000.00", "is_archived": True}
        )
        asset = Asset.objects.get(pk=position)
        asset.currency = "USD"
        with self.assertRaises(ValidationError) as result:
            asset.full_clean()
        self.assertIn("currency", result.exception.message_dict)
        asset.currency = "BRL"
        asset.valuation_mode = "UNITS"
        asset.opening_balance = Decimal("0")
        asset.opening_product = None
        with self.assertRaises(ValidationError) as result:
            asset.full_clean()
        self.assertIn("valuation_mode", result.exception.message_dict)

    def test_a_reserved_account_keeps_its_currency(self):
        pk = self.create()
        self.reserved(pk, "10.00")
        self.account.currency = "USD"
        with self.assertRaises(ValidationError):
            self.account.full_clean()

    def test_a_deleted_investment_takes_its_reservation(self):
        position = self.invest()
        pk = self.create()
        self.reserved(pk, "10.00", f"investment:{position}")
        response = self.delete(f"/api/investments/positions/{position}")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.goal(pk)["reservations"], [])


class OwnerTests(GoalTestCase):
    def test_the_goals_and_the_sources_of_another_owner_are_out_of_reach(self):
        foreign = FinancialGoal.objects.create(
            user=self.other, name="Alheia", target_amount=Decimal("10.00")
        )
        self.assertEqual(self.goals(), [])
        self.assertEqual(
            self.put(f"{GOALS}/{foreign.pk}", {"name": "x", "target_amount": "1"}).status_code, 404
        )
        self.assertEqual(self.delete(f"{GOALS}/{foreign.pk}").status_code, 404)
        self.assertEqual(self.reserve(foreign.pk, "1.00").status_code, 404)
        bank = self.account.bank.__class__.objects.create(user=self.other, name="Outro")
        account = BankAccount.objects.create(
            user=self.other, bank=bank, name="Conta", currency="BRL", opening_balance=Decimal("50")
        )
        pk = self.create()
        self.assert_errors(self.reserve(pk, "10.00", f"account:{account.pk}"), 400, "source")


class SessionTests(ApiTestCase):
    signed_in = False

    def test_goals_need_a_session(self):
        self.assertEqual(self.get(GOALS).status_code, 401)
        self.assertEqual(self.post(GOALS, {"name": "x", "target_amount": "1"}).status_code, 401)
        self.assertEqual(
            self.put(f"{GOALS}/1", {"name": "x", "target_amount": "1"}).status_code, 401
        )
        self.assertEqual(self.delete(f"{GOALS}/1").status_code, 401)
        self.assertEqual(
            self.put(f"{GOALS}/1/reservations", {"source": "account:1", "amount": "1"}).status_code,
            401,
        )
