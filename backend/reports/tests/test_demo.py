from datetime import date

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from reports import demo


class DemoExportTests(TransactionTestCase):
    """The export commits as the API does, so the derived rows exist when it reads."""

    def test_the_export_holds_the_answers_of_every_screen(self):
        data = demo.export("pt-BR")
        answers = data["answers"]
        self.assertEqual(data["language"], "pt-BR")
        self.assertEqual(data["today"][8:], "18")
        self.assertEqual(
            answers["GET /api/plan/closing?month=" + data["today"][:7]]["accounts"][0]["date"],
            data["today"],
        )
        month = data["today"][:7]
        for key in (
            "GET /api/session",
            "GET /api/reports/home",
            "GET /api/reports/net-worth",
            "GET /api/banking/wallet",
            "GET /api/plan/month",
            "GET /api/plan/goals",
            "GET /api/plan/forecast",
            "GET /api/plan/closing",
            "GET /api/ledger/transactions",
            f"GET /api/ledger/transactions?month={month}",
            f"GET /api/reports/month?month={month}",
        ):
            self.assertIn(key, answers)
        self.assertEqual(answers["GET /api/session"]["user"]["username"], "demo")
        # The sheet without changes for both periods, and the saved sheet with its changes.
        self.assertEqual([sheet["months"] for sheet in data["sheets"]], [6, 12, 6])
        self.assertEqual(len(data["sheets"][1]["answer"]["totals"]), 12)
        self.assertTrue(data["sheets"][2]["changes"]["manual"])
        home = answers["GET /api/reports/home"]
        self.assertEqual(home["limit"]["amount"], "6000.00")
        self.assertGreater(float(home["limit"]["left"]), 0)
        self.assertEqual(
            sorted(goal["name"] for goal in home["goals"]),
            ["Reserva de emergência", "Viagem ao Japão"],
        )
        self.assertIsNotNone(home["closing"])  # The month before waits for its closing.
        names = [row["name"] for row in answers["GET /api/ledger/categories"]]
        self.assertIn("Mercado", names)
        self.assertNotIn("Groceries", names)
        # Every listed entry has its own answer, for its window.
        listed = answers[f"GET /api/ledger/transactions?month={month}"]["items"]
        self.assertTrue(listed)
        for item in listed:
            self.assertIn(f"GET /api/ledger/transactions/{item['id']}", answers)
        # Amounts travel with two decimals, whatever the database returns for a sum.
        for bank in answers["GET /api/banking/wallet"]["banks"]:
            for account in bank["accounts"]:
                self.assertRegex(account["balance"], r"^-?\d+\.\d{2}$")
        worth = answers["GET /api/reports/net-worth"]["today"]
        self.assertTrue(worth["complete"])
        # The analysis has an answer for every period that its controls can reach.
        default = answers["GET /api/reports/analysis"]
        self.assertEqual(default["end"][:7], month)
        self.assertTrue(default["flows"][0]["categories"])
        self.assertTrue(default["positions"])
        self.assertTrue(default["worth"]["complete"])
        first, year = default["first"][:7], f"{month[:4]}-01"
        for start, end in ((month, month), (first, month), (year, month), (first, first)):
            self.assertIn(f"GET /api/reports/analysis?end={end}&start={start}", answers)
        # Each item of the Wallet has its analysis.
        accounts = answers["GET /api/banking/wallet"]["banks"][0]["accounts"]
        account = answers[f"GET /api/reports/items/account/{accounts[0]['id']}"]
        self.assertEqual(len(account["months"]), 12)
        card = accounts[0]["credit_cards"][0]
        self.assertTrue(answers[f"GET /api/reports/items/card/{card['id']}"]["categories"])
        position = answers["GET /api/investments/positions"]["positions"][0]
        share = answers[f"GET /api/reports/items/investment/{position['id']}"]["share"]
        self.assertGreater(len(share["items"]), 1)
        # A click on a month of a chart has its answer too.
        origin = answers[f"GET /api/reports/analysis/month?month={month}"]
        self.assertTrue(origin["entries"])
        self.assertTrue(origin["worth"]["accounts"])
        self.assertIn(f"GET /api/reports/analysis/month?month={first}", answers)

    def test_the_demonstration_day_is_the_latest_18th(self):
        self.assertEqual(demo.demonstration_day(date(2026, 11, 18)), date(2026, 11, 18))
        self.assertEqual(demo.demonstration_day(date(2026, 11, 30)), date(2026, 11, 18))
        self.assertEqual(demo.demonstration_day(date(2026, 11, 10)), date(2026, 10, 18))
        self.assertEqual(demo.demonstration_day(date(2027, 1, 1)), date(2026, 12, 18))

    def test_the_export_refuses_a_database_with_a_user(self):
        get_user_model().objects.create_user("someone")
        with self.assertRaisesMessage(RuntimeError, "already has a user"):
            demo.export("en")
        self.assertEqual(get_user_model().objects.count(), 1)
