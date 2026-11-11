from reports.tests.test_api import ReportsApiTestCase

BASE = "/api/reports/items"


class ItemTestCase(ReportsApiTestCase):
    """Today is 2026-11-10. The analysis of one item covers the twelve months to this one."""

    def item(self, kind, pk):
        response = self.get(f"{BASE}/{kind}/{pk}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def invest(self, **changes):
        payload = {
            "name": "Reserva",
            "institution_id": self.account.bank_id,
            "currency": "BRL",
            "opening_balance": "2000.00",
            "opening_date": "2026-09-15",
            **changes,
        }
        response = self.post("/api/investments/positions", payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["id"]


class InvestmentItemTests(ItemTestCase):
    def setUp(self):
        super().setUp()
        self.reserva = self.invest()
        response = self.post(
            f"/api/investments/positions/{self.reserva}/operations",
            {"kind": "YIELD", "date": "2026-10-31", "amount": "15.00"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.tesouro = self.invest(
            name="Tesouro", opening_balance="5000.00", opening_date="2026-10-20"
        )

    def test_the_months_have_the_value_the_cost_and_what_moved(self):
        body = self.item("investment", self.reserva)
        self.assertEqual(
            (body["name"], body["institution_name"], body["currency"]), ("Reserva", "Nubank", "BRL")
        )
        months = body["months"]
        self.assertEqual(
            (len(months), months[0]["month"], months[-1]["month"]), (12, "2025-12-01", "2026-11-01")
        )
        rows = [
            (row["month"][:7], row["value"], row["deposits"], row["withdrawals"], row["yields"])
            for row in months[-4:]
        ]
        self.assertEqual(
            rows,
            [
                ("2026-08", "0.00", "0.00", "0.00", "0.00"),
                # The opening position counts as a deposit of its month.
                ("2026-09", "2000.00", "2000.00", "0.00", "0.00"),
                ("2026-10", "2015.00", "0.00", "0.00", "15.00"),
                ("2026-11", "2015.00", "0.00", "0.00", "0.00"),
            ],
        )

    def test_the_figures_of_today_and_the_totals_of_the_period(self):
        body = self.item("investment", self.reserva)
        self.assertEqual(
            (body["value"], body["deposits"], body["withdrawals"], body["yields"]),
            ("2015.00", "2000.00", "0.00", "15.00"),
        )
        # A balance has no unit price: it earns yields, and has no gain against a cost.
        self.assertIsNone(body["gain"])

    def test_the_share_compares_the_position_with_every_investment(self):
        share = self.item("investment", self.reserva)["share"]
        self.assertEqual(
            (share["value"], share["total"], share["percent"]), ("2015.00", "7015.00", "28.7")
        )
        self.assertEqual(
            [(row["name"], row["value"], row["share"], row["current"]) for row in share["items"]],
            [("Tesouro", "5000.00", "71.3", False), ("Reserva", "2015.00", "28.7", True)],
        )

    def test_the_item_is_the_owners_only_and_needs_a_session(self):
        self.client.force_login(self.other)
        self.assertEqual(self.get(f"{BASE}/investment/{self.reserva}").status_code, 404)
        self.client.logout()
        self.assertEqual(self.get(f"{BASE}/investment/{self.reserva}").status_code, 401)


class AccountItemTests(ItemTestCase):
    def setUp(self):
        super().setUp()
        self.record(
            title="Salário", amount="5000.00", transaction_type="INCOME", category_id=self.salary.pk
        )
        self.record(amount="120.50")
        self.record(title="Outubro", amount="40.00", date="2026-10-05")
        response = self.post(
            "/api/banking/accounts",
            {"bank_name": "Nubank", "name": "Reserva", "opening_balance": "3000.00"},
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_months_have_the_balance_and_what_entered_and_left(self):
        body = self.item("account", self.account.pk)
        self.assertEqual(
            (body["name"], body["bank_name"], body["currency"]), ("Conta", "Nubank", "BRL")
        )
        rows = [
            (row["month"][:7], row["balance"], row["inflow"], row["outflow"])
            for row in body["months"][-3:]
        ]
        self.assertEqual(
            rows,
            [
                ("2026-09", "1000.00", "0.00", "0.00"),
                ("2026-10", "960.00", "0.00", "40.00"),
                ("2026-11", "5839.50", "5000.00", "120.50"),
            ],
        )
        self.assertEqual(len(body["months"]), 12)

    def test_the_totals_and_the_change_of_the_period(self):
        body = self.item("account", self.account.pk)
        self.assertEqual(
            (body["balance"], body["change"], body["inflow"], body["outflow"]),
            ("5839.50", "4839.50", "5000.00", "160.50"),
        )

    def test_the_share_compares_the_account_with_every_account(self):
        share = self.item("account", self.account.pk)["share"]
        self.assertEqual(
            (share["value"], share["total"], share["percent"]), ("5839.50", "8839.50", "66.1")
        )
        self.assertEqual(
            [(row["name"], row["value"], row["current"]) for row in share["items"]],
            [("Conta", "5839.50", True), ("Reserva", "3000.00", False)],
        )

    def test_the_item_is_the_owners_only_and_needs_a_session(self):
        self.client.force_login(self.other)
        self.assertEqual(self.get(f"{BASE}/account/{self.account.pk}").status_code, 404)
        self.client.logout()
        self.assertEqual(self.get(f"{BASE}/account/{self.account.pk}").status_code, 401)


class CardItemTests(ItemTestCase):
    def setUp(self):
        super().setUp()
        card = f"credit:{self.card.pk}"
        self.record(title="Cinema", amount="60.00", category_id=self.fun.pk, instrument=card)
        self.record(title="Notebook", amount="900.00", instrument=card, installments=3)
        self.record(title="Jantar", amount="40.00", instrument=f"credit:{self.manual.pk}")

    def test_the_months_have_the_statement_of_each_month(self):
        body = self.item("card", self.card.pk)
        self.assertEqual(
            (body["name"], body["account_name"], body["currency"]), ("Platinum", "Conta", "BRL")
        )
        months = body["months"]
        self.assertEqual((len(months), months[-1]["month"]), (12, "2026-11-01"))
        # One installment of three counts in the month; the others are in later months.
        self.assertEqual([row["amount"] for row in months[-2:]], ["0.00", "360.00"])
        self.assertEqual((body["total"], body["average"]), ("360.00", "30.00"))

    def test_what_the_card_owes_counts_every_installment(self):
        self.assertEqual(self.item("card", self.card.pk)["owed"], "960.00")

    def test_the_categories_of_the_period_are_listed_by_amount(self):
        categories = self.item("card", self.card.pk)["categories"]
        self.assertEqual(
            [(row["name"], row["amount"], row["share"]) for row in categories],
            [("Alimentação", "300.00", "83.3"), ("Lazer", "60.00", "16.7")],
        )

    def test_the_share_compares_the_card_with_every_card(self):
        share = self.item("card", self.card.pk)["share"]
        self.assertEqual(
            (share["value"], share["total"], share["percent"]), ("360.00", "400.00", "90.0")
        )
        self.assertEqual(
            [(row["name"], row["value"], row["current"]) for row in share["items"]],
            [("Platinum", "360.00", True), ("Black", "40.00", False)],
        )

    def test_the_item_is_the_owners_only_and_needs_a_session(self):
        self.client.force_login(self.other)
        self.assertEqual(self.get(f"{BASE}/card/{self.card.pk}").status_code, 404)
        self.client.logout()
        self.assertEqual(self.get(f"{BASE}/card/{self.card.pk}").status_code, 401)
