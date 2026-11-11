from datetime import date
from decimal import Decimal

from banking.models import Bank, BankAccount, ExchangeRate
from config.testing import ApiTestCase

RATES = "/api/banking/exchange-rates"
TRANSFERS = "/api/banking/transfers"


class ExchangeTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        bank = Bank.objects.create(user=self.user, name="Wise")
        self.reais = BankAccount.objects.create(
            user=self.user,
            bank=bank,
            name="Reais",
            currency="BRL",
            opening_balance=Decimal("1000.00"),
        )
        self.dollars = BankAccount.objects.create(
            user=self.user,
            bank=bank,
            name="Dollars",
            currency="USD",
            opening_balance=Decimal("100.00"),
        )

    def rates(self):
        response = self.get(RATES)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def record(self, **changes):
        payload = {
            "from_currency": "USD",
            "rate": "5.25",
            "effective_date": "2026-11-01",
            **changes,
        }
        return self.post(RATES, payload)


class ExchangeRateApiTests(ExchangeTestCase):
    def test_a_rate_is_recorded_to_the_currency_of_totals(self):
        self.assertEqual(self.rates(), [])
        response = self.record()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.rates(),
            [
                {
                    "id": response.json()["id"],
                    "from_currency": "USD",
                    "to_currency": "BRL",
                    "rate": "5.25000000",
                    "effective_date": "2026-11-01",
                }
            ],
        )

    def test_the_date_is_today_when_omitted_and_rates_are_listed_newest_first(self):
        self.record()
        response = self.post(RATES, {"from_currency": "USD", "rate": "5.40"})
        self.assertEqual(response.status_code, 200, response.content)
        newest, oldest = self.rates()
        self.assertEqual((newest["rate"], oldest["rate"]), ("5.40000000", "5.25000000"))
        self.assertEqual(newest["effective_date"], date.today().isoformat())

    def test_the_same_pair_and_date_again_replaces_the_rate(self):
        self.record()
        self.assertEqual(self.record(rate="5.30").status_code, 200)
        (rate,) = self.rates()
        self.assertEqual(rate["rate"], "5.30000000")

    def test_a_rate_can_name_another_target_currency(self):
        self.record(from_currency="EUR", to_currency="USD", rate="1.08")
        (rate,) = self.rates()
        self.assertEqual((rate["from_currency"], rate["to_currency"]), ("EUR", "USD"))

    def test_wrong_values_are_refused(self):
        self.assert_errors(self.record(from_currency="BRL"), 400, "to_currency")
        self.assert_errors(self.record(rate="0"), 400, "rate")
        self.assert_errors(self.record(rate="-1"), 400, "rate")
        self.assert_errors(self.record(from_currency="XXX"), 422, "from_currency")
        self.assertEqual(ExchangeRate.objects.count(), 0)

    def test_a_rate_is_deleted(self):
        pk = self.record().json()["id"]
        self.assertEqual(self.delete(f"{RATES}/{pk}").status_code, 204)
        self.assertEqual(self.rates(), [])

    def test_the_rates_of_another_owner_are_out_of_reach(self):
        foreign = ExchangeRate.objects.create(
            user=self.other,
            from_currency="USD",
            to_currency="BRL",
            rate=Decimal("9"),
            effective_date=date(2026, 11, 1),
        )
        self.assertEqual(self.rates(), [])
        self.assertEqual(self.delete(f"{RATES}/{foreign.pk}").status_code, 404)
        self.assertEqual(self.record().status_code, 200)
        self.assertEqual(ExchangeRate.objects.get(pk=foreign.pk).rate, 9)


class CrossCurrencyTransferTests(ExchangeTestCase):
    def transfer(self, **changes):
        payload = {
            "source_account_id": self.reais.pk,
            "destination_account_id": self.dollars.pk,
            "amount": "525.00",
            **changes,
        }
        with self.captureOnCommitCallbacks(execute=True):
            return self.post(TRANSFERS, payload)

    def balances(self):
        wallet = self.get("/api/banking/wallet").json()
        return {
            account["name"]: account["balance"]
            for bank in wallet["banks"]
            for account in bank["accounts"]
        }

    def test_a_transfer_between_currencies_has_an_amount_for_each_account(self):
        response = self.transfer(destination_amount="100.00")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.balances(), {"Dollars": "200.00", "Reais": "475.00"})

    def test_a_transfer_between_currencies_needs_the_received_amount(self):
        self.assert_errors(self.transfer(), 400, "destination_amount")
        self.assertEqual(self.balances(), {"Dollars": "100.00", "Reais": "1000.00"})

    def test_a_transfer_in_one_currency_keeps_one_amount(self):
        other = BankAccount.objects.create(
            user=self.user, bank=self.reais.bank, name="Reserva", currency="BRL"
        )
        response = self.transfer(destination_account_id=other.pk, destination_amount="500.00")
        self.assert_errors(response, 400, "destination_amount")
        response = self.transfer(destination_account_id=other.pk)
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.balances()["Reserva"], "525.00")


class SessionTests(ApiTestCase):
    signed_in = False

    def test_exchange_rates_need_a_session(self):
        self.assertEqual(self.get(RATES).status_code, 401)
        self.assertEqual(self.post(RATES, {"from_currency": "USD", "rate": "5"}).status_code, 401)
        self.assertEqual(self.delete(f"{RATES}/1").status_code, 401)
