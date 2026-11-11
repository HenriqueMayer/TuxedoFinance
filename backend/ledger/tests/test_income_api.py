from datetime import date
from decimal import Decimal

from banking.models import Bank, BankAccount
from ledger.models import RecurringIncome, ScheduleAmount, Transaction
from ledger.tests.test_api import LedgerApiTestCase

URL = "/api/incomes"


class IncomeTestCase(LedgerApiTestCase):
    """Today is 2026-11-10. A salary in two parts: the 5th and the 20th."""

    def payload(self, **changes):
        return {
            "name": "Salário",
            "category_id": self.salary.pk,
            "account_id": self.account.pk,
            "start": "2026-11-01",
            "parts": [{"day": 20, "amount": "2000.00"}, {"day": 5, "amount": "2800.00"}],
            **changes,
        }

    def create(self, **changes):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(URL, self.payload(**changes))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def change(self, body, **changes):
        payload = {
            "name": body["name"],
            "category_id": body["category"]["id"],
            "account_id": body["account"]["id"],
            "until": body["until"],
            "confirm": body["confirm"],
            "gross": body["gross"],
            "advance_percent": body["advance_percent"],
            "parts": [
                {"id": part["id"], "day": part["day"], "amount": part["amount"]}
                for part in body["parts"]
            ],
            **changes,
        }
        with self.captureOnCommitCallbacks(execute=True):
            return self.put(f"{URL}/{body['id']}", payload)

    def changed(self, body, **changes):
        response = self.change(body, **changes)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def entries(self):
        return list(Transaction.objects.filter(user=self.user).order_by("date"))


class CreateIncomeTests(IncomeTestCase):
    def test_each_part_is_a_repeating_income_entry_of_the_account(self):
        body = self.create()
        first, second = self.entries()
        self.assertEqual((first.date, second.date), (date(2026, 11, 5), date(2026, 11, 20)))
        for entry in (first, second):
            self.assertEqual(
                (entry.title, entry.transaction_type, entry.is_fixed, entry.installments),
                ("Salário", "INCOME", True, 1),
            )
            self.assertEqual(
                (entry.bank_account_id, entry.category_id, entry.recurring_income_id),
                (self.account.pk, self.salary.pk, body["id"]),
            )
        self.assertEqual((first.amount, second.amount), (Decimal("2800.00"), Decimal("2000.00")))

    def test_the_answer_lists_the_parts_by_day_with_the_next_date_and_the_total(self):
        body = self.create()
        self.assertEqual(
            (body["name"], body["currency"], body["total"]), ("Salário", "BRL", "4800.00")
        )
        self.assertEqual(body["category"], {"id": self.salary.pk, "name": "Salário"})
        self.assertEqual(body["account"]["name"], "Conta")
        self.assertEqual(
            [(part["day"], part["amount"], part["next_date"]) for part in body["parts"]],
            [(5, "2800.00", "2026-12-05"), (20, "2000.00", "2026-11-20")],
        )
        self.assertEqual((body["until"], body["confirm"]), (None, False))

    def test_a_part_with_a_past_day_is_in_the_balance_already(self):
        self.create()
        balance = self.get(f"/api/banking/accounts/{self.account.pk}").json()["balance"]
        self.assertEqual(balance, "3800.00")

    def test_without_a_start_the_first_month_is_the_current_one(self):
        self.create(start=None)
        self.assertEqual([entry.date.month for entry in self.entries()], [11, 11])

    def test_the_inputs_of_the_calculation_are_kept(self):
        body = self.create(gross="5000.00", advance_percent="40.00")
        self.assertEqual((body["gross"], body["advance_percent"]), ("5000.00", "40.00"))

    def test_confirmation_starts_with_the_current_month(self):
        body = self.create(confirm=True)
        self.assertTrue(body["confirm"])
        for entry in self.entries():
            self.assertEqual(
                (entry.requires_confirmation, entry.confirmation_start), (True, date(2026, 11, 1))
            )
        # A part that waits for its confirmation does not change the balance.
        balance = self.get(f"/api/banking/accounts/{self.account.pk}").json()["balance"]
        self.assertEqual(balance, "1000.00")

    def test_an_income_needs_a_name_one_part_and_valid_days_and_amounts(self):
        self.assert_errors(self.post(URL, self.payload(name=" ")), 400, "name")
        self.assert_errors(self.post(URL, self.payload(parts=[])), 400, "parts")
        bad = [{"day": 32, "amount": "10.00"}, {"day": 5, "amount": "0.00"}]
        self.assert_errors(self.post(URL, self.payload(parts=bad)), 400, "parts")
        many = [{"day": day, "amount": "10.00"} for day in range(1, 8)]
        self.assert_errors(self.post(URL, self.payload(parts=many)), 400, "parts")
        self.assertEqual(RecurringIncome.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_the_account_and_the_category_are_the_owners_and_the_category_takes_income(self):
        bank = Bank.objects.create(user=self.other, name="Outro")
        foreign = BankAccount.objects.create(
            user=self.other, bank=bank, name="Alheia", currency="BRL", opening_balance=0
        )
        self.assert_errors(self.post(URL, self.payload(account_id=foreign.pk)), 400, "account_id")
        self.assert_errors(
            self.post(URL, self.payload(category_id=self.food.pk)), 400, "category_id"
        )
        self.assertEqual(Transaction.objects.count(), 0)


class ListIncomeTests(IncomeTestCase):
    def test_the_list_has_each_income_and_the_total_of_a_month_by_currency(self):
        self.create()
        self.create(name="Aluguel", parts=[{"day": 12, "amount": "900.00"}])
        body = self.get(URL).json()
        self.assertEqual([item["name"] for item in body["items"]], ["Aluguel", "Salário"])
        self.assertEqual(body["totals"], [{"currency": "BRL", "amount": "5700.00"}])

    def test_the_list_is_the_owners_only_and_needs_a_session(self):
        body = self.create()
        self.client.force_login(self.other)
        self.assertEqual(self.get(URL).json(), {"items": [], "totals": []})
        self.assertEqual(self.get(f"{URL}/{body['id']}").status_code, 404)
        self.assertEqual(self.change(body).status_code, 404)
        self.assertEqual(self.delete(f"{URL}/{body['id']}").status_code, 404)
        self.client.logout()
        self.assertEqual(self.get(URL).status_code, 401)
        self.assertEqual(self.post(URL, self.payload()).status_code, 401)


class ChangeIncomeTests(IncomeTestCase):
    def test_the_name_and_the_category_reach_every_part(self):
        other = self.salary.__class__.objects.create(
            user=self.user, name="Renda extra", transaction_type="INCOME"
        )
        body = self.changed(self.create(), name="Salário CLT", category_id=other.pk)
        self.assertEqual(body["name"], "Salário CLT")
        self.assertEqual(
            {(entry.title, entry.category_id) for entry in self.entries()},
            {("Salário CLT", other.pk)},
        )

    def test_an_amount_and_a_day_change_while_the_income_has_no_past_month(self):
        body = self.create()
        body["parts"][0].update(day=7, amount="3000.00")
        body = self.changed(body)
        self.assertEqual(
            [(part["day"], part["amount"]) for part in body["parts"]],
            [(7, "3000.00"), (20, "2000.00")],
        )
        self.assertEqual(self.entries()[0].date, date(2026, 11, 7))
        self.assertEqual(ScheduleAmount.objects.count(), 0)

    def test_with_past_months_a_new_amount_holds_from_the_next_receipt(self):
        body = self.create(start="2026-09-01")
        body["parts"][0]["amount"] = "3000.00"  # The 5th: the next receipt is in December.
        body["parts"][1]["amount"] = "2100.00"  # The 20th: the next receipt is in November.
        body = self.changed(body)
        self.assertEqual([part["amount"] for part in body["parts"]], ["3000.00", "2100.00"])
        self.assertEqual(body["total"], "5100.00")
        # The past months keep their amounts.
        first, second = self.entries()
        self.assertEqual((first.amount, second.amount), (Decimal("2800.00"), Decimal("2000.00")))
        self.assertEqual(
            sorted(ScheduleAmount.objects.values_list("effective_month", "amount")),
            [(date(2026, 11, 1), Decimal("2100.00")), (date(2026, 12, 1), Decimal("3000.00"))],
        )

    def test_with_past_months_the_day_of_a_part_does_not_change(self):
        body = self.create(start="2026-09-01")
        body["parts"][0]["day"] = 7
        self.assert_errors(self.change(body), 400, "parts")
        self.assertEqual(self.entries()[0].date, date(2026, 9, 5))

    def test_a_new_part_starts_in_the_current_month(self):
        body = self.create(start="2026-09-01")
        parts = [
            {"id": part["id"], "day": part["day"], "amount": part["amount"]}
            for part in body["parts"]
        ]
        body = self.changed(body, parts=[*parts, {"day": 28, "amount": "150.00"}])
        self.assertEqual([part["day"] for part in body["parts"]], [5, 20, 28])
        self.assertEqual(Transaction.objects.get(amount="150.00").date, date(2026, 11, 28))

    def test_a_removed_part_without_a_past_month_is_deleted(self):
        body = self.create()
        body = self.changed(body, parts=[{**body["parts"][0]}])
        self.assertEqual([part["day"] for part in body["parts"]], [5])
        self.assertEqual(Transaction.objects.count(), 1)

    def test_a_removed_part_with_past_months_ends_and_keeps_them(self):
        body = self.create(start="2026-09-01")
        kept = body["parts"][0]
        body = self.changed(body, parts=[{"id": kept["id"], "day": 5, "amount": kept["amount"]}])
        self.assertEqual([part["day"] for part in body["parts"]], [5])
        ended = Transaction.objects.get(date=date(2026, 9, 20))
        self.assertEqual(ended.fixed_until, date(2026, 10, 31))

    def test_a_part_of_another_income_is_refused(self):
        other = self.create(name="Aluguel", parts=[{"day": 12, "amount": "900.00"}])
        body = self.create()
        stolen = {"id": other["parts"][0]["id"], "day": 12, "amount": "1.00"}
        self.assert_errors(self.change(body, parts=[stolen]), 400, "parts")

    def test_the_last_month_reaches_every_part(self):
        body = self.changed(self.create(), until="2027-03-01")
        self.assertEqual(body["until"], "2027-03-01")
        self.assertEqual({entry.fixed_until for entry in self.entries()}, {date(2027, 3, 1)})
        body = self.changed(body, until=None)
        self.assertEqual({entry.fixed_until for entry in self.entries()}, {None})

    def test_confirmation_turns_on_and_off(self):
        body = self.changed(self.create(), confirm=True)
        self.assertEqual({entry.requires_confirmation for entry in self.entries()}, {True})
        self.changed(body, confirm=False)
        self.assertEqual({entry.requires_confirmation for entry in self.entries()}, {False})


class DeleteIncomeTests(IncomeTestCase):
    def test_a_deleted_income_takes_its_entries(self):
        body = self.create()
        self.record()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.delete(f"{URL}/{body['id']}").status_code, 204)
        self.assertEqual(RecurringIncome.objects.count(), 0)
        self.assertEqual([entry.title for entry in self.entries()], ["Feira"])


class PartEntryTests(IncomeTestCase):
    """A part is an entry that the income controls."""

    def test_the_entry_is_locked_and_names_its_income(self):
        body = self.create()
        entry = self.get(f"/api/ledger/transactions/{body['parts'][0]['id']}").json()
        self.assertEqual((entry["locked"], entry["recurring_income_id"]), (True, body["id"]))
        plain = self.record()
        self.assertEqual((plain["locked"], plain["recurring_income_id"]), (False, None))

    def test_the_entry_is_not_changed_or_deleted_as_a_transaction(self):
        body = self.create()
        url = f"/api/ledger/transactions/{body['parts'][0]['id']}"
        self.assert_errors(self.put(url, self.entry()), 400, "__all__")
        self.assert_errors(self.delete(url), 400, "__all__")
        self.assertEqual(Transaction.objects.count(), 2)

    def test_the_months_of_a_part_stay_in_its_monthly_schedule(self):
        body = self.create()
        url = f"/api/ledger/transactions/{body['parts'][1]['id']}/schedule"
        self.assertEqual(self.get(url).status_code, 200)
