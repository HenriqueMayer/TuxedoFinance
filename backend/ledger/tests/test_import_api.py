import base64
from datetime import date
from decimal import Decimal

from banking.models import BankAccount, CardInvoice
from config.testing import ApiTestCase
from ledger.models import Transaction
from ledger.statements import ImportBatch
from reports.tests.test_api import ReportsApiTestCase

IMPORTS = "/api/imports"

CSV = "Data;Histórico;Valor;Identificador\n03/11/2026;Padaria;-25,50;a1\n05/11/2026;Salário;5.000,00;a2\n"


def ofx(*rows):
    """Return an OFX file with ``(day, amount, identifier, memo)`` rows of November 2026."""
    body = "".join(
        f"<STMTTRN><DTPOSTED>202611{day:02d}\n<TRNAMT>{amount}\n<FITID>{fitid}\n<MEMO>{memo}\n</STMTTRN>"
        for day, amount, fitid, memo in rows
    )
    return f"<OFX><CURDEF>BRL\n<ACCTID>12345\n{body}</OFX>"


STATEMENT = ofx((3, "-25.50", "f1", "Padaria"), (5, "5000.00", "f2", "Salário"))


class ImportTestCase(ReportsApiTestCase):
    """Today is 2026-11-10. The account holds 1000.00 since 2026-01-01."""

    def setUp(self):
        super().setUp()
        self.account.opening_date = date(2026, 1, 1)
        self.account.save()

    def upload(self, text=STATEMENT, name="extrato.ofx", **changes):
        payload = {
            "account_id": self.account.pk,
            "file_name": name,
            "content": base64.b64encode(text.encode()).decode(),
            **changes,
        }
        return self.post(IMPORTS, payload)

    def staged(self, text=STATEMENT, name="extrato.ofx", **changes):
        response = self.upload(text, name, **changes)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def decide(self, batch, *decisions):
        response = self.put(f"{IMPORTS}/{batch['id']}/decisions", {"decisions": list(decisions)})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def create_all(self, batch):
        return self.decide(
            batch,
            *(
                {
                    "row_id": row["id"],
                    "action": "CREATE",
                    "category_id": (self.salary if Decimal(row["amount"]) > 0 else self.market).pk,
                }
                for row in batch["rows"]
            ),
        )

    def confirm(self, batch):
        with self.captureOnCommitCallbacks(execute=True):
            return self.post(f"{IMPORTS}/{batch['id']}/confirm", {"digest": batch["digest"]})

    def balance(self):
        wallet = self.get("/api/banking/wallet").json()
        return wallet["banks"][0]["accounts"][0]["balance"]


class StagingTests(ImportTestCase):
    def test_an_ofx_file_is_ready_for_review_and_creates_nothing(self):
        batch = self.staged()
        self.assertEqual(
            (batch["status"], batch["file_format"], batch["currency"]), ("READY", "OFX", "BRL")
        )
        self.assertEqual(batch["account_name"], "Nubank · Conta")
        self.assertEqual(
            [(row["date"], row["amount"], row["description"]) for row in batch["rows"]],
            [("2026-11-03", "-25.50", "Padaria"), ("2026-11-05", "5000.00", "Salário")],
        )
        # No entry has these descriptions yet, so the owner decides both rows.
        self.assertEqual([row["action"] for row in batch["rows"]], ["", ""])
        self.assertEqual(batch["undecided"], 2)
        self.assertFalse(batch["needs_opening_date"])
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.balance(), "1000.00")

    def test_the_same_file_again_opens_the_same_import(self):
        first = self.staged()
        second = self.staged()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(ImportBatch.objects.count(), 1)
        (listed,) = self.get(IMPORTS).json()
        self.assertEqual(
            (listed["id"], listed["file_name"], listed["status"], listed["rows"]),
            (first["id"], "extrato.ofx", "READY", 2),
        )

    def test_a_csv_file_proposes_its_columns_and_waits_for_them(self):
        batch = self.staged(CSV, "extrato.csv")
        self.assertEqual((batch["status"], batch["file_format"]), ("STAGED", "CSV"))
        self.assertEqual(batch["headers"], ["Data", "Histórico", "Valor", "Identificador"])
        self.assertEqual(batch["rows"], [])
        self.assertEqual(batch["sample"][0]["Histórico"], "Padaria")
        mapping = batch["mapping"]
        self.assertEqual(
            {
                name: mapping[name]
                for name in ("date_column", "description_column", "amount_column")
            },
            {"date_column": "Data", "description_column": "Histórico", "amount_column": "Valor"},
        )
        self.assertEqual(
            (mapping["id_column"], mapping["date_format"], mapping["decimal_mark"]),
            ("Identificador", "%d/%m/%Y", ","),
        )
        response = self.put(f"{IMPORTS}/{batch['id']}/mapping", mapping)
        self.assertEqual(response.status_code, 200, response.content)
        ready = response.json()
        self.assertEqual(ready["status"], "READY")
        self.assertEqual(
            [(row["date"], row["amount"]) for row in ready["rows"]],
            [("2026-11-03", "-25.50"), ("2026-11-05", "5000.00")],
        )

    def test_wrong_columns_keep_the_file_staged(self):
        batch = self.staged(CSV, "extrato.csv")
        mapping = {**batch["mapping"], "date_format": "%Y-%m-%d"}
        response = self.put(f"{IMPORTS}/{batch['id']}/mapping", mapping)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.get(f"{IMPORTS}/{batch['id']}").json()["status"], "STAGED")

    def test_a_file_that_is_not_a_statement_is_refused(self):
        self.assertEqual(self.upload("not a statement", "notes.csv").status_code, 400)
        self.assert_errors(self.upload(content="***"), 400, "content")
        other = ofx((3, "-1.00", "u1", "Coffee")).replace("BRL", "USD")
        self.assertEqual(self.upload(other).status_code, 400)
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_an_opening_balance_without_a_date_is_reported(self):
        self.account.opening_date = None
        self.account.save()
        batch = self.staged()
        self.assertTrue(batch["needs_opening_date"])
        # A decision that creates a record is refused until the opening balance has its date.
        decision = {
            "row_id": batch["rows"][0]["id"],
            "action": "CREATE",
            "category_id": self.market.pk,
        }
        response = self.put(f"{IMPORTS}/{batch['id']}/decisions", {"decisions": [decision]})
        self.assert_errors(response, 400, "__all__")


class SuggestionTests(ImportTestCase):
    def test_a_known_description_gets_its_category(self):
        self.record(title="padaria", amount="9.00", date="2026-10-20", category_id=self.food.pk)
        batch = self.staged()
        first, second = batch["rows"]
        self.assertEqual((first["action"], first["category_id"]), ("CREATE", self.food.pk))
        self.assertEqual(second["action"], "")
        self.assertEqual(batch["undecided"], 1)

    def test_a_row_that_equals_a_recorded_movement_is_matched(self):
        self.record(title="Pão", amount="25.50", date="2026-11-03")
        batch = self.staged()
        row = batch["rows"][0]
        self.assertEqual(row["action"], "MATCH")
        self.assertEqual([match["id"] for match in row["matches"]], [row["matched_movement_id"]])
        self.assertEqual(row["matches"][0]["label"], "Pão")

    def test_a_bank_identifier_confirmed_before_is_skipped(self):
        self.assertEqual(self.confirm(self.create_all(self.staged())).status_code, 200)
        again = self.staged(ofx((3, "-25.50", "f1", "Padaria"), (8, "-10.00", "f3", "Café")))
        first, second = again["rows"]
        self.assertEqual((first["action"], first["duplicate"]), ("SKIP", True))
        self.assertEqual((second["action"], second["duplicate"]), ("", False))


class ConfirmationTests(ImportTestCase):
    def test_reviewed_rows_become_entries_once(self):
        batch = self.create_all(self.staged(closing_balance="5974.50", closing_date="2026-11-05"))
        self.assertEqual(batch["undecided"], 0)
        response = self.confirm(batch)
        self.assertEqual(response.status_code, 200, response.content)
        confirmed = response.json()
        self.assertEqual(confirmed["status"], "CONFIRMED")
        self.assertEqual(
            confirmed["reconciliation"],
            {
                "date": "2026-11-05",
                "expected": "5974.50",
                "actual": "5974.50",
                "difference": "0.00",
            },
        )
        titles = sorted(Transaction.objects.values_list("title", "amount"))
        self.assertEqual(titles, [("Padaria", Decimal("25.50")), ("Salário", Decimal("5000.00"))])
        self.assertEqual(self.balance(), "5974.50")
        # A second confirmation changes nothing.
        self.assertEqual(self.confirm(batch).status_code, 200)
        self.assertEqual(Transaction.objects.count(), 2)

    def test_a_matched_row_creates_nothing(self):
        self.record(title="Pão", amount="25.50", date="2026-11-03")
        batch = self.staged(ofx((3, "-25.50", "f1", "Padaria")))
        self.assertEqual(self.confirm(batch).status_code, 200)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(self.balance(), "974.50")

    def test_an_undecided_row_or_a_changed_review_refuses_the_confirmation(self):
        batch = self.staged()
        self.assertEqual(self.confirm(batch).status_code, 400)
        decided = self.create_all(batch)
        self.assertEqual(self.confirm(batch).status_code, 400)  # The digest of the first reading.
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.confirm(decided).status_code, 200)

    def test_a_decision_with_a_wrong_reference_is_refused(self):
        batch = self.staged()
        row = batch["rows"][0]["id"]
        wrong = (
            {"row_id": row, "action": "CREATE"},
            {"row_id": row, "action": "CREATE", "category_id": self.salary.pk},
            {"row_id": row, "action": "MATCH", "matched_movement_id": 999999},
            {"row_id": row, "action": "TRANSFER", "counterparty_account_id": self.account.pk},
            {"row_id": 999999, "action": "SKIP"},
        )
        for decision in wrong:
            with self.subTest(decision=decision):
                response = self.put(f"{IMPORTS}/{batch['id']}/decisions", {"decisions": [decision]})
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.get(f"{IMPORTS}/{batch['id']}").json()["undecided"], 2)

    def test_a_row_can_pay_an_invoice_or_be_a_transfer(self):
        self.record(amount="200.00", instrument=f"credit:{self.manual.pk}")
        invoice = CardInvoice.objects.get(card=self.manual)
        savings = BankAccount.objects.create(
            user=self.user,
            bank=self.account.bank,
            name="Reserva",
            currency="BRL",
            opening_date=date(2026, 1, 1),
        )
        batch = self.staged(
            ofx((9, "-200.00", "p1", "Pagamento fatura"), (9, "-300.00", "t1", "TED"))
        )
        self.assertEqual([item["id"] for item in batch["invoices"]], [invoice.pk])
        self.assertEqual(batch["invoices"][0]["card_name"], "Black")
        payment, transfer = batch["rows"]
        decided = self.decide(
            batch,
            {"row_id": payment["id"], "action": "PAY_INVOICE", "invoice_id": invoice.pk},
            {
                "row_id": transfer["id"],
                "action": "TRANSFER",
                "counterparty_account_id": savings.pk,
                "counterparty_amount": "300.00",
            },
        )
        self.assertEqual(self.confirm(decided).status_code, 200)
        self.assertEqual(self.balance(), "500.00")
        self.assertEqual(savings.current_balance(), Decimal("300.00"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.current_state.remaining_amount, Decimal("0.00"))

    def test_an_undone_import_removes_its_entries_and_frees_the_file(self):
        batch = self.create_all(self.staged())
        self.confirm(batch)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(f"{IMPORTS}/{batch['id']}/undo")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "UNDONE")
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.balance(), "1000.00")
        self.assertNotEqual(self.staged()["id"], batch["id"])

    def test_an_edited_entry_refuses_the_undo(self):
        batch = self.create_all(self.staged())
        self.confirm(batch)
        Transaction.objects.filter(title="Padaria").update(amount=Decimal("30.00"))
        self.assertEqual(self.post(f"{IMPORTS}/{batch['id']}/undo").status_code, 400)
        self.assertEqual(Transaction.objects.count(), 2)

    def test_an_import_is_discarded_before_its_confirmation_only(self):
        batch = self.staged()
        self.assertEqual(self.delete(f"{IMPORTS}/{batch['id']}").status_code, 204)
        self.assertEqual(ImportBatch.objects.count(), 0)
        batch = self.create_all(self.staged())
        self.confirm(batch)
        self.assertEqual(self.delete(f"{IMPORTS}/{batch['id']}").status_code, 400)


class OwnerTests(ImportTestCase):
    def test_the_imports_and_accounts_of_another_owner_are_out_of_reach(self):
        batch = self.staged()
        self.client.force_login(self.other)
        self.assertEqual(self.get(IMPORTS).json(), [])
        path = f"{IMPORTS}/{batch['id']}"
        self.assertEqual(self.get(path).status_code, 404)
        self.assertEqual(
            self.put(
                f"{path}/mapping", {"date_column": "a", "description_column": "b"}
            ).status_code,
            404,
        )
        self.assertEqual(self.put(f"{path}/decisions", {"decisions": []}).status_code, 404)
        self.assertEqual(self.post(f"{path}/confirm", {"digest": "x"}).status_code, 404)
        self.assertEqual(self.post(f"{path}/undo").status_code, 404)
        self.assertEqual(self.delete(path).status_code, 404)
        self.assert_errors(self.upload(), 400, "account_id")


class SessionTests(ApiTestCase):
    signed_in = False

    def test_imports_need_a_session(self):
        self.assertEqual(self.get(IMPORTS).status_code, 401)
        self.assertEqual(self.post(IMPORTS, {}).status_code, 401)
        self.assertEqual(self.get(f"{IMPORTS}/1").status_code, 401)
        self.assertEqual(self.put(f"{IMPORTS}/1/mapping", {}).status_code, 401)
        self.assertEqual(self.put(f"{IMPORTS}/1/decisions", {}).status_code, 401)
        self.assertEqual(self.post(f"{IMPORTS}/1/confirm", {}).status_code, 401)
        self.assertEqual(self.post(f"{IMPORTS}/1/undo").status_code, 401)
        self.assertEqual(self.delete(f"{IMPORTS}/1").status_code, 401)
