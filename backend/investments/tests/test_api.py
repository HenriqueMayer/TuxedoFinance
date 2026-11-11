from datetime import date
from decimal import Decimal
from unittest.mock import patch

from banking.models import Bank, BankAccount, BankMovement
from banking.services import account_balance
from config.testing import ApiTestCase
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation

TODAY = date(2026, 11, 10)
URL = "/api/investments"


class InvestmentApiTestCase(ApiTestCase):
    """One owner with an account of 1,000.00; today is fixed."""

    def setUp(self):
        super().setUp()
        clock = patch("django.utils.timezone.localdate", return_value=TODAY)
        clock.start()
        self.addCleanup(clock.stop)
        self.bank = Bank.objects.create(user=self.user, name="Nubank")
        self.account = BankAccount.objects.create(
            user=self.user,
            bank=self.bank,
            name="Conta",
            currency="BRL",
            opening_balance=Decimal("1000.00"),
            opening_date=date(2026, 1, 1),
        )

    def create(self, **changes):
        payload = {"name": "Reserva", "institution_id": self.bank.pk, "currency": "BRL", **changes}
        return self.post(f"{URL}/positions", payload)

    def position(self, **changes):
        response = self.create(**changes)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["id"]

    def operate(self, position, kind="DEPOSIT", **changes):
        payload = {"kind": kind, "account_id": self.account.pk, **changes}
        return self.post(f"{URL}/positions/{position}/operations", payload)

    def read(self, position):
        response = self.get(f"{URL}/positions/{position}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def overview(self):
        response = self.get(f"{URL}/positions")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class CreatePositionTests(InvestmentApiTestCase):
    def test_a_position_without_a_balance_is_listed_at_zero(self):
        position = self.position()
        row = self.overview()["positions"][0]
        self.assertEqual(
            (row["id"], row["name"], row["institution_name"], row["value"], row["valuation_mode"]),
            (position, "Reserva", "Nubank", "0.00", "MONETARY"),
        )
        self.assertEqual(self.overview()["total"], "0.00")

    def test_an_opening_balance_counts_and_moves_no_money(self):
        self.position(opening_balance="2500.00")
        self.assertEqual(self.overview()["total"], "2500.00")
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))
        self.assertEqual(Asset.objects.get().opening_date, TODAY)

    def test_an_opening_in_units_is_quantity_times_price(self):
        position = self.position(
            name="Tesouro",
            valuation_mode="UNITS",
            opening_quantity="2",
            opening_unit_price="150.50",
            opening_date="2026-10-01",
        )
        row = self.read(position)
        self.assertEqual((row["value"], row["cost"]), ("301.00", "301.00"))
        self.assertEqual(Decimal(row["quantity"]), Decimal("2"))
        self.assertFalse(row["has_price"])
        self.assertEqual(row["opening"]["date"], "2026-10-01")

    def test_a_typed_institution_is_created_or_reused(self):
        self.position(name="CDB", institution_id=None, institution_name="XP")
        self.position(name="LCI", institution_id=None, institution_name="xp")
        self.position(name="Caixinha", institution_id=None, institution_name="nubank")
        self.assertEqual(Bank.objects.filter(user=self.user).count(), 2)
        self.assertEqual(InvestmentProduct.objects.filter(bank=self.bank).count(), 1)

    def test_invalid_values_are_field_errors(self):
        self.assert_errors(self.create(name=" "), 400, "name")
        self.assert_errors(self.create(institution_id=None), 400, "institution_name")
        self.assert_errors(
            self.create(valuation_mode="UNITS", opening_quantity="2"),
            400,
            "opening_quantity",
            "opening_unit_price",
        )
        self.position()
        self.assert_errors(self.create(), 400, "name")
        self.assertEqual(Asset.objects.count(), 1)

    def test_another_owners_institution_is_refused(self):
        foreign = Bank.objects.create(user=self.other, name="Other")
        self.assert_errors(self.create(institution_id=foreign.pk), 400, "institution_id")


class OperationTests(InvestmentApiTestCase):
    def test_a_deposit_leaves_the_account_and_enters_the_position(self):
        position = self.position()
        response = self.operate(position, amount="300.00")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(account_balance(self.account), Decimal("700.00"))
        row = self.read(position)
        self.assertEqual(row["value"], "300.00")
        self.assertEqual(
            [(item["kind"], item["value"], item["account_name"]) for item in row["operations"]],
            [("DEPOSIT", "300.00", "Conta")],
        )
        self.assertEqual(BankMovement.objects.get().kind, BankMovement.Kind.INVESTMENT)

    def test_a_withdrawal_returns_to_the_account_and_cannot_exceed_the_position(self):
        position = self.position(opening_balance="500.00")
        self.assert_errors(self.operate(position, "WITHDRAWAL", amount="600.00"), 400, "amount")
        response = self.operate(position, "WITHDRAWAL", amount="200.00")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(account_balance(self.account), Decimal("1200.00"))
        self.assertEqual(self.read(position)["value"], "300.00")

    def test_a_yield_changes_the_position_and_not_the_account(self):
        position = self.position(opening_balance="500.00")
        response = self.operate(position, "YIELD", amount="12.34", account_id=None)
        self.assertEqual(response.status_code, 200, response.content)
        row = self.read(position)
        self.assertEqual((row["value"], row["yields"]), ("512.34", "12.34"))
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))

    def test_units_use_quantity_and_price_and_the_cash_that_moved(self):
        position = self.position(name="Ações", valuation_mode="UNITS")
        self.operate(position, quantity="3", unit_price="100.00", cash_amount="301.50")
        self.assertEqual(account_balance(self.account), Decimal("698.50"))
        self.operate(position, "WITHDRAWAL", quantity="1", unit_price="130.00")
        self.assertEqual(account_balance(self.account), Decimal("828.50"))
        row = self.read(position)
        self.assertEqual((Decimal(row["quantity"]), row["cost"]), (Decimal("2"), "200.00"))
        self.assert_errors(
            self.operate(position, "WITHDRAWAL", quantity="5", unit_price="130.00"),
            400,
            "quantity",
        )

    def test_a_deposit_and_a_withdrawal_need_an_own_account(self):
        position = self.position()
        self.assert_errors(
            self.operate(position, amount="10.00", account_id=None), 400, "account_id"
        )
        foreign_bank = Bank.objects.create(user=self.other, name="Other")
        foreign = BankAccount.objects.create(user=self.other, bank=foreign_bank, name="Other")
        self.assert_errors(
            self.operate(position, amount="10.00", account_id=foreign.pk), 400, "account_id"
        )
        self.assert_errors(self.operate(position, amount="0"), 400, "amount")
        self.assertFalse(Investment.objects.exists())

    def test_deleting_an_operation_returns_the_money(self):
        position = self.position()
        operation = self.operate(position, amount="300.00").json()["id"]
        self.assertEqual(self.delete(f"{URL}/operations/{operation}").status_code, 204)
        self.assertEqual(account_balance(self.account), Decimal("1000.00"))
        self.assertEqual(self.read(position)["value"], "0.00")
        self.assertFalse(BankMovement.objects.exists())

    def test_a_deposit_that_a_later_withdrawal_needs_cannot_be_deleted(self):
        position = self.position()
        deposit = self.operate(position, amount="300.00", date="2026-11-01").json()["id"]
        self.operate(position, "WITHDRAWAL", amount="300.00", date="2026-11-05")
        self.assert_errors(self.delete(f"{URL}/operations/{deposit}"), 400, "date")
        self.assertEqual(Investment.objects.count(), 2)

    def test_an_archived_position_accepts_no_operation(self):
        position = self.position()
        self.put(f"{URL}/positions/{position}", {"name": "Reserva", "is_archived": True})
        self.assert_errors(self.operate(position, amount="10.00"), 400, "__all__")


class CurrentValueTests(InvestmentApiTestCase):
    def value(self, position, value):
        return self.post(f"{URL}/positions/{position}/value", {"value": value})

    def test_a_higher_balance_becomes_a_yield_of_the_difference(self):
        position = self.position(opening_balance="500.00", opening_date="2026-10-01")
        self.assertEqual(self.value(position, "512.34").status_code, 200)
        operation = Investment.objects.get()
        self.assertEqual(
            (operation.kind, operation.amount, operation.date), ("YIELD", Decimal("12.34"), TODAY)
        )
        self.assertEqual(self.read(position)["value"], "512.34")
        # The same balance again records nothing.
        self.assertEqual(self.value(position, "512.34").status_code, 200)
        self.assertEqual(Investment.objects.count(), 1)

    def test_a_lower_balance_is_refused_because_it_is_a_withdrawal(self):
        position = self.position(opening_balance="500.00")
        self.assert_errors(self.value(position, "400.00"), 400, "value")
        self.assert_errors(self.value(position, "0"), 400, "value")
        self.assertFalse(Investment.objects.exists())

    def test_for_units_the_value_is_the_price_of_today(self):
        position = self.position(
            name="Ações", valuation_mode="UNITS", opening_quantity="2", opening_unit_price="100"
        )
        self.assertEqual(self.value(position, "150").status_code, 200)
        self.assertEqual(self.value(position, "160").status_code, 200)
        self.assertEqual(PriceObservation.objects.get().unit_price, Decimal("160"))
        row = self.read(position)
        self.assertEqual((row["value"], row["cost"], row["gain"]), ("320.00", "200.00", "120.00"))
        self.assertTrue(row["has_price"])
        self.assertEqual(row["price_date"], "2026-11-10")
        self.assertFalse(Investment.objects.exists())


class PositionMaintenanceTests(InvestmentApiTestCase):
    def test_rename_and_archive(self):
        position = self.position()
        response = self.put(
            f"{URL}/positions/{position}", {"name": "Caixinha", "is_archived": True}
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = self.read(position)
        self.assertEqual((row["name"], row["is_archived"]), ("Caixinha", True))
        self.assertEqual(InvestmentProduct.objects.get().name, "Caixinha")
        self.assert_errors(self.put(f"{URL}/positions/{position}", {"name": ""}), 400, "name")

    def test_a_position_without_operations_is_deleted_with_its_product(self):
        position = self.position(opening_balance="500.00")
        self.assertEqual(self.delete(f"{URL}/positions/{position}").status_code, 204)
        self.assertFalse(Asset.objects.exists())
        self.assertFalse(InvestmentProduct.objects.exists())
        self.assertTrue(Bank.objects.filter(pk=self.bank.pk).exists())

    def test_a_position_with_operations_is_not_deleted(self):
        position = self.position()
        self.operate(position, amount="300.00")
        self.assert_errors(self.delete(f"{URL}/positions/{position}"), 400, "__all__")
        self.assertTrue(Asset.objects.exists())

    def test_the_total_is_in_the_base_currency_and_names_a_missing_rate(self):
        self.position(opening_balance="500.00")
        self.position(name="Dollars", currency="USD", opening_balance="100.00")
        overview = self.overview()
        self.assertEqual((overview["currency"], overview["total"]), ("BRL", "500.00"))
        self.assertFalse(overview["complete"])
        self.assertEqual(overview["missing_currencies"], ["USD"])
        dollars = next(row for row in overview["positions"] if row["name"] == "Dollars")
        self.assertEqual((dollars["value"], dollars["base_value"]), ("100.00", None))


class AccessTests(InvestmentApiTestCase):
    def test_every_operation_is_the_owners_only(self):
        position = self.position(opening_balance="500.00")
        operation = self.operate(position, amount="100.00").json()["id"]
        self.client.force_login(self.other)
        self.assertEqual(self.overview()["positions"], [])
        self.assertEqual(self.get(f"{URL}/positions/{position}").status_code, 404)
        self.assertEqual(self.put(f"{URL}/positions/{position}", {"name": "Mine"}).status_code, 404)
        self.assertEqual(self.delete(f"{URL}/positions/{position}").status_code, 404)
        self.assertEqual(
            self.post(f"{URL}/positions/{position}/value", {"value": "900"}).status_code, 404
        )
        self.assertEqual(self.operate(position, amount="1.00").status_code, 404)
        self.assertEqual(self.delete(f"{URL}/operations/{operation}").status_code, 404)
        self.assertEqual(Investment.objects.count(), 1)
        self.assertEqual(Asset.objects.get().name, "Reserva")


class SessionTests(InvestmentApiTestCase):
    signed_in = False

    def test_every_operation_needs_a_session(self):
        for method, path in (
            ("get", f"{URL}/positions"),
            ("post", f"{URL}/positions"),
            ("get", f"{URL}/positions/1"),
            ("put", f"{URL}/positions/1"),
            ("delete", f"{URL}/positions/1"),
            ("post", f"{URL}/positions/1/value"),
            ("post", f"{URL}/positions/1/operations"),
            ("delete", f"{URL}/operations/1"),
        ):
            with self.subTest(method=method, path=path):
                response = self.get(path) if method == "get" else self.send(method, path)
                self.assertEqual(response.status_code, 401)
