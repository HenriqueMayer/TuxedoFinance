from datetime import date
from decimal import Decimal

from banking.models import BankAccount, ExchangeRate
from config.testing import ApiTestCase
from planning.models import SavedSheet
from reports.tests.test_api import TODAY, ReportsApiTestCase

FORECAST = "/api/plan/forecast"
SHEET = "/api/plan/sheet"
SHEETS = "/api/plan/sheets"


class SheetTestCase(ReportsApiTestCase):
    """Today is 2026-11-10. The account holds 1000.00. The sheet starts in November."""

    def forecast(self):
        response = self.get(FORECAST)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def sheet(self, changes=None, months=6):
        response = self.post(SHEET, {"months": months, "changes": changes or {}})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def row(self, sheet, label):
        return next(row for row in sheet["rows"] if row["label"] == label)

    def values(self, row):
        return [cell["value"] for cell in row["cells"]]

    def column(self, sheet, name):
        return [total[name] for total in sheet["totals"]]


class ForecastTests(SheetTestCase):
    def test_without_future_entries_the_balance_stays(self):
        forecast = self.forecast()
        self.assertEqual((forecast["currency"], forecast["opening_balance"]), ("BRL", "1000.00"))
        self.assertTrue(forecast["complete"])
        self.assertEqual(
            [total["month"] for total in forecast["months"]],
            ["2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"],
        )
        self.assertEqual(
            forecast["months"][0],
            {
                "month": "2026-11-01",
                "income": "0.00",
                "expenses": "0.00",
                "result": "0.00",
                "balance": "1000.00",
                "live_balance": "1000.00",
            },
        )
        self.assertEqual(forecast["months"][-1]["balance"], "1000.00")

    def test_repeating_entries_count_from_tomorrow_on(self):
        # The salary of November was paid on the 5th: it is in the balance already.
        self.record(
            title="Salário",
            amount="5000.00",
            transaction_type="INCOME",
            category_id=self.salary.pk,
            date="2026-11-05",
            is_fixed=True,
        )
        self.record(title="Aluguel", amount="1500.00", date="2026-11-20", is_fixed=True)
        sheet = self.sheet()
        self.assertEqual(sheet["opening_balance"], "6000.00")
        self.assertEqual(
            self.values(self.row(sheet, "Salário"))[:3], ["0.00", "5000.00", "5000.00"]
        )
        self.assertEqual(
            self.values(self.row(sheet, "Aluguel"))[:3], ["1500.00", "1500.00", "1500.00"]
        )
        self.assertEqual(self.column(sheet, "income")[:3], ["0.00", "5000.00", "5000.00"])
        self.assertEqual(self.column(sheet, "result")[:3], ["-1500.00", "3500.00", "3500.00"])
        self.assertEqual(self.column(sheet, "balance")[:3], ["4500.00", "8000.00", "11500.00"])
        salary = self.row(sheet, "Salário")
        self.assertEqual((salary["section"], salary["manual"]), ("income", False))
        self.assertRegex(salary["key"], r"^transaction:\d+$")

    def test_a_card_counts_when_its_invoice_is_paid(self):
        # The card closes on the 24th and its invoice is paid from the account on the 1st.
        self.record(
            title="Notebook", amount="900.00", instrument=f"credit:{self.card.pk}", installments=3
        )
        sheet = self.sheet()
        card = self.row(sheet, "Platinum")
        self.assertEqual(card["key"], f"card:{self.card.pk}")
        self.assertEqual(self.values(card)[:5], ["0.00", "300.00", "300.00", "300.00", "0.00"])
        self.assertEqual(
            self.column(sheet, "balance")[:4], ["1000.00", "700.00", "400.00", "100.00"]
        )

    def test_an_invoice_that_waits_for_its_payment_counts_on_its_due_date(self):
        self.record(amount="200.00", instrument=f"credit:{self.manual.pk}")
        sheet = self.sheet()
        self.assertEqual(self.values(self.row(sheet, "Black"))[:3], ["0.00", "200.00", "0.00"])

    def test_a_month_that_waits_for_confirmation_counts_in_the_current_month(self):
        self.set_today(date(2026, 10, 1))
        self.record(
            title="Academia",
            amount="100.00",
            date="2026-10-15",
            is_fixed=True,
            requires_confirmation=True,
        )
        self.set_today(TODAY)
        sheet = self.sheet()
        # October waits for confirmation and November falls on the 15th: both are still to pay.
        self.assertEqual(
            self.values(self.row(sheet, "Academia"))[:3], ["200.00", "100.00", "100.00"]
        )
        self.assertEqual(sheet["opening_balance"], "1000.00")

    def test_another_currency_needs_an_exchange_rate(self):
        dollars = BankAccount.objects.create(
            user=self.user,
            bank=self.account.bank,
            name="Dollars",
            currency="USD",
            opening_balance=Decimal("100.00"),
        )
        self.record(
            title="Hosting", amount="10.00", date="2026-11-20", instrument=f"account:{dollars.pk}"
        )
        forecast = self.forecast()
        self.assertEqual((forecast["complete"], forecast["missing_currencies"]), (False, ["USD"]))
        self.assertEqual(forecast["opening_balance"], "1000.00")
        ExchangeRate.objects.create(
            user=self.user,
            from_currency="USD",
            to_currency="BRL",
            rate=Decimal("5"),
            effective_date=date(2026, 11, 1),
        )
        forecast = self.forecast()
        self.assertTrue(forecast["complete"])
        self.assertEqual(forecast["opening_balance"], "1500.00")
        self.assertEqual(forecast["months"][0]["expenses"], "50.00")

    def test_twelve_months(self):
        sheet = self.sheet(months=12)
        self.assertEqual(len(sheet["totals"]), 12)
        self.assertEqual(sheet["totals"][-1]["month"], "2027-10-01")


class SheetChangeTests(SheetTestCase):
    def setUp(self):
        super().setUp()
        self.record(title="Aluguel", amount="1500.00", date="2026-11-20", is_fixed=True)
        self.rent = self.row(self.sheet(), "Aluguel")["key"]

    def test_a_changed_cell_replaces_the_recorded_value_in_the_sheet_only(self):
        sheet = self.sheet({"cells": {self.rent: {"2026-12": "1800.00", "2027-01": "0"}}})
        cells = self.row(sheet, "Aluguel")["cells"]
        self.assertEqual(
            cells[1],
            {"month": "2026-12-01", "live": "1500.00", "value": "1800.00", "changed": True},
        )
        self.assertEqual((cells[2]["value"], cells[2]["changed"]), ("0.00", True))
        self.assertEqual((cells[0]["value"], cells[0]["changed"]), ("1500.00", False))
        self.assertEqual(self.column(sheet, "balance")[:3], ["-500.00", "-2300.00", "-2300.00"])
        self.assertEqual(
            self.column(sheet, "live_balance")[:3], ["-500.00", "-2000.00", "-3500.00"]
        )
        # Nothing was recorded: the live sheet is as before.
        self.assertEqual(self.column(self.sheet(), "balance")[:2], ["-500.00", "-2000.00"])

    def test_a_manual_row_has_one_amount_for_each_month_and_cells_can_differ(self):
        changes = {
            "manual": [{"id": "a1", "label": "Bônus", "section": "income", "amount": "1000.00"}],
            "cells": {"manual:a1": {"2026-12": "2500.00"}},
        }
        sheet = self.sheet(changes)
        bonus = self.row(sheet, "Bônus")
        self.assertEqual(
            (bonus["key"], bonus["section"], bonus["manual"]), ("manual:a1", "income", True)
        )
        self.assertEqual(self.values(bonus)[:3], ["1000.00", "2500.00", "1000.00"])
        self.assertEqual(bonus["cells"][0]["live"], "0.00")
        self.assertEqual(self.column(sheet, "income")[:3], ["1000.00", "2500.00", "1000.00"])
        self.assertEqual(self.column(sheet, "balance")[:2], ["500.00", "1500.00"])

    def test_a_change_for_a_row_that_no_longer_exists_has_no_effect(self):
        sheet = self.sheet({"cells": {"transaction:999999": {"2026-12": "50.00"}}})
        self.assertEqual(len(sheet["rows"]), 1)
        self.assertEqual(self.column(sheet, "balance")[:2], ["-500.00", "-2000.00"])

    def test_wrong_changes_are_refused(self):
        wrong = (
            {"cells": {self.rent: {"2026-12": "-1.00"}}},
            {"cells": {self.rent: {"December": "1.00"}}},
            {"manual": [{"id": "a1", "label": " ", "section": "income"}]},
            {"manual": [{"id": "a1", "label": "x", "section": "savings"}]},
            {"manual": [{"id": "a1", "label": "x", "section": "income", "amount": "-5"}]},
            {
                "manual": [
                    {"id": f"m{number}", "label": "x", "section": "income"} for number in range(41)
                ]
            },
        )
        for changes in wrong:
            with self.subTest(changes=changes):
                response = self.post(SHEET, {"months": 6, "changes": changes})
                self.assertIn(response.status_code, (400, 422), response.content)
        self.assertEqual(self.post(SHEET, {"months": 7}).status_code, 422)


class SavedSheetTests(SheetTestCase):
    CHANGES = {
        "manual": [{"id": "a1", "label": "Bônus", "section": "income", "amount": "1000.00"}],
        "cells": {"manual:a1": {"2026-12": "2500.00"}},
    }

    def save(self, name="Mudança de emprego", **changes):
        return self.post(SHEETS, {"name": name, "months": 12, "changes": self.CHANGES, **changes})

    def test_a_sheet_is_saved_listed_changed_and_deleted(self):
        response = self.save()
        self.assertEqual(response.status_code, 200, response.content)
        pk = response.json()["id"]
        (listed,) = self.get(SHEETS).json()
        self.assertEqual((listed["id"], listed["name"]), (pk, "Mudança de emprego"))
        saved = self.get(f"{SHEETS}/{pk}").json()
        self.assertEqual((saved["name"], saved["months"]), ("Mudança de emprego", 12))
        self.assertEqual(saved["changes"]["cells"], {"manual:a1": {"2026-12": "2500.00"}})
        self.assertEqual(saved["changes"]["manual"][0]["label"], "Bônus")
        # The saved changes compose with the records of today.
        self.assertEqual(self.sheet(saved["changes"])["totals"][1]["income"], "2500.00")

        response = self.put(f"{SHEETS}/{pk}", {"name": "Plano B", "months": 6, "changes": {}})
        self.assertEqual(response.status_code, 200, response.content)
        saved = self.get(f"{SHEETS}/{pk}").json()
        self.assertEqual((saved["name"], saved["months"]), ("Plano B", 6))
        self.assertEqual(saved["changes"], {"cells": {}, "manual": []})
        self.assertEqual(self.delete(f"{SHEETS}/{pk}").status_code, 204)
        self.assertEqual(self.get(SHEETS).json(), [])

    def test_a_name_is_needed_and_is_not_repeated(self):
        self.assert_errors(self.save(name="  "), 400, "name")
        self.assertEqual(self.save().status_code, 200)
        self.assert_errors(self.save(name="mudança de emprego"), 400, "name")
        self.assertEqual(SavedSheet.objects.count(), 1)

    def test_the_sheets_of_another_owner_are_out_of_reach(self):
        foreign = SavedSheet.objects.create(user=self.other, name="Alheia", changes={})
        self.assertEqual(self.get(SHEETS).json(), [])
        self.assertEqual(self.get(f"{SHEETS}/{foreign.pk}").status_code, 404)
        self.assertEqual(
            self.put(f"{SHEETS}/{foreign.pk}", {"name": "x", "changes": {}}).status_code, 404
        )
        self.assertEqual(self.delete(f"{SHEETS}/{foreign.pk}").status_code, 404)


class SessionTests(ApiTestCase):
    signed_in = False

    def test_the_sheet_needs_a_session(self):
        self.assertEqual(self.get(FORECAST).status_code, 401)
        self.assertEqual(self.post(SHEET, {}).status_code, 401)
        self.assertEqual(self.get(SHEETS).status_code, 401)
        self.assertEqual(self.post(SHEETS, {"name": "x"}).status_code, 401)
        self.assertEqual(self.get(f"{SHEETS}/1").status_code, 401)
        self.assertEqual(self.put(f"{SHEETS}/1", {"name": "x"}).status_code, 401)
        self.assertEqual(self.delete(f"{SHEETS}/1").status_code, 401)
