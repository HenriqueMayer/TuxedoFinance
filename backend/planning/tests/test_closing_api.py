from datetime import date
from decimal import Decimal

from config.testing import ApiTestCase
from planning.models import MonthClosing
from reports.tests.test_api import ReportsApiTestCase

CLOSING = "/api/plan/closing"
OCTOBER = "2026-10-01"


class ClosingTestCase(ReportsApiTestCase):
    """Today is 2026-11-10. The account holds 1000.00. October is the month to close."""

    def setUp(self):
        super().setUp()
        self.record(
            title="Salário",
            amount="3000.00",
            transaction_type="INCOME",
            category_id=self.salary.pk,
            date="2026-10-03",
        )
        self.record(amount="100.00", date="2026-10-05")

    def review(self, month=""):
        response = self.get(CLOSING, month=month)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def account_row(self, review=None):
        (row,) = (review or self.review())["accounts"]
        return row

    def check(self, balance, **changes):
        payload = {"month": OCTOBER, "account_id": self.account.pk, "balance": balance, **changes}
        return self.put(f"{CLOSING}/balances", payload)

    def checked(self, balance):
        response = self.check(balance)
        self.assertEqual(response.status_code, 200, response.content)
        return self.account_row(response.json())

    def adjust(self, difference):
        payload = {"month": OCTOBER, "account_id": self.account.pk, "difference": difference}
        with self.captureOnCommitCallbacks(execute=True):
            return self.post(f"{CLOSING}/adjustments", payload)

    def close(self, **changes):
        return self.post(CLOSING, {"month": OCTOBER, **changes})


class ReviewTests(ClosingTestCase):
    def test_the_month_before_is_reviewed_with_its_result_and_its_balances(self):
        review = self.review()
        self.assertEqual((review["month"], review["currency"]), (OCTOBER, "BRL"))
        self.assertEqual((review["is_closed"], review["changed_since"]), (False, False))
        self.assertEqual(
            review["result"],
            {
                "income": "3000.00",
                "expenses": "100.00",
                "result": "2900.00",
                "limit": None,
                "left": None,
            },
        )
        self.assertEqual(
            review["worth"], {"net_worth": "3900.00", "change": "2900.00", "complete": True}
        )
        self.assertEqual([row["name"] for row in review["spending"]], ["Alimentação"])
        self.assertEqual(
            self.account_row(review),
            {
                "account_id": self.account.pk,
                "name": "Nubank · Conta",
                "currency": "BRL",
                "date": "2026-10-31",
                "tracked": "3900.00",
                "statement": None,
                "difference": None,
                "adjusted": False,
            },
        )
        self.assertEqual(review["open_items"], [])
        self.assertEqual(review["next_limit"], {"month": "2026-11-01", "amount": None})

    def test_the_current_month_is_checked_on_today(self):
        review = self.review("2026-11")
        self.assertEqual(review["month"], "2026-11-01")
        self.assertEqual(self.account_row(review)["date"], "2026-11-10")
        self.assertEqual(review["next_limit"]["month"], "2026-12-01")

    def test_a_later_month_is_not_reviewed(self):
        self.assert_errors(self.get(CLOSING, month="2026-12"), 400, "month")

    def test_what_the_month_left_open_is_listed(self):
        # The invoice of September waits for a payment since 2026-10-05.
        self.record(amount="200.00", date="2026-09-20", instrument=f"credit:{self.manual.pk}")
        (item,) = self.review()["open_items"]
        self.assertEqual(
            (item["kind"], item["title"], item["due_date"], item["amount"], item["status"]),
            ("invoice", "Black", "2026-10-05", "200.00", "OVERDUE"),
        )


class BalanceTests(ClosingTestCase):
    def test_a_typed_balance_shows_its_difference(self):
        row = self.checked("3880.00")
        self.assertEqual(
            (row["statement"], row["difference"], row["adjusted"]), ("3880.00", "-20.00", False)
        )
        row = self.checked("3900.00")
        self.assertEqual((row["statement"], row["difference"]), ("3900.00", "0.00"))

    def test_an_empty_balance_removes_the_check(self):
        self.checked("3880.00")
        row = self.checked(None)
        self.assertEqual((row["statement"], row["difference"]), (None, None))

    def test_an_adjustment_makes_the_balances_equal_and_can_be_removed(self):
        self.checked("3880.00")
        response = self.adjust("-20.00")
        self.assertEqual(response.status_code, 200, response.content)
        row = self.account_row(response.json())
        self.assertEqual(
            (row["tracked"], row["difference"], row["adjusted"]), ("3880.00", "0.00", True)
        )
        wallet = self.get("/api/banking/wallet").json()
        self.assertEqual(wallet["banks"][0]["accounts"][0]["balance"], "3880.00")
        # The adjustment is not an expense of the month.
        self.assertEqual(self.review()["result"]["expenses"], "100.00")

        payload = {"month": OCTOBER, "account_id": self.account.pk}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.send("delete", f"{CLOSING}/adjustments", payload)
        self.assertEqual(response.status_code, 200, response.content)
        row = self.account_row(response.json())
        self.assertEqual((row["difference"], row["adjusted"]), ("-20.00", False))

    def test_an_adjustment_needs_the_difference_that_the_owner_saw(self):
        self.assert_errors(self.adjust("-20.00"), 400, "difference")  # No balance was typed.
        self.checked("3880.00")
        self.assert_errors(self.adjust("-25.00"), 400, "difference")
        self.checked("3900.00")
        self.assert_errors(self.adjust("0.00"), 400, "difference")
        self.assertEqual(self.account_row()["adjusted"], False)

    def test_an_account_of_another_owner_is_refused(self):
        from banking.models import Bank, BankAccount

        bank = Bank.objects.create(user=self.other, name="Outro")
        foreign = BankAccount.objects.create(
            user=self.other, bank=bank, name="Conta", currency="BRL"
        )
        self.assert_errors(self.check("10.00", account_id=foreign.pk), 400, "account_id")


class CloseTests(ClosingTestCase):
    def test_closing_records_the_month_and_sets_the_next_limit(self):
        response = self.close(next_limit="2500.00")
        self.assertEqual(response.status_code, 200, response.content)
        review = response.json()
        self.assertTrue(review["is_closed"])
        self.assertEqual(review["closed_on"], "2026-11-10")
        self.assertEqual(review["next_limit"], {"month": "2026-11-01", "amount": "2500.00"})
        self.assertIsNone(review["result"]["limit"])  # October keeps its own value.
        self.assertEqual(self.get("/api/plan/month").json()["limit"], "2500.00")
        closing = MonthClosing.objects.get(user=self.user)
        self.assertEqual((closing.month, closing.expenses), (date(2026, 10, 1), Decimal("100.00")))

    def test_closing_without_a_limit_keeps_the_limit(self):
        self.put("/api/plan/limit", {"month": "2026-09-01", "amount": "4000.00"})
        self.assertEqual(self.close().status_code, 200)
        self.assertEqual(self.get("/api/plan/month").json()["limit"], "4000.00")
        self.assertEqual(self.close().status_code, 200)  # A second closing changes nothing.
        self.assertEqual(MonthClosing.objects.count(), 1)

    def test_a_closed_month_says_when_its_entries_changed_later(self):
        self.close()
        self.assertFalse(self.review("2026-10")["changed_since"])
        self.record(title="Esquecido", amount="40.00", date="2026-10-20")
        review = self.review("2026-10")
        self.assertEqual((review["is_closed"], review["changed_since"]), (True, True))
        # Closing again accepts the month as it is now.
        self.close()
        self.assertFalse(self.review("2026-10")["changed_since"])

    def test_a_month_is_reopened(self):
        self.close()
        response = self.send("delete", CLOSING, {"month": OCTOBER})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["is_closed"])
        self.assertEqual(MonthClosing.objects.count(), 0)

    def test_wrong_values_are_refused(self):
        self.assert_errors(self.close(month="2026-12-01"), 400, "month")
        self.assert_errors(self.close(month="2026-10-15"), 400, "month")
        self.assert_errors(self.close(next_limit="-5"), 400, "next_limit")
        self.assertEqual(MonthClosing.objects.count(), 0)

    def test_home_asks_for_the_closing_of_the_month_before_until_it_is_done(self):
        home = "/api/reports/home"
        self.assertEqual(self.get(home).json()["closing"], {"month": OCTOBER, "changed": False})
        self.close()
        self.assertIsNone(self.get(home).json()["closing"])
        # After it, the review opens on the current month.
        self.assertEqual(self.review()["month"], "2026-11-01")
        # A later entry in the closed month brings the question back.
        self.record(title="Esquecido", amount="40.00", date="2026-10-20")
        self.assertEqual(self.get(home).json()["closing"], {"month": OCTOBER, "changed": True})
        self.assertEqual(self.review()["month"], OCTOBER)
        self.close()
        self.assertIsNone(self.get(home).json()["closing"])


class NewOwnerTests(ReportsApiTestCase):
    def test_an_owner_without_earlier_entries_is_not_asked(self):
        self.record(amount="10.00")
        self.assertIsNone(self.get("/api/reports/home").json()["closing"])


class OwnerTests(ClosingTestCase):
    def test_the_closings_of_another_owner_are_separate(self):
        self.close()
        self.client.force_login(self.other)
        review = self.review("2026-10")
        self.assertEqual((review["is_closed"], review["accounts"]), (False, []))
        self.assertEqual(review["result"]["income"], "0.00")


class SessionTests(ApiTestCase):
    signed_in = False

    def test_the_closing_needs_a_session(self):
        self.assertEqual(self.get(CLOSING).status_code, 401)
        self.assertEqual(self.post(CLOSING, {"month": OCTOBER}).status_code, 401)
        self.assertEqual(self.send("delete", CLOSING, {"month": OCTOBER}).status_code, 401)
        self.assertEqual(self.put(f"{CLOSING}/balances", {}).status_code, 401)
        self.assertEqual(self.post(f"{CLOSING}/adjustments", {}).status_code, 401)
        self.assertEqual(self.send("delete", f"{CLOSING}/adjustments", {}).status_code, 401)
