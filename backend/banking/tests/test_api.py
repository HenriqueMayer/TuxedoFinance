from decimal import Decimal

from banking.models import Bank, BankAccount, CreditCard
from config.testing import ApiTestCase

ACCOUNT = {"bank_name": "Nubank", "name": "Conta", "opening_balance": "1500.00"}


class AccountApiTests(ApiTestCase):
    def test_first_account_creates_its_bank(self):
        response = self.post("/api/banking/accounts", ACCOUNT)
        self.assertEqual(response.status_code, 200, response.content)
        account = BankAccount.objects.get(user=self.user)
        self.assertEqual(account.opening_balance, Decimal("1500.00"))
        self.assertEqual(account.currency, "BRL")
        self.assertEqual(
            response.json(),
            {
                "id": f"account:{account.pk}",
                "kind": "account",
                "name": "Conta",
                "bank_name": "Nubank",
                "account_name": "Conta",
                "currency": "BRL",
                "color": account.bank.color,
            },
        )

    def test_second_account_reuses_the_bank_whatever_the_letter_case(self):
        self.post("/api/banking/accounts", ACCOUNT)
        response = self.post(
            "/api/banking/accounts", {**ACCOUNT, "bank_name": " nubank ", "name": "Reserva"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Bank.objects.filter(user=self.user).count(), 1)

    def test_same_account_twice_is_refused_and_keeps_one(self):
        self.post("/api/banking/accounts", ACCOUNT)
        response = self.post("/api/banking/accounts", ACCOUNT)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(BankAccount.objects.filter(user=self.user).count(), 1)

    def test_a_refused_account_does_not_leave_a_new_bank(self):
        response = self.post("/api/banking/accounts", {**ACCOUNT, "name": ""})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Bank.objects.filter(user=self.user).exists())

    def test_another_owner_with_the_same_bank_name_gets_a_separate_bank(self):
        Bank.objects.create(user=self.other, name="Nubank")
        self.post("/api/banking/accounts", ACCOUNT)
        self.assertEqual(Bank.objects.filter(name="Nubank").count(), 2)

    def test_unsupported_currency_is_refused(self):
        self.assert_errors(
            self.post("/api/banking/accounts", {**ACCOUNT, "currency": "XXX"}), 422, "currency"
        )

    def test_accounts_need_a_session(self):
        self.client.logout()
        self.assertEqual(self.post("/api/banking/accounts", ACCOUNT).status_code, 401)


class CardApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.account = self.post("/api/banking/accounts", ACCOUNT).json()["id"]

    def card(self, **changes):
        return {
            "account": self.account,
            "name": "Platinum",
            "closing_day": 24,
            "due_day": 1,
            **changes,
        }

    def test_credit_card_is_created_on_the_owned_account(self):
        response = self.post("/api/banking/credit-cards", self.card())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["kind"], "credit")
        self.assertEqual(response.json()["bank_name"], "Nubank")
        self.assertEqual(CreditCard.objects.get(user=self.user).closing_day, 24)

    def test_credit_card_days_outside_the_month_are_refused(self):
        self.assert_errors(
            self.post("/api/banking/credit-cards", self.card(closing_day=0)), 400, "closing_day"
        )
        self.assert_errors(
            self.post("/api/banking/credit-cards", self.card(due_day=32)), 400, "due_day"
        )

    def test_card_on_another_owners_account_is_refused(self):
        bank = Bank.objects.create(user=self.other, name="Itaú")
        foreign = BankAccount.objects.create(
            user=self.other, bank=bank, name="Conta", currency="BRL"
        )
        response = self.post(
            "/api/banking/credit-cards", self.card(account=f"account:{foreign.pk}")
        )
        self.assert_errors(response, 400, "account")
        self.assertFalse(CreditCard.objects.exists())

    def test_card_needs_an_account_id_and_not_a_card_id(self):
        self.assert_errors(
            self.post("/api/banking/debit-cards", {"account": "credit:1", "name": "Débito"}),
            400,
            "account",
        )

    def test_debit_card_is_created(self):
        response = self.post(
            "/api/banking/debit-cards", {"account": self.account, "name": "Débito"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["kind"], "debit")


class InstrumentListTests(ApiTestCase):
    def test_list_has_accounts_then_debit_then_credit_and_only_the_owners(self):
        account = self.post("/api/banking/accounts", ACCOUNT).json()["id"]
        self.post(
            "/api/banking/credit-cards",
            {"account": account, "name": "Platinum", "closing_day": 24, "due_day": 1},
        )
        self.post("/api/banking/debit-cards", {"account": account, "name": "Débito"})
        bank = Bank.objects.create(user=self.other, name="Itaú")
        BankAccount.objects.create(user=self.other, bank=bank, name="Alheia", currency="BRL")

        response = self.get("/api/banking/instruments")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["kind"] for item in response.json()], ["account", "debit", "credit"])
        self.assertNotIn("Alheia", [item["name"] for item in response.json()])

    def test_list_needs_a_session(self):
        self.client.logout()
        self.assertEqual(self.get("/api/banking/instruments").status_code, 401)
