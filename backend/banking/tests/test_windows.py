from ledger.tests.test_api import LedgerApiTestCase


class AccountWindowTests(LedgerApiTestCase):
    """Today is 2026-11-10."""

    def movements(self):
        return self.get(f"/api/banking/accounts/{self.account.pk}").json()["movements"]

    def test_the_latest_movements_end_today(self):
        # A repeating expense and a purchase in installments have dates after today.
        self.record(title="Aluguel", amount="500.00", date="2026-10-10", is_fixed=True)
        self.record(
            title="Notebook",
            amount="900.00",
            date="2026-10-05",
            instrument=f"credit:{self.card.pk}",
            installments=3,
        )
        rows = self.movements()
        self.assertEqual(
            [(row["date"], row["amount"]) for row in rows],
            [("2026-11-10", "500.00"), ("2026-11-01", "300.00"), ("2026-10-10", "500.00")],
        )

    def test_the_settlement_of_an_invoice_names_its_month_in_words(self):
        self.record(amount="80.00", date="2026-10-05", instrument=f"credit:{self.card.pk}")
        labels = [row["label"] for row in self.movements()]
        self.assertEqual(labels, ["Platinum invoice October 2026"])


class CardWindowTests(LedgerApiTestCase):
    def test_the_invoices_end_at_the_open_statement_and_the_later_ones_are_apart(self):
        self.record(
            title="Notebook",
            amount="900.00",
            date="2026-10-05",
            instrument=f"credit:{self.card.pk}",
            installments=4,
        )
        body = self.get(f"/api/banking/credit-cards/{self.card.pk}").json()
        # Today is before the closing day: the open statement is of November.
        self.assertEqual(
            [row["reference_month"] for row in body["invoices"]], ["2026-11-01", "2026-10-01"]
        )
        # The later statements come oldest first: the next one is the first.
        self.assertEqual(
            [row["reference_month"] for row in body["later_invoices"]],
            ["2026-12-01", "2027-01-01"],
        )
