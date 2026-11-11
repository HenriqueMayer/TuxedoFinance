from datetime import date
from decimal import Decimal
from unittest.mock import patch

from banking.models import Bank, BankAccount, CardInvoice, CreditCard
from banking.services import account_balance
from config.testing import ApiTestCase
from ledger.categories import Category
from ledger.models import Transaction

TODAY = date(2026, 11, 10)


class LedgerApiTestCase(ApiTestCase):
    """One owner with an account, a credit card and two categories; today is fixed."""

    def setUp(self):
        super().setUp()
        clock = patch("django.utils.timezone.localdate", return_value=TODAY)
        clock.start()
        self.addCleanup(clock.stop)
        bank = Bank.objects.create(user=self.user, name="Nubank")
        self.account = BankAccount.objects.create(
            user=self.user,
            bank=bank,
            name="Conta",
            currency="BRL",
            opening_balance=Decimal("1000.00"),
        )
        self.card = CreditCard.objects.create(
            user=self.user, account=self.account, name="Platinum", closing_day=24, due_day=1
        )
        self.food = Category.objects.create(
            user=self.user, name="Mercado", transaction_type="EXPENSE"
        )
        self.salary = Category.objects.create(
            user=self.user, name="Salário", transaction_type="INCOME"
        )

    def entry(self, **changes):
        return {
            "title": "Feira",
            "amount": "120.50",
            "category_id": self.food.pk,
            "instrument": f"account:{self.account.pk}",
            **changes,
        }

    def record(self, **changes):
        """Record an entry and run the ledger synchronization that follows a commit."""
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("/api/ledger/transactions", self.entry(**changes))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class RecordTransactionTests(LedgerApiTestCase):
    def test_an_expense_needs_four_values_and_defaults_to_today(self):
        body = self.record()
        self.assertEqual(body["date"], "2026-11-10")
        self.assertEqual(body["transaction_type"], "EXPENSE")
        self.assertEqual(body["amount"], "120.50")
        self.assertEqual(body["currency"], "BRL")
        self.assertEqual(body["category"], {"id": self.food.pk, "name": "Mercado"})
        self.assertEqual(body["instrument"]["id"], f"account:{self.account.pk}")
        self.assertFalse(body["locked"])

    def test_an_account_expense_lowers_the_account_balance(self):
        self.record()
        self.assertEqual(account_balance(self.account), Decimal("879.50"))

    def test_an_income_raises_the_account_balance(self):
        self.record(
            transaction_type="INCOME", title="Salário", amount="5000", category_id=self.salary.pk
        )
        self.assertEqual(account_balance(self.account), Decimal("6000.00"))

    def test_a_card_expense_goes_to_the_statement_and_not_to_the_account(self):
        self.record(instrument=f"credit:{self.card.pk}")
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))
        invoice = CardInvoice.objects.get(card=self.card)
        self.assertEqual(invoice.amount, Decimal("120.50"))
        # Bought on the 10th, before the closing day 24: the November statement.
        self.assertEqual(invoice.reference_month, date(2026, 11, 1))

    def test_installments_split_the_amount_over_the_statements(self):
        self.record(instrument=f"credit:{self.card.pk}", amount="300.00", installments=3)
        amounts = CardInvoice.objects.filter(card=self.card).order_by("reference_month")
        self.assertEqual([invoice.amount for invoice in amounts], [Decimal("100.00")] * 3)

    def test_validation_errors_name_the_fields_of_the_request(self):
        cases = {
            "instrument": [
                {"instrument": "credit:999999"},
                {"instrument": "nonsense"},
                {
                    "transaction_type": "INCOME",
                    "category_id": self.salary.pk,
                    "instrument": f"credit:{self.card.pk}",
                },
            ],
            "category_id": [{"category_id": self.salary.pk}, {"category_id": 999999}],
            "amount": [{"amount": "0"}, {"amount": "-5"}],
            "title": [{"title": "   "}],
            "installments": [{"installments": 3}],  # Installments need a credit card.
        }
        for field, changes in cases.items():
            for change in changes:
                with self.subTest(field=field, change=change):
                    self.assert_errors(
                        self.post("/api/ledger/transactions", self.entry(**change)), 400, field
                    )
        self.assertFalse(Transaction.objects.exists())

    def test_every_error_of_an_entry_is_reported_in_one_answer(self):
        response = self.post(
            "/api/ledger/transactions",
            self.entry(title="", amount="0", category_id=0, instrument=""),
        )
        self.assert_errors(response, 400, "title", "amount", "category_id", "instrument")
        self.assertFalse(Transaction.objects.exists())

    def test_another_owners_records_cannot_be_used(self):
        bank = Bank.objects.create(user=self.other, name="Itaú")
        account = BankAccount.objects.create(
            user=self.other, bank=bank, name="Alheia", currency="BRL"
        )
        category = Category.objects.create(user=self.other, name="Alheia")
        self.assert_errors(
            self.post("/api/ledger/transactions", self.entry(instrument=f"account:{account.pk}")),
            400,
            "instrument",
        )
        self.assert_errors(
            self.post("/api/ledger/transactions", self.entry(category_id=category.pk)),
            400,
            "category_id",
        )

    def test_recording_needs_a_session_and_a_csrf_token(self):
        self.assertEqual(
            self.post("/api/ledger/transactions", self.entry(), csrf=False).status_code, 403
        )
        self.client.logout()
        self.assertEqual(self.post("/api/ledger/transactions", self.entry()).status_code, 401)


class ChangeTransactionTests(LedgerApiTestCase):
    def test_a_changed_amount_changes_the_balance(self):
        item = self.record()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.put(
                f"/api/ledger/transactions/{item['id']}", self.entry(amount="20.00", title="Pão")
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["title"], "Pão")
        self.assertEqual(account_balance(self.account), Decimal("980.00"))

    def test_moving_an_expense_to_the_card_restores_the_balance(self):
        item = self.record()
        with self.captureOnCommitCallbacks(execute=True):
            self.put(
                f"/api/ledger/transactions/{item['id']}",
                self.entry(instrument=f"credit:{self.card.pk}"),
            )
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))
        self.assertEqual(CardInvoice.objects.get(card=self.card).amount, Decimal("120.50"))

    def test_an_invalid_change_keeps_the_record(self):
        item = self.record()
        self.assert_errors(
            self.put(f"/api/ledger/transactions/{item['id']}", self.entry(amount="0")),
            400,
            "amount",
        )
        self.assertEqual(Transaction.objects.get().amount, Decimal("120.50"))

    def test_deleting_restores_the_balance(self):
        item = self.record()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.delete(f"/api/ledger/transactions/{item['id']}").status_code, 204)
        self.assertFalse(Transaction.objects.exists())
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))

    def test_another_owner_cannot_read_change_or_delete(self):
        item = self.record()
        self.client.force_login(self.other)
        path = f"/api/ledger/transactions/{item['id']}"
        self.assertEqual(self.get(path).status_code, 404)
        self.assertEqual(self.put(path, self.entry()).status_code, 404)
        self.assertEqual(self.delete(path).status_code, 404)
        self.assertTrue(Transaction.objects.filter(pk=item["id"]).exists())


class ListTransactionTests(LedgerApiTestCase):
    def setUp(self):
        super().setUp()
        self.record(title="Feira", amount="120.50", date="2026-11-03")
        self.record(title="Padaria", amount="18.00", date="2026-11-05")
        self.record(
            title="Salário",
            amount="5000.00",
            date="2026-11-01",
            transaction_type="INCOME",
            category_id=self.salary.pk,
        )
        self.record(
            title="Notebook",
            amount="3000.00",
            date="2026-10-28",
            instrument=f"credit:{self.card.pk}",
            installments=3,
        )

    def titles(self, **query):
        response = self.get("/api/ledger/transactions", **query)
        self.assertEqual(response.status_code, 200, response.content)
        return [item["title"] for item in response.json()["items"]]

    def test_default_order_is_newest_first_with_totals_of_full_amounts(self):
        body = self.get("/api/ledger/transactions").json()
        self.assertEqual(
            [item["title"] for item in body["items"]], ["Padaria", "Feira", "Salário", "Notebook"]
        )
        self.assertEqual((body["count"], body["page"], body["pages"]), (4, 1, 1))
        self.assertEqual((body["income"], body["expense"]), ("5000.00", "3138.50"))

    def test_search_type_category_instrument_and_sort(self):
        self.assertEqual(self.titles(q="pad"), ["Padaria"])
        self.assertEqual(self.titles(q="mercado"), ["Padaria", "Feira", "Notebook"])
        self.assertEqual(self.titles(type="INCOME"), ["Salário"])
        self.assertEqual(self.titles(category=self.salary.pk), ["Salário"])
        self.assertEqual(self.titles(instrument=f"credit:{self.card.pk}"), ["Notebook"])
        self.assertEqual(self.titles(sort="highest")[0], "Salário")
        self.assertEqual(self.titles(sort="oldest")[0], "Notebook")

    def test_a_month_lists_by_billed_month_and_shows_the_amount_of_that_month(self):
        # The notebook was bought after the closing day 24 of October: its three
        # installments fall on the statements of November, December and January.
        body = self.get("/api/ledger/transactions", month="2026-12").json()
        self.assertEqual(
            [(item["title"], item["month_amount"]) for item in body["items"]],
            [("Notebook", "1000.00")],
        )
        self.assertEqual((body["income"], body["expense"]), ("0", "1000.00"))

        november = self.get("/api/ledger/transactions", month="2026-11").json()
        self.assertEqual(november["count"], 4)
        self.assertEqual((november["income"], november["expense"]), ("5000.00", "1138.50"))

    def test_an_invalid_month_or_filter_is_ignored(self):
        self.assertEqual(
            len(self.titles(month="2026-13", type="NOPE", instrument="x:1", sort="nope")), 4
        )

    def test_the_list_is_the_owners_only(self):
        self.client.force_login(self.other)
        self.assertEqual(self.titles(), [])

    def test_pages_hold_fifty_rows(self):
        Transaction.objects.bulk_create(
            Transaction(
                user=self.user,
                title=f"Linha {number}",
                amount=Decimal("1.00"),
                transaction_type="EXPENSE",
                category=self.food,
                payment_channel="ACCOUNT",
                bank_account=self.account,
                date=date(2026, 9, 1),
            )
            for number in range(60)
        )
        body = self.get("/api/ledger/transactions", page=2).json()
        self.assertEqual(
            (body["count"], body["page"], body["pages"], len(body["items"])), (64, 2, 2, 14)
        )
        # A page past the end answers with the last page.
        self.assertEqual(self.get("/api/ledger/transactions", page=9).json()["page"], 2)


class SuggestionTests(LedgerApiTestCase):
    def test_a_known_title_suggests_its_category_and_instrument(self):
        self.record(title="Feira", instrument=f"credit:{self.card.pk}")
        body = self.get("/api/ledger/transactions/suggestion", title="feira ").json()
        self.assertEqual(
            body, {"category_id": self.food.pk, "instrument": f"credit:{self.card.pk}"}
        )

    def test_no_title_suggests_the_last_instrument_only(self):
        self.record(title="Feira")
        body = self.get("/api/ledger/transactions/suggestion").json()
        self.assertEqual(body, {"category_id": None, "instrument": f"account:{self.account.pk}"})

    def test_nothing_recorded_suggests_nothing(self):
        body = self.get("/api/ledger/transactions/suggestion", title="Feira").json()
        self.assertEqual(body, {"category_id": None, "instrument": None})

    def test_another_owners_entries_are_not_suggested(self):
        self.record(title="Feira")
        self.client.force_login(self.other)
        body = self.get("/api/ledger/transactions/suggestion", title="Feira").json()
        self.assertEqual(body, {"category_id": None, "instrument": None})


class CategoryApiTests(LedgerApiTestCase):
    def names(self):
        return [item["name"] for item in self.get("/api/ledger/categories").json()]

    def test_a_new_user_has_default_categories(self):
        self.assertIn("Groceries", self.names())

    def test_create_change_and_delete(self):
        created = self.post(
            "/api/ledger/categories", {"name": "Lazer", "transaction_type": "EXPENSE"}
        )
        self.assertEqual(created.status_code, 200, created.content)
        category_id = created.json()["id"]
        changed = self.put(
            f"/api/ledger/categories/{category_id}", {"name": "Cinema", "parent_id": self.food.pk}
        )
        self.assertEqual(
            changed.json(),
            {
                "id": category_id,
                "name": "Cinema",
                "transaction_type": None,
                "parent_id": self.food.pk,
            },
        )
        self.assertEqual(self.delete(f"/api/ledger/categories/{category_id}").status_code, 204)
        self.assertNotIn("Cinema", self.names())

    def test_duplicate_name_blank_name_and_circular_parent_are_refused(self):
        self.assertEqual(self.post("/api/ledger/categories", {"name": "Mercado"}).status_code, 400)
        self.assert_errors(self.post("/api/ledger/categories", {"name": " "}), 400, "name")
        child = Category.objects.create(
            user=self.user, name="Feira livre", parent_category=self.food
        )
        response = self.put(
            f"/api/ledger/categories/{self.food.pk}", {"name": "Mercado", "parent_id": child.pk}
        )
        self.assert_errors(response, 400, "parent_category")

    def test_a_category_with_records_is_not_deleted(self):
        self.record()
        response = self.delete(f"/api/ledger/categories/{self.food.pk}")
        self.assert_errors(response, 400, "__all__")
        self.assertTrue(Category.objects.filter(pk=self.food.pk).exists())

    def test_another_owners_category_is_hidden_and_cannot_be_a_parent(self):
        foreign = Category.objects.create(user=self.other, name="Alheia")
        self.assertNotIn("Alheia", self.names())
        self.assertEqual(
            self.put(f"/api/ledger/categories/{foreign.pk}", {"name": "Minha"}).status_code, 404
        )
        self.assertEqual(self.delete(f"/api/ledger/categories/{foreign.pk}").status_code, 404)
        self.assert_errors(
            self.post("/api/ledger/categories", {"name": "Nova", "parent_id": foreign.pk}),
            400,
            "parent_id",
        )
