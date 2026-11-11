from datetime import date
from decimal import Decimal
from unittest.mock import patch

from banking.models import Bank, BankAccount, CreditCard
from banking.services import account_balance
from config.testing import ApiTestCase
from ledger.categories import Category
from ledger.models import Transaction


class ScheduleApiTestCase(ApiTestCase):
    """A rent that repeats from 5 September 2026 and asks for confirmation; today is 10 November."""

    def setUp(self):
        super().setUp()
        bank = Bank.objects.create(user=self.user, name="Nubank")
        self.account = BankAccount.objects.create(
            user=self.user,
            bank=bank,
            name="Conta",
            currency="BRL",
            opening_balance=Decimal("10000.00"),
        )
        self.card = CreditCard.objects.create(
            user=self.user, account=self.account, name="Platinum", closing_day=24, due_day=1
        )
        self.housing = Category.objects.create(
            user=self.user, name="Moradia", transaction_type="EXPENSE"
        )
        # Recorded in September, so confirmation starts with September.
        self.set_today(date(2026, 9, 1))
        self.rent = self.record(
            title="Aluguel",
            amount="1500.00",
            date="2026-09-05",
            is_fixed=True,
            requires_confirmation=True,
        )
        self.set_today(date(2026, 11, 10))
        self.path = f"/api/ledger/transactions/{self.rent['id']}/schedule"

    def set_today(self, value):
        for clock in getattr(self, "_clocks", []):
            clock.stop()
        clock = patch("django.utils.timezone.localdate", return_value=value)
        clock.start()
        self._clocks = [clock]
        self.addCleanup(clock.stop)

    def entry(self, **changes):
        return {
            "title": "Feira",
            "amount": "100.00",
            "category_id": self.housing.pk,
            "instrument": f"account:{self.account.pk}",
            **changes,
        }

    def record(self, **changes):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("/api/ledger/transactions", self.entry(**changes))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def act(self, month, action):
        with self.captureOnCommitCallbacks(execute=True):
            return self.post(f"{self.path}/{month}/{action}")

    def months(self, body=None):
        body = body or self.get(self.path).json()
        return {row["month"][:7]: row for row in body["months"]}


class RepeatingEntryTests(ScheduleApiTestCase):
    def test_a_repeating_entry_reports_its_settings(self):
        self.assertTrue(self.rent["is_fixed"])
        self.assertTrue(self.rent["requires_confirmation"])
        self.assertIsNone(self.rent["fixed_until"])

    def test_a_repeating_entry_appears_in_each_month_of_the_list(self):
        for month in ("2026-09", "2026-11", "2027-03"):
            with self.subTest(month=month):
                body = self.get("/api/ledger/transactions", month=month).json()
                self.assertEqual(
                    [(row["title"], row["month_amount"]) for row in body["items"]],
                    [("Aluguel", "1500.00")],
                )
        self.assertEqual(self.get("/api/ledger/transactions", month="2026-08").json()["count"], 0)

    def test_an_end_month_stops_the_repetition(self):
        self.record(
            title="Curso",
            amount="300.00",
            date="2026-11-10",
            is_fixed=True,
            fixed_until="2026-12-31",
        )

        def titles(month):
            rows = self.get("/api/ledger/transactions", month=month).json()["items"]
            return {row["title"] for row in rows}

        self.assertIn("Curso", titles("2026-12"))
        self.assertNotIn("Curso", titles("2027-01"))

    def test_confirmation_is_refused_for_a_card_and_for_an_entry_that_does_not_repeat(self):
        response = self.post(
            "/api/ledger/transactions",
            self.entry(
                is_fixed=True, requires_confirmation=True, instrument=f"credit:{self.card.pk}"
            ),
        )
        self.assert_errors(response, 400, "requires_confirmation")
        # Without repetition the setting has no meaning and is dropped, not refused.
        once = self.record(requires_confirmation=True)
        self.assertFalse(once["requires_confirmation"])

    def test_installments_and_repetition_exclude_each_other(self):
        response = self.post(
            "/api/ledger/transactions",
            self.entry(is_fixed=True, installments=3, instrument=f"credit:{self.card.pk}"),
        )
        self.assert_errors(response, 400, "installments")

    def test_the_amount_and_first_date_of_an_entry_with_past_months_do_not_change_here(self):
        path = f"/api/ledger/transactions/{self.rent['id']}"
        base = self.entry(
            title="Aluguel",
            amount="1500.00",
            date="2026-09-05",
            is_fixed=True,
            requires_confirmation=True,
        )
        self.assert_errors(self.put(path, {**base, "amount": "1600.00"}), 400, "amount")
        self.assert_errors(self.put(path, {**base, "date": "2026-09-06"}), 400, "date")
        # The title and the category can change.
        self.assertEqual(
            self.put(path, {**base, "title": "Aluguel do apartamento"}).status_code, 200
        )
        self.assertEqual(Transaction.objects.get(pk=self.rent["id"]).amount, Decimal("1500.00"))


class MonthlyScheduleTests(ScheduleApiTestCase):
    def test_months_that_passed_wait_for_confirmation_and_do_not_change_the_balance(self):
        months = self.months()
        self.assertEqual(list(months)[:4], ["2026-09", "2026-10", "2026-11", "2026-12"])
        self.assertEqual(
            [months[m]["status"] for m in ("2026-09", "2026-10", "2026-11", "2026-12")],
            ["EXPECTED"] * 4,
        )
        self.assertEqual(
            [months[m]["awaiting"] for m in ("2026-09", "2026-10", "2026-11", "2026-12")],
            [True, True, True, False],
        )
        # Nothing is confirmed: no money left the account.
        self.assertEqual(account_balance(self.account), Decimal("10000.00"))

    def test_confirming_a_month_records_it_and_debits_the_account(self):
        response = self.act("2026-09", "confirm")
        self.assertEqual(response.status_code, 200, response.content)
        month = self.months(response.json())["2026-09"]
        self.assertEqual(
            (month["status"], month["awaiting"], month["can_restore"]), ("CONFIRMED", False, True)
        )
        self.assertEqual(account_balance(self.account), Decimal("8500.00"))

    def test_skipping_a_month_removes_its_amount_and_restore_brings_it_back(self):
        self.assertEqual(
            self.months(self.act("2026-10", "skip").json())["2026-10"]["status"], "SKIPPED"
        )
        self.assertEqual(self.get("/api/ledger/transactions", month="2026-10").json()["count"], 0)
        self.assertEqual(
            self.months(self.act("2026-10", "restore").json())["2026-10"]["status"], "EXPECTED"
        )
        self.assertEqual(self.get("/api/ledger/transactions", month="2026-10").json()["count"], 1)

    def test_restore_without_a_change_and_a_month_outside_the_schedule_are_refused(self):
        self.assert_errors(self.act("2026-10", "restore"), 400, "month")
        self.assertEqual(self.act("2026-08", "confirm").status_code, 400)
        self.assertEqual(self.act("nonsense", "confirm").status_code, 404)

    def test_an_amount_change_applies_from_its_month_and_keeps_the_months_before(self):
        response = self.post(f"{self.path}-amounts", {"month": "2026-12", "amount": "1650.00"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["amount_changes"], [{"month": "2026-12-01", "amount": "1650.00"}])
        months = self.months(body)
        self.assertEqual(
            (months["2026-11"]["amount"], months["2026-12"]["amount"], months["2027-01"]["amount"]),
            ("1500.00", "1650.00", "1650.00"),
        )

        removed = self.delete(f"{self.path}-amounts/2026-12")
        self.assertEqual(removed.status_code, 200, removed.content)
        self.assertEqual(self.months(removed.json())["2026-12"]["amount"], "1500.00")

    def test_an_invalid_amount_change_is_refused(self):
        self.assert_errors(
            self.post(f"{self.path}-amounts", {"month": "nonsense", "amount": "10"}), 400, "month"
        )
        self.assert_errors(
            self.post(f"{self.path}-amounts", {"month": "2026-12", "amount": "0"}), 400, "amount"
        )
        # The first month has the amount of the entry itself.
        self.assert_errors(
            self.post(f"{self.path}-amounts", {"month": "2026-09", "amount": "10"}), 400, "month"
        )

    def test_an_entry_that_does_not_repeat_has_no_schedule(self):
        once = self.record()
        self.assertEqual(
            self.get(f"/api/ledger/transactions/{once['id']}/schedule").status_code, 404
        )

    def test_another_owner_cannot_read_or_change_a_schedule(self):
        self.client.force_login(self.other)
        self.assertEqual(self.get(self.path).status_code, 404)
        self.assertEqual(self.act("2026-09", "confirm").status_code, 404)
        self.assertEqual(
            self.post(f"{self.path}-amounts", {"month": "2026-12", "amount": "10"}).status_code, 404
        )
        self.assertEqual(self.delete(f"{self.path}-amounts/2026-12").status_code, 404)
