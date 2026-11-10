import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from banking.models import Bank, BankAccount, BankTransfer, CardInvoice, CreditCard, InvoicePayment
from banking.services import account_balance
from config.testing import ApiTestCase
from ledger.categories import Category

TODAY = date(2026, 11, 10)


class WalletApiTestCase(ApiTestCase):
    """One owner with two accounts and a card that confirms payments; today is fixed."""

    def setUp(self):
        super().setUp()
        clock = patch("django.utils.timezone.localdate", return_value=TODAY)
        clock.start()
        self.addCleanup(clock.stop)
        self.account = self.create_account(name="Conta", opening_balance="1000.00")
        self.savings = self.create_account(name="Reserva", opening_balance="500.00")
        self.card = (
            self.post(
                "/api/banking/credit-cards",
                {
                    "account": f"account:{self.account.pk}",
                    "name": "Platinum",
                    "closing_day": 24,
                    "due_day": 1,
                    "confirm_payments": True,
                },
            )
            .json()["id"]
            .split(":")[1]
        )
        self.food = Category.objects.create(
            user=self.user, name="Mercado", transaction_type="EXPENSE"
        )

    def create_account(self, **values):
        response = self.post("/api/banking/accounts", {"bank_name": "Nubank", **values})
        self.assertEqual(response.status_code, 200, response.content)
        return BankAccount.objects.get(pk=response.json()["id"].split(":")[1])

    def record(self, **changes):
        entry = {
            "title": "Feira",
            "amount": "120.00",
            "category_id": self.food.pk,
            "instrument": f"credit:{self.card}",
            **changes,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("/api/ledger/transactions", entry)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def invoice(self):
        return CardInvoice.objects.get(card_id=self.card, reference_month=date(2026, 11, 1))

    def pay(self, amount="120.00", **changes):
        payload = {
            "account_id": self.account.pk,
            "amount": amount,
            "confirmation_key": str(uuid.uuid4()),
            **changes,
        }
        return self.post(f"/api/banking/invoices/{self.invoice().pk}/payments", payload)


class OverviewTests(WalletApiTestCase):
    def test_overview_groups_accounts_by_bank_with_balances_and_the_next_invoice(self):
        self.record()
        self.record(title="Aluguel", amount="300.00", instrument=f"account:{self.account.pk}")
        body = self.get("/api/banking/wallet").json()

        self.assertEqual([bank["name"] for bank in body["banks"]], ["Nubank"])
        accounts = {account["name"]: account for account in body["banks"][0]["accounts"]}
        self.assertEqual(accounts["Conta"]["balance"], "700.00")
        self.assertEqual(accounts["Reserva"]["balance"], "500.00")
        self.assertEqual(body["totals"], [{"currency": "BRL", "balance": "1200.00"}])

        card = accounts["Conta"]["credit_cards"][0]
        self.assertTrue(card["confirm_payments"])
        self.assertEqual(card["next_invoice"]["amount"], "120.00")
        self.assertEqual(card["next_invoice"]["remaining"], "120.00")
        self.assertEqual(card["next_invoice"]["due_date"], "2026-12-01")
        self.assertEqual(card["next_invoice"]["status"], "SCHEDULED")

    def test_overview_is_the_owners_only(self):
        self.client.force_login(self.other)
        self.assertEqual(self.get("/api/banking/wallet").json(), {"banks": [], "totals": []})

    def test_overview_needs_a_session(self):
        self.client.logout()
        self.assertEqual(self.get("/api/banking/wallet").status_code, 401)


class AccountTests(WalletApiTestCase):
    def path(self, account=None):
        return f"/api/banking/accounts/{(account or self.account).pk}"

    def change(self, **changes):
        values = {"bank_name": "Nubank", "name": "Conta", "opening_balance": "1000.00", **changes}
        return self.put(self.path(), values)

    def test_account_shows_its_movements_newest_first(self):
        self.record(
            title="Aluguel",
            amount="300.00",
            instrument=f"account:{self.account.pk}",
            date="2026-11-02",
        )
        self.record(
            title="Salário",
            amount="5000.00",
            instrument=f"account:{self.account.pk}",
            date="2026-11-05",
            transaction_type="INCOME",
            category_id=Category.objects.create(user=self.user, name="Renda").pk,
        )
        body = self.get(self.path()).json()
        self.assertEqual(body["balance"], "5700.00")
        self.assertEqual(
            [(row["label"], row["direction"], row["amount"]) for row in body["movements"]],
            [("Salário", "CREDIT", "5000.00"), ("Aluguel", "DEBIT", "300.00")],
        )

    def test_a_changed_opening_balance_changes_the_balance(self):
        response = self.change(name="Corrente", opening_balance="1500.00")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["balance"], "1500.00")
        self.assertEqual(response.json()["name"], "Corrente")

    def test_moving_the_last_account_of_a_bank_removes_the_empty_bank(self):
        self.put(
            self.path(self.savings),
            {"bank_name": "Itaú", "name": "Reserva", "opening_balance": "500.00"},
        )
        self.assertEqual(
            set(Bank.objects.filter(user=self.user).values_list("name", flat=True)),
            {"Nubank", "Itaú"},
        )
        self.change(bank_name="Itaú")
        self.assertEqual(
            set(Bank.objects.filter(user=self.user).values_list("name", flat=True)), {"Itaú"}
        )

    def test_a_duplicate_name_in_the_bank_is_refused(self):
        self.assertEqual(self.change(name="Reserva").status_code, 400)
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, "Conta")

    def test_an_account_with_records_is_not_deleted(self):
        self.assert_errors(self.delete(self.path()), 400, "__all__")  # It has a card.
        self.assertTrue(BankAccount.objects.filter(pk=self.account.pk).exists())

    def test_an_empty_account_is_deleted(self):
        self.assertEqual(self.delete(self.path(self.savings)).status_code, 204)
        self.assertFalse(BankAccount.objects.filter(pk=self.savings.pk).exists())

    def test_another_owner_cannot_read_change_or_delete(self):
        self.client.force_login(self.other)
        self.assertEqual(self.get(self.path()).status_code, 404)
        self.assertEqual(self.change(name="Minha").status_code, 404)
        self.assertEqual(self.delete(self.path()).status_code, 404)


class CreditCardTests(WalletApiTestCase):
    def path(self):
        return f"/api/banking/credit-cards/{self.card}"

    def test_card_lists_its_invoices_with_state(self):
        self.record(amount="300.00", installments=3)
        body = self.get(self.path()).json()
        self.assertEqual(
            [(row["reference_month"], row["amount"]) for row in body["invoices"]],
            [("2027-01-01", "100.00"), ("2026-12-01", "100.00"), ("2026-11-01", "100.00")],
        )

    def test_turning_confirmation_off_keeps_existing_invoices_confirmed(self):
        self.record()
        response = self.put(
            self.path(),
            {"name": "Black", "closing_day": 24, "due_day": 1, "confirm_payments": False},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["confirm_payments"])
        self.assertTrue(response.json()["invoices"][0]["confirm_payments"])

    def test_invalid_days_are_refused(self):
        response = self.put(
            self.path(),
            {"name": "Black", "closing_day": 40, "due_day": 1, "confirm_payments": True},
        )
        self.assert_errors(response, 400, "closing_day")

    def test_a_card_with_purchases_is_not_deleted_and_an_unused_one_is(self):
        self.record()
        self.assert_errors(self.delete(self.path()), 400, "__all__")
        unused = CreditCard.objects.create(
            user=self.user, account=self.account, name="Extra", closing_day=1, due_day=10
        )
        self.assertEqual(self.delete(f"/api/banking/credit-cards/{unused.pk}").status_code, 204)

    def test_another_owner_gets_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.get(self.path()).status_code, 404)


class InvoiceTests(WalletApiTestCase):
    def setUp(self):
        super().setUp()
        self.record()
        self.record(title="Notebook", amount="900.00", installments=3)

    def test_invoice_lines_add_up_to_its_amount(self):
        body = self.get(f"/api/banking/invoices/{self.invoice().pk}").json()
        self.assertEqual(
            [(line["title"], line["amount"]) for line in body["lines"]],
            [("Feira", "120.00"), ("Notebook", "300.00")],
        )
        self.assertEqual(body["amount"], "420.00")
        self.assertEqual(body["gross_amount"], "420.00")
        self.assertEqual(
            sum(Decimal(line["amount"]) for line in body["lines"]), Decimal(body["amount"])
        )

    def test_a_full_payment_settles_the_invoice_and_debits_the_account(self):
        response = self.pay("420.00")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            (body["status"], body["remaining"], body["confirmed_amount"]),
            ("PAID", "0.00", "420.00"),
        )
        self.assertEqual(account_balance(self.account), Decimal("580.00"))

    def test_a_part_payment_leaves_the_rest(self):
        body = self.pay("100.00").json()
        self.assertEqual((body["status"], body["remaining"]), ("PARTIAL", "320.00"))
        self.assertEqual(len(body["payments"]), 1)

    def test_a_payment_cannot_exceed_the_invoice_or_be_in_the_future(self):
        self.assert_errors(self.pay("420.01"), 400, "amount")
        self.assert_errors(self.pay("10.00", date="2026-11-11"), 400, "date")
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))

    def test_a_repeated_request_records_one_payment(self):
        key = str(uuid.uuid4())
        self.pay("100.00", confirmation_key=key)
        self.assertEqual(self.pay("100.00", confirmation_key=key).status_code, 200)
        self.assertEqual(InvoicePayment.objects.count(), 1)
        self.assertEqual(account_balance(self.account), Decimal("900.00"))

    def test_undoing_a_payment_restores_the_balance_and_the_state(self):
        payment = self.pay("420.00").json()["payments"][0]["id"]
        self.assertEqual(self.delete(f"/api/banking/invoice-payments/{payment}").status_code, 204)
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))
        self.assertEqual(
            self.get(f"/api/banking/invoices/{self.invoice().pk}").json()["status"], "SCHEDULED"
        )

    def test_an_automatic_invoice_refuses_a_confirmed_payment(self):
        automatic = CreditCard.objects.create(
            user=self.user, account=self.account, name="Auto", closing_day=24, due_day=1
        )
        self.record(instrument=f"credit:{automatic.pk}")
        invoice = CardInvoice.objects.get(card=automatic)
        response = self.post(
            f"/api/banking/invoices/{invoice.pk}/payments",
            {
                "account_id": self.account.pk,
                "amount": "120.00",
                "confirmation_key": str(uuid.uuid4()),
            },
        )
        self.assert_errors(response, 400, "invoice")

    def test_another_owners_invoice_payment_and_account_are_refused(self):
        payment = self.pay("100.00").json()["payments"][0]["id"]
        bank = Bank.objects.create(user=self.other, name="Itaú")
        foreign = BankAccount.objects.create(
            user=self.other, bank=bank, name="Alheia", currency="BRL"
        )
        self.assert_errors(self.pay("10.00", account_id=foreign.pk), 400, "account_id")
        self.client.force_login(self.other)
        self.assertEqual(self.get(f"/api/banking/invoices/{self.invoice().pk}").status_code, 404)
        self.assertEqual(self.pay("10.00").status_code, 404)
        self.assertEqual(self.delete(f"/api/banking/invoice-payments/{payment}").status_code, 404)
        self.assertEqual(InvoicePayment.objects.count(), 1)


class TransferTests(WalletApiTestCase):
    def transfer(self, **changes):
        payload = {
            "source_account_id": self.account.pk,
            "destination_account_id": self.savings.pk,
            "amount": "250.00",
            **changes,
        }
        return self.post("/api/banking/transfers", payload)

    def test_a_transfer_moves_money_between_two_accounts(self):
        self.assertEqual(self.transfer().status_code, 204)
        self.assertEqual(account_balance(self.account), Decimal("750.00"))
        self.assertEqual(account_balance(self.savings), Decimal("750.00"))

    def test_undoing_a_transfer_restores_both_balances(self):
        self.transfer()
        row = self.get(f"/api/banking/accounts/{self.account.pk}").json()["movements"][0]
        self.assertEqual(
            self.delete(f"/api/banking/transfers/{row['transfer_id']}").status_code, 204
        )
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))
        self.assertEqual(account_balance(self.savings), Decimal("500.00"))
        self.assertFalse(BankTransfer.objects.exists())

    def test_invalid_transfers_are_refused(self):
        self.assert_errors(
            self.transfer(destination_account_id=self.account.pk), 400, "destination_account_id"
        )
        self.assert_errors(self.transfer(amount="0"), 400, "amount")
        bank = Bank.objects.create(user=self.other, name="Itaú")
        foreign = BankAccount.objects.create(
            user=self.other, bank=bank, name="Alheia", currency="BRL"
        )
        self.assert_errors(
            self.transfer(destination_account_id=foreign.pk), 400, "destination_account_id"
        )
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))

    def test_another_owner_cannot_undo_a_transfer(self):
        self.transfer()
        self.client.force_login(self.other)
        self.assertEqual(
            self.delete(f"/api/banking/transfers/{BankTransfer.objects.get().pk}").status_code, 404
        )
