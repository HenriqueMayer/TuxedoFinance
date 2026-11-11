import uuid
from datetime import date
from decimal import Decimal

from banking.models import BankAccount, CardInvoice, ExchangeRate
from ledger.services import sync_user_ledger
from reports.tests.test_api import TODAY, ReportsApiTestCase

URL = "/api/reports/net-worth"


class WorthTestCase(ReportsApiTestCase):
    def worth(self):
        response = self.get(URL)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def today(self):
        return self.worth()["today"]

    def parts(self):
        today = self.today()
        return tuple(today[name] for name in ("accounts", "investments", "card_debt", "net_worth"))

    def invest(self, **changes):
        payload = {
            "name": "Reserva",
            "institution_id": self.account.bank_id,
            "currency": "BRL",
            **changes,
        }
        response = self.post("/api/investments/positions", payload)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["id"]


class NetWorthTests(WorthTestCase):
    def test_accounts_alone_are_the_net_worth(self):
        self.assertEqual(self.parts(), ("1000.00", "0.00", "0.00", "1000.00"))
        self.assertEqual(self.today()["currency"], "BRL")
        self.assertTrue(self.today()["complete"])

    def test_an_expense_from_the_account_lowers_it_and_a_transfer_does_not(self):
        self.record(amount="100.00")
        other = BankAccount.objects.create(
            user=self.user, bank=self.account.bank, name="Reserva", currency="BRL"
        )
        response = self.post(
            "/api/banking/transfers",
            {
                "source_account_id": self.account.pk,
                "destination_account_id": other.pk,
                "amount": "200.00",
            },
        )
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.parts(), ("900.00", "0.00", "0.00", "900.00"))

    def test_an_installment_plan_is_debt_for_its_full_amount_at_once(self):
        self.record(amount="300.00", installments=3, instrument=f"credit:{self.manual.pk}")
        self.assertEqual(self.parts(), ("1000.00", "0.00", "300.00", "700.00"))

    def test_a_confirmed_payment_moves_money_from_the_account_to_the_debt(self):
        self.record(amount="300.00", installments=3, instrument=f"credit:{self.manual.pk}")
        invoice = CardInvoice.objects.filter(card=self.manual).order_by("reference_month").first()
        response = self.post(
            f"/api/banking/invoices/{invoice.pk}/payments",
            {
                "account_id": self.account.pk,
                "amount": "40.00",
                "confirmation_key": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.parts(), ("960.00", "0.00", "260.00", "700.00"))

    def test_a_repeating_card_expense_is_debt_only_from_the_date_of_each_month(self):
        self.record(
            amount="50.00", is_fixed=True, date="2026-10-20", instrument=f"credit:{self.manual.pk}"
        )
        # October and no more: the November occurrence is on the 20th.
        self.assertEqual(self.parts(), ("1000.00", "0.00", "50.00", "950.00"))

    def test_a_card_that_settles_on_the_due_date_is_debt_until_that_date(self):
        self.record(amount="120.00", instrument=f"credit:{self.card.pk}")
        self.assertEqual(self.parts(), ("1000.00", "0.00", "120.00", "880.00"))
        self.set_today(date(2026, 12, 2))
        sync_user_ledger(self.user)
        self.assertEqual(self.parts(), ("880.00", "0.00", "0.00", "880.00"))

    def test_an_investment_counts_and_a_deposit_only_moves_money(self):
        position = self.invest(opening_balance="500.00")
        self.assertEqual(self.parts(), ("1000.00", "500.00", "0.00", "1500.00"))
        response = self.post(
            f"/api/investments/positions/{position}/operations",
            {"kind": "DEPOSIT", "account_id": self.account.pk, "amount": "300.00"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.parts(), ("700.00", "800.00", "0.00", "1500.00"))

    def test_a_new_value_of_an_investment_changes_the_net_worth(self):
        position = self.invest(opening_balance="500.00")
        response = self.post(f"/api/investments/positions/{position}/value", {"value": "530.00"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.parts(), ("1000.00", "530.00", "0.00", "1530.00"))

    def test_another_currency_is_converted_or_named_as_missing(self):
        dollars = BankAccount.objects.create(
            user=self.user,
            bank=self.account.bank,
            name="Dollars",
            currency="USD",
            opening_balance=Decimal("100.00"),
        )
        today = self.today()
        self.assertEqual((today["net_worth"], today["complete"]), ("1000.00", False))
        self.assertEqual(today["missing_currencies"], ["USD"])
        ExchangeRate.objects.create(
            user=self.user,
            from_currency="USD",
            to_currency="BRL",
            rate=Decimal("5"),
            effective_date=date(2026, 11, 1),
        )
        today = self.today()
        self.assertEqual((today["accounts"], today["complete"]), ("1500.00", True))
        self.assertEqual(dollars.currency, "USD")


class SeriesTests(WorthTestCase):
    def test_twelve_month_ends_and_the_last_one_is_today(self):
        self.account.opening_date = date(2026, 9, 15)
        self.account.save()
        self.record(amount="100.00", date="2026-10-05")
        self.invest(opening_balance="500.00", opening_date="2026-11-03")
        months = self.worth()["months"]
        self.assertEqual(len(months), 12)
        self.assertEqual(
            [row["month"] for row in months][-3:], ["2026-09-01", "2026-10-01", "2026-11-01"]
        )
        self.assertEqual(months[0]["month"], "2025-12-01")
        self.assertEqual(
            [row["net_worth"] for row in months][-4:], ["0.00", "1000.00", "900.00", "1400.00"]
        )
        self.assertEqual(months[-1]["net_worth"], self.today()["net_worth"])


class HomeWorthTests(WorthTestCase):
    def test_home_has_the_net_worth_and_the_end_of_the_month_before(self):
        self.account.opening_date = date(2026, 9, 15)
        self.account.save()
        self.record(amount="100.00", date="2026-11-05")
        worth = self.get("/api/reports/home").json()["worth"]
        self.assertEqual(
            (worth["currency"], worth["net_worth"], worth["previous"], worth["change"]),
            ("BRL", "900.00", "1000.00", "-100.00"),
        )


class AccessTests(WorthTestCase):
    def test_the_read_is_the_owners_only(self):
        self.invest(opening_balance="500.00")
        self.client.force_login(self.other)
        self.assertEqual(self.parts(), ("0.00", "0.00", "0.00", "0.00"))

    def test_the_read_needs_a_session(self):
        self.client.logout()
        self.assertEqual(self.get(URL).status_code, 401)
        self.assertEqual(TODAY, date(2026, 11, 10))
