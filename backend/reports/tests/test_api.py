import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from banking.models import Bank, BankAccount, CardInvoice, CreditCard
from config.testing import ApiTestCase
from ledger.categories import Category
from ledger.models import Transaction, TransactionSplit

TODAY = date(2026, 11, 10)


class ReportsApiTestCase(ApiTestCase):
    """One owner with an account, two cards and a small category tree; today is fixed."""

    def setUp(self):
        super().setUp()
        self.set_today(TODAY)
        bank = Bank.objects.create(user=self.user, name="Nubank")
        self.account = BankAccount.objects.create(
            user=self.user,
            bank=bank,
            name="Conta",
            currency="BRL",
            opening_balance=Decimal("1000.00"),
        )
        # This card settles from the account on the due date.
        self.card = CreditCard.objects.create(
            user=self.user, account=self.account, name="Platinum", closing_day=24, due_day=1
        )
        # This card waits for a confirmed payment.
        self.manual = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name="Black",
            closing_day=24,
            due_day=5,
            manual_settlement_from=date(2026, 1, 1),
        )
        self.food = Category.objects.create(
            user=self.user, name="Alimentação", transaction_type="EXPENSE"
        )
        self.market = Category.objects.create(
            user=self.user, name="Mercado", parent_category=self.food
        )
        self.fun = Category.objects.create(user=self.user, name="Lazer", transaction_type="EXPENSE")
        self.salary = Category.objects.create(
            user=self.user, name="Salário", transaction_type="INCOME"
        )

    def set_today(self, value):
        clock = patch("django.utils.timezone.localdate", return_value=value)
        clock.start()
        self.addCleanup(clock.stop)
        return clock

    def record(self, **changes):
        entry = {
            "title": "Feira",
            "amount": "100.00",
            "category_id": self.market.pk,
            "instrument": f"account:{self.account.pk}",
            **changes,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("/api/ledger/transactions", entry)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class MonthResultTests(ReportsApiTestCase):
    def test_a_month_adds_income_and_expenses_by_billed_month(self):
        self.record(
            title="Salário", amount="5000.00", transaction_type="INCOME", category_id=self.salary.pk
        )
        self.record(amount="120.50")
        self.record(
            title="Cinema",
            amount="60.00",
            category_id=self.fun.pk,
            instrument=f"credit:{self.card.pk}",
        )
        # Bought after the closing day of October: it belongs to November too.
        self.record(
            title="Jantar", amount="80.00", date="2026-10-28", instrument=f"credit:{self.card.pk}"
        )
        self.record(title="Outubro", amount="40.00", date="2026-10-05")

        result = self.get("/api/reports/home").json()["result"]
        self.assertEqual(
            result,
            [
                {
                    "currency": "BRL",
                    "income": "5000.00",
                    "expenses": "260.50",
                    "left": "4739.50",
                    "previous_expenses": "40.00",
                }
            ],
        )

    def test_an_installment_plan_counts_one_installment_in_each_month(self):
        self.record(
            title="Notebook", amount="900.00", instrument=f"credit:{self.card.pk}", installments=3
        )
        for month in ("2026-11", "2026-12", "2027-01"):
            with self.subTest(month=month):
                result = self.get("/api/reports/month", month=month).json()["result"]
                self.assertEqual(result[0]["expenses"], "300.00")
        self.assertEqual(self.get("/api/reports/month", month="2027-02").json()["result"], [])

    def test_home_and_the_transactions_list_give_the_same_month_totals(self):
        self.record(
            title="Salário", amount="5000.00", transaction_type="INCOME", category_id=self.salary.pk
        )
        self.record(amount="120.50")
        self.record(
            title="Notebook", amount="900.00", instrument=f"credit:{self.card.pk}", installments=3
        )
        home = self.get("/api/reports/home").json()["result"][0]
        listed = self.get("/api/ledger/transactions", month="2026-11").json()
        self.assertEqual((home["income"], home["expenses"]), (listed["income"], listed["expense"]))

    def test_a_month_without_records_is_empty_and_an_invalid_month_is_the_current_one(self):
        body = self.get("/api/reports/month", month="nonsense").json()
        self.assertEqual((body["month"], body["result"], body["spending"]), ("2026-11-01", [], []))

    def test_reads_are_the_owners_only_and_need_a_session(self):
        self.record()
        self.client.force_login(self.other)
        body = self.get("/api/reports/home").json()
        self.assertEqual((body["result"], body["spending"], body["due"]), ([], [], []))
        self.client.logout()
        self.assertEqual(self.get("/api/reports/home").status_code, 401)
        self.assertEqual(self.get("/api/reports/month").status_code, 401)


class SpendingTests(ReportsApiTestCase):
    def test_a_subcategory_counts_in_its_parent_and_is_listed_under_it(self):
        self.record(amount="100.00")  # Mercado, inside Alimentação.
        self.record(title="Restaurante", amount="50.00", category_id=self.food.pk)
        self.record(title="Cinema", amount="60.00", category_id=self.fun.pk)
        self.record(
            title="Salário", amount="5000.00", transaction_type="INCOME", category_id=self.salary.pk
        )

        spending = self.get("/api/reports/home").json()["spending"]
        self.assertEqual(
            [(row["name"], row["amount"]) for row in spending],
            [("Alimentação", "150.00"), ("Lazer", "60.00")],
        )
        self.assertEqual(
            spending[0]["children"],
            [{"category_id": self.market.pk, "name": "Mercado", "amount": "100.00"}],
        )
        self.assertEqual(spending[1]["children"], [])

    def test_a_split_entry_counts_in_each_of_its_categories(self):
        item = self.record(title="Compras", amount="100.00")
        source = Transaction.objects.get(pk=item["id"])
        TransactionSplit.objects.create(
            transaction=source, category=self.market, amount=Decimal("70.00")
        )
        TransactionSplit.objects.create(
            transaction=source, category=self.fun, amount=Decimal("30.00")
        )
        spending = self.get("/api/reports/home").json()["spending"]
        self.assertEqual(
            [(row["name"], row["amount"]) for row in spending],
            [("Alimentação", "70.00"), ("Lazer", "30.00")],
        )

    def test_the_categories_add_up_to_the_expenses_of_the_month(self):
        self.record(amount="33.33")
        self.record(
            title="Cinema",
            amount="66.67",
            category_id=self.fun.pk,
            instrument=f"credit:{self.card.pk}",
        )
        self.record(
            title="Notebook",
            amount="1000.00",
            category_id=self.fun.pk,
            instrument=f"credit:{self.card.pk}",
            installments=3,
        )
        body = self.get("/api/reports/home").json()
        total = sum(Decimal(row["amount"]) for row in body["spending"])
        self.assertEqual(total, Decimal(body["result"][0]["expenses"]))


class TrendTests(ReportsApiTestCase):
    def test_the_trend_has_six_months_in_order_with_zeros(self):
        self.record(amount="40.00", date="2026-09-10")
        self.record(amount="100.00")
        trend = self.get("/api/reports/month").json()["trend"]
        self.assertEqual(
            [row["month"] for row in trend], [f"2026-{m:02d}-01" for m in range(6, 12)]
        )
        self.assertEqual(
            [row["expenses"] for row in trend], ["0.00", "0.00", "0.00", "40.00", "0.00", "100.00"]
        )


class DueSoonTests(ReportsApiTestCase):
    def due(self):
        return [
            (row["title"], row["due_date"], row["amount"], row["status"])
            for row in self.get("/api/reports/home").json()["due"]
        ]

    def test_open_invoices_are_listed_by_due_date(self):
        self.record(amount="200.00", instrument=f"credit:{self.manual.pk}")
        self.record(amount="60.00", instrument=f"credit:{self.card.pk}")
        self.assertEqual(
            self.due(),
            [
                ("Platinum", "2026-12-01", "60.00", "SCHEDULED"),
                ("Black", "2026-12-05", "200.00", "SCHEDULED"),
            ],
        )

    def test_a_paid_invoice_and_an_invoice_far_ahead_are_not_listed(self):
        self.record(amount="200.00", instrument=f"credit:{self.manual.pk}")
        self.record(
            title="Longe", amount="900.00", instrument=f"credit:{self.card.pk}", installments=3
        )
        invoice = CardInvoice.objects.get(card=self.manual)
        self.post(
            f"/api/banking/invoices/{invoice.pk}/payments",
            {
                "account_id": self.account.pk,
                "amount": "200.00",
                "confirmation_key": str(uuid.uuid4()),
            },
        )
        # Only the statement due on 1 December is inside 45 days.
        self.assertEqual(self.due(), [("Platinum", "2026-12-01", "300.00", "SCHEDULED")])

    def test_an_unpaid_invoice_past_its_due_date_is_overdue_and_an_automatic_one_is_gone(self):
        self.record(amount="200.00", instrument=f"credit:{self.manual.pk}")
        self.record(amount="60.00", instrument=f"credit:{self.card.pk}")
        self.set_today(date(2026, 12, 6))
        self.assertEqual(self.due(), [("Black", "2026-12-05", "200.00", "OVERDUE")])


class DueBillTests(ReportsApiTestCase):
    def bills(self):
        rows = self.get("/api/reports/home").json()["due"]
        return [
            (row["kind"], row["title"], row["due_date"], row["amount"], row["status"])
            for row in rows
        ]

    def test_a_repeating_expense_is_listed_until_its_date_each_month(self):
        self.record(title="Internet", amount="110.00", date="2026-10-20", is_fixed=True)
        # October passed and needs no confirmation. November and December are inside 45 days.
        self.assertEqual(
            self.bills(),
            [
                ("bill", "Internet", "2026-11-20", "110.00", "SCHEDULED"),
                ("bill", "Internet", "2026-12-20", "110.00", "SCHEDULED"),
            ],
        )

    def test_a_month_that_waits_for_confirmation_is_listed_after_its_date(self):
        self.set_today(date(2026, 10, 1))
        item = self.record(
            title="Aluguel",
            amount="1500.00",
            date="2026-10-05",
            is_fixed=True,
            requires_confirmation=True,
        )
        self.set_today(TODAY)
        self.assertEqual(
            self.bills(),
            [
                ("bill", "Aluguel", "2026-10-05", "1500.00", "AWAITING"),
                ("bill", "Aluguel", "2026-11-05", "1500.00", "AWAITING"),
                ("bill", "Aluguel", "2026-12-05", "1500.00", "SCHEDULED"),
            ],
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.post(f"/api/ledger/transactions/{item['id']}/schedule/2026-10/confirm")
        self.assertEqual([row[2] for row in self.bills()], ["2026-11-05", "2026-12-05"])

    def test_repeating_income_and_card_expenses_are_not_bills(self):
        self.record(
            title="Salário",
            amount="5000.00",
            date="2026-11-20",
            is_fixed=True,
            transaction_type="INCOME",
            category_id=self.salary.pk,
        )
        self.record(
            title="Streaming", amount="40.00", is_fixed=True, instrument=f"credit:{self.card.pk}"
        )
        rows = self.get("/api/reports/home").json()["due"]
        self.assertEqual([row["kind"] for row in rows], ["invoice"])
