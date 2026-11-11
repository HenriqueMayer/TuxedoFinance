from decimal import Decimal

from banking.models import Bank, BankAccount, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from config.testing import ApiTestCase

PROGRAMS = "/api/loyalty/programs"


class LoyaltyTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        bank = Bank.objects.create(user=self.user, name="Nubank")
        self.account = BankAccount.objects.create(
            user=self.user,
            bank=bank,
            name="Conta",
            currency="BRL",
            opening_balance=Decimal("1000.00"),
        )

    def create(self, **changes):
        response = self.post(PROGRAMS, {"name": "Livelo", "unit_name": "pontos", **changes})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["id"]

    def program(self, pk):
        response = self.get(f"{PROGRAMS}/{pk}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def entry(self, pk, kind="EARNED", amount="1000", **changes):
        return self.post(f"{PROGRAMS}/{pk}/entries", {"kind": kind, "amount": amount, **changes})

    def earned(self, pk, amount="1000"):
        response = self.entry(pk, "EARNED", amount)
        self.assertEqual(response.status_code, 200, response.content)

    def redeem(self, pk, **changes):
        payload = {"points": "4000", "account_id": self.account.pk, "amount": "120.00", **changes}
        with self.captureOnCommitCallbacks(execute=True):
            return self.post(f"{PROGRAMS}/{pk}/redemptions", payload)

    def balance(self):
        wallet = self.get("/api/banking/wallet").json()
        return wallet["banks"][0]["accounts"][0]["balance"]


class ProgramTests(LoyaltyTestCase):
    def test_a_program_starts_empty_and_is_listed(self):
        pk = self.create()
        self.assertEqual(
            self.get(PROGRAMS).json(),
            [{"id": pk, "name": "Livelo", "unit_name": "pontos", "balance": "0.00"}],
        )
        self.assertEqual(self.program(pk)["entries"], [])

    def test_a_name_is_needed_and_is_not_repeated(self):
        self.assert_errors(self.post(PROGRAMS, {"name": " "}), 400, "name")
        self.create()
        self.assert_errors(self.post(PROGRAMS, {"name": "livelo"}), 400, "name")
        self.assertEqual(LoyaltyProgram.objects.count(), 1)

    def test_a_program_is_renamed_and_an_empty_one_is_deleted(self):
        pk = self.create()
        response = self.put(f"{PROGRAMS}/{pk}", {"name": "Smiles", "unit_name": "milhas"})
        self.assertEqual(response.status_code, 200, response.content)
        program = self.program(pk)
        self.assertEqual((program["name"], program["unit_name"]), ("Smiles", "milhas"))
        self.earned(pk)
        self.assertEqual(self.delete(f"{PROGRAMS}/{pk}").status_code, 400)
        entry = self.program(pk)["entries"][0]["id"]
        self.assertEqual(self.delete(f"/api/loyalty/entries/{entry}").status_code, 204)
        self.assertEqual(self.delete(f"{PROGRAMS}/{pk}").status_code, 204)
        self.assertEqual(self.get(PROGRAMS).json(), [])


class EntryTests(LoyaltyTestCase):
    def test_points_are_earned_used_and_expire(self):
        pk = self.create()
        self.earned(pk, "5000")
        self.assertEqual(self.entry(pk, "USED", "1200", notes="Passagem").status_code, 200)
        self.assertEqual(self.entry(pk, "EXPIRED", "300", date="2026-10-31").status_code, 200)
        program = self.program(pk)
        self.assertEqual(program["balance"], "3500.00")
        self.assertEqual(
            sorted((row["kind"], row["amount"], row["notes"]) for row in program["entries"]),
            [("EARNED", "5000.00", ""), ("EXPIRED", "300.00", ""), ("USED", "1200.00", "Passagem")],
        )
        self.assertTrue(all(row["undoable"] for row in program["entries"]))

    def test_points_cannot_leave_a_program_that_lacks_them(self):
        pk = self.create()
        self.earned(pk, "100")
        self.assert_errors(self.entry(pk, "USED", "100.01"), 400, "amount")
        self.assert_errors(self.entry(pk, "EXPIRED", "500"), 400, "amount")
        self.assert_errors(self.entry(pk, "EARNED", "0"), 400, "amount")
        self.assertEqual(self.program(pk)["balance"], "100.00")

    def test_an_entry_is_undone_unless_later_points_depend_on_it(self):
        pk = self.create()
        self.earned(pk, "1000")
        self.assertEqual(self.entry(pk, "USED", "800").status_code, 200)
        earned = next(row for row in self.program(pk)["entries"] if row["kind"] == "EARNED")
        used = next(row for row in self.program(pk)["entries"] if row["kind"] == "USED")
        self.assertEqual(self.delete(f"/api/loyalty/entries/{earned['id']}").status_code, 400)
        self.assertEqual(self.delete(f"/api/loyalty/entries/{used['id']}").status_code, 204)
        self.assertEqual(self.delete(f"/api/loyalty/entries/{earned['id']}").status_code, 204)
        self.assertEqual(self.program(pk)["balance"], "0.00")


class RedemptionTests(LoyaltyTestCase):
    def test_a_redemption_takes_points_and_adds_money_to_the_account(self):
        pk = self.create()
        self.earned(pk, "10000")
        response = self.redeem(pk)
        self.assertEqual(response.status_code, 200, response.content)
        program = self.program(pk)
        self.assertEqual(program["balance"], "6000.00")
        row = next(row for row in program["entries"] if row["kind"] == "REDEEMED")
        self.assertEqual(
            (row["amount"], row["cash_amount"], row["cash_currency"], row["account_name"]),
            ("4000.00", "120.00", "BRL", "Conta"),
        )
        self.assertEqual(self.balance(), "1120.00")

    def test_a_redemption_needs_the_points_and_an_own_account(self):
        pk = self.create()
        self.earned(pk, "1000")
        self.assert_errors(self.redeem(pk), 400, "points")
        self.assert_errors(self.redeem(pk, points="500", amount="0"), 400, "amount")
        bank = Bank.objects.create(user=self.other, name="Outro")
        foreign = BankAccount.objects.create(user=self.other, bank=bank, name="Conta")
        self.assert_errors(self.redeem(pk, points="500", account_id=foreign.pk), 400, "account_id")
        self.assertEqual(RewardRedemption.objects.count(), 0)
        self.assertEqual(self.balance(), "1000.00")

    def test_an_undone_redemption_returns_the_points_and_takes_the_money_back(self):
        pk = self.create()
        self.earned(pk, "10000")
        self.redeem(pk)
        row = next(row for row in self.program(pk)["entries"] if row["kind"] == "REDEEMED")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.delete(f"/api/loyalty/entries/{row['id']}")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self.program(pk)["balance"], "10000.00")
        self.assertEqual(self.balance(), "1000.00")
        self.assertEqual(RewardRedemption.objects.count(), 0)
        self.assertEqual(LoyaltyEntry.objects.count(), 1)


class OwnerTests(LoyaltyTestCase):
    def test_the_programs_of_another_owner_are_out_of_reach(self):
        foreign = LoyaltyProgram.objects.create(user=self.other, name="Alheio")
        entry = LoyaltyEntry.objects.create(
            user=self.other,
            program=foreign,
            direction="CREDIT",
            kind="ADJUSTMENT",
            amount=Decimal("10"),
            date="2026-11-01",
        )
        self.assertEqual(self.get(PROGRAMS).json(), [])
        path = f"{PROGRAMS}/{foreign.pk}"
        self.assertEqual(self.get(path).status_code, 404)
        self.assertEqual(self.put(path, {"name": "x"}).status_code, 404)
        self.assertEqual(self.delete(path).status_code, 404)
        self.assertEqual(self.entry(foreign.pk).status_code, 404)
        self.assertEqual(self.redeem(foreign.pk).status_code, 404)
        self.assertEqual(self.delete(f"/api/loyalty/entries/{entry.pk}").status_code, 404)


class SessionTests(ApiTestCase):
    signed_in = False

    def test_loyalty_needs_a_session(self):
        self.assertEqual(self.get(PROGRAMS).status_code, 401)
        self.assertEqual(self.post(PROGRAMS, {"name": "x"}).status_code, 401)
        self.assertEqual(self.get(f"{PROGRAMS}/1").status_code, 401)
        self.assertEqual(self.put(f"{PROGRAMS}/1", {"name": "x"}).status_code, 401)
        self.assertEqual(self.delete(f"{PROGRAMS}/1").status_code, 401)
        self.assertEqual(self.post(f"{PROGRAMS}/1/entries", {}).status_code, 401)
        self.assertEqual(self.post(f"{PROGRAMS}/1/redemptions", {}).status_code, 401)
        self.assertEqual(self.delete("/api/loyalty/entries/1").status_code, 401)
