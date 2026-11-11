"""Difference rule and adjustment services of balance checks (R8).

Worked example (synthetic): opening balance BRL 1,000.00 on 2026-10-01,
-200.00 on 10-05, +3,000.00 on 10-31 and -50.00 on 11-02. A check on 10-31
with a statement balance of 3,780.00 has a tracked balance of 3,800.00 and a
difference of -20.00. Its adjustment is a DEBIT of 20.00 on 10-31. Then the
difference is 0.00 and the balance on 11-03 is 3,730.00. A check on 11-02 with
3,730.00 has a difference of 0.00. Removing the 10-31 adjustment gives -20.00
for both checks.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from banking import reconciliation
from banking.models import BalanceCheckpoint, BankAccount, BankMovement
from banking.reconciliation import (
    AlreadyAdjusted,
    NoDifference,
    StaleDifference,
    delete_checkpoint,
    latest_statuses,
    record_adjustment,
    remove_adjustment,
    save_checkpoint,
    statuses,
)
from banking.services import account_balance, create_movement
from banking.tests.factories import make_account

TODAY = date(2026, 11, 3)
D = Decimal


class ReconciliationCase(TestCase):
    def setUp(self):
        clock = patch("django.utils.timezone.localdate", return_value=TODAY)
        clock.start()
        self.addCleanup(clock.stop)
        self.user = get_user_model().objects.create_user("reconciliation-owner")
        self.account = make_account(self.user, opening="1000.00")
        self.account.opening_date = date(2026, 10, 1)
        self.account.save()

    def move(self, amount, on, account=None, user=None):
        amount = D(amount)
        return create_movement(
            user=user or self.user,
            account=account or self.account,
            direction=BankMovement.Direction.CREDIT if amount > 0 else BankMovement.Direction.DEBIT,
            kind=BankMovement.Kind.INCOME if amount > 0 else BankMovement.Kind.EXPENSE,
            amount=abs(amount),
            effective_date=on,
        )

    def worked_example(self):
        self.move("-200.00", date(2026, 10, 5))
        self.move("3000.00", date(2026, 10, 31))
        self.move("-50.00", date(2026, 11, 2))

    def check(self, on, balance, account=None, note=""):
        return save_checkpoint(
            user=self.user,
            account=account or self.account,
            date=on,
            statement_balance=D(balance),
            note=note,
        )


class WorkedExampleTests(ReconciliationCase):
    def test_worked_example_records_and_removes_the_adjustment(self):
        self.worked_example()
        october = self.check(date(2026, 10, 31), "3780.00")
        self.assertEqual(reconciliation.tracked(self.account, october.date), D("3800.00"))
        self.assertEqual(reconciliation.difference(october), D("-20.00"))
        self.assertEqual(october.checked_difference, D("-20.00"))

        movement = record_adjustment(
            user=self.user, checkpoint_id=october.pk, expected_difference=D("-20.00")
        )
        self.assertEqual(
            (movement.direction, movement.kind, movement.amount, movement.effective_date),
            ("DEBIT", "ADJUSTMENT", D("20.00"), date(2026, 10, 31)),
        )
        self.assertEqual(
            (movement.source_key, movement.description), (f"checkpoint:{october.pk}", "")
        )
        self.assertIsNone(movement.invoice_id)
        october.refresh_from_db()
        self.assertEqual(october.adjustment_id, movement.pk)
        self.assertEqual(october.checked_difference, D("0.00"))
        self.assertEqual(reconciliation.difference(october), D("0.00"))
        self.assertEqual(account_balance(self.account, TODAY), D("3730.00"))

        november = self.check(date(2026, 11, 2), "3730.00")
        self.assertEqual(reconciliation.difference(november), D("0.00"))

        self.assertEqual(remove_adjustment(user=self.user, checkpoint_id=october.pk), D("-20.00"))
        self.assertFalse(BankMovement.objects.filter(pk=movement.pk).exists())
        october.refresh_from_db()
        self.assertIsNone(october.adjustment_id)
        self.assertEqual(october.checked_difference, D("-20.00"))
        self.assertEqual(reconciliation.difference(october), D("-20.00"))
        self.assertEqual(reconciliation.difference(november), D("-20.00"))

    def test_positive_difference_records_a_credit(self):
        self.worked_example()
        checkpoint = self.check(date(2026, 10, 31), "3812.34")
        movement = record_adjustment(
            user=self.user, checkpoint_id=checkpoint.pk, expected_difference=D("12.34")
        )
        self.assertEqual((movement.direction, movement.amount), ("CREDIT", D("12.34")))

    def test_negative_statement_balance_is_valid(self):
        checkpoint = self.check(date(2026, 10, 2), "-150.00")
        self.assertEqual(reconciliation.difference(checkpoint), D("-1150.00"))

    def test_manual_obligations_and_future_rows_are_not_in_the_tracked_balance(self):
        self.worked_example()
        # A derived row dated after the check date is a projection for that date.
        self.move("-999.00", date(2026, 11, 20))
        checkpoint = self.check(date(2026, 11, 2), "3750.00")
        self.assertEqual(reconciliation.tracked(self.account, checkpoint.date), D("3750.00"))
        self.assertEqual(reconciliation.difference(checkpoint), D("0.00"))


class BatchReadTests(ReconciliationCase):
    def test_statuses_and_latest_statuses_equal_account_balance(self):
        self.worked_example()
        other = make_account(self.user, name="Savings", opening="50.00")
        self.move("25.00", date(2026, 10, 10), account=other)
        rows = [
            self.check(date(2026, 10, 1), "1000.00"),
            self.check(date(2026, 10, 5), "790.00"),
            self.check(date(2026, 10, 31), "3780.00"),
            self.check(date(2026, 11, 3), "3750.00"),
            self.check(date(2026, 10, 9), "50.00", account=other),
            self.check(date(2026, 10, 10), "80.00", account=other),
        ]
        record_adjustment(user=self.user, checkpoint_id=rows[2].pk, expected_difference=D("-20.00"))
        for account in (self.account, other):
            ordered = BalanceCheckpoint.objects.filter(account=account)
            for status in statuses(account, ordered):
                with self.subTest(account=account.name, date=status.checkpoint.date):
                    expected = account_balance(account, status.checkpoint.date)
                    self.assertEqual(status.tracked, expected)
                    self.assertEqual(
                        status.difference, status.checkpoint.statement_balance - expected
                    )
        latest = latest_statuses(self.user, [self.account.pk, other.pk])
        self.assertEqual(latest[self.account.pk].checkpoint.date, date(2026, 11, 3))
        self.assertEqual(
            latest[self.account.pk].tracked, account_balance(self.account, date(2026, 11, 3))
        )
        self.assertEqual(latest[other.pk].checkpoint.date, date(2026, 10, 10))
        self.assertEqual(latest[other.pk].difference, D("5.00"))

    def test_latest_statuses_uses_two_queries_and_skips_accounts_without_checks(self):
        self.worked_example()
        empty = make_account(self.user, name="Empty")
        self.check(date(2026, 10, 31), "3780.00")
        with self.assertNumQueries(2):
            result = latest_statuses(self.user, [self.account.pk, empty.pk])
        self.assertEqual(set(result), {self.account.pk})
        self.assertEqual(latest_statuses(self.user, []), {})

    def test_latest_statuses_ignores_another_owner(self):
        other_user = get_user_model().objects.create_user("reconciliation-other")
        other = make_account(other_user, bank_name="Other bank")
        BalanceCheckpoint.objects.create(
            user=other_user, account=other, date=date(2026, 10, 1), statement_balance=D("1.00")
        )
        self.assertEqual(latest_statuses(self.user, [other.pk]), {})

    def test_sums_with_more_decimal_places_still_give_a_valid_adjustment(self):
        # SQLite sums can return a value such as Decimal('44569.1000000000').
        for amount in ("0.10", "0.20", "39.90", "44529.00"):
            self.move(amount, date(2026, 10, 2))
        checkpoint = self.check(date(2026, 10, 2), "100.00")
        current = reconciliation.difference(checkpoint)
        self.assertEqual(current.as_tuple().exponent, -2)
        (status,) = statuses(self.account, [checkpoint])
        self.assertEqual(str(status.tracked), "45569.20")
        movement = record_adjustment(
            user=self.user, checkpoint_id=checkpoint.pk, expected_difference=current
        )
        self.assertEqual(movement.amount, D("45469.20"))

    def test_undated_opening_balance_applies_on_every_date(self):
        legacy = make_account(self.user, name="Legacy", opening="300.00")
        checkpoint = self.check(date(2020, 1, 1), "300.00", account=legacy)
        (status,) = statuses(legacy, [checkpoint])
        self.assertEqual(status.difference, D("0.00"))
        self.assertTrue(status.opening_date_unknown)
        (dated,) = statuses(self.account, [self.check(date(2026, 10, 1), "1000.00")])
        self.assertFalse(dated.opening_date_unknown)


class AdjustmentGuardTests(ReconciliationCase):
    def setUp(self):
        super().setUp()
        self.worked_example()
        self.checkpoint = self.check(date(2026, 10, 31), "3780.00")

    def adjustments(self):
        return BankMovement.objects.filter(kind=BankMovement.Kind.ADJUSTMENT).count()

    def test_stale_expected_difference_writes_nothing(self):
        for expected in (D("-19.99"), None):
            with self.subTest(expected=expected), self.assertRaises(StaleDifference) as caught:
                record_adjustment(
                    user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=expected
                )
            self.assertEqual(caught.exception.current, D("-20.00"))
        self.assertEqual(self.adjustments(), 0)

    def test_parse_expected_refuses_text(self):
        self.assertEqual(reconciliation.parse_expected("-20.00"), D("-20.00"))
        for value in ("abc", "", "NaN", "Infinity", "1,5"):
            with self.subTest(value=value):
                self.assertIsNone(reconciliation.parse_expected(value))

    def test_zero_difference_needs_no_adjustment(self):
        zero = self.check(date(2026, 11, 2), "3750.00")
        with self.assertRaises(NoDifference):
            record_adjustment(user=self.user, checkpoint_id=zero.pk, expected_difference=D("0.00"))
        self.assertEqual(self.adjustments(), 0)

    def test_double_record_creates_one_movement(self):
        record_adjustment(
            user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-20.00")
        )
        with self.assertRaises(AlreadyAdjusted):
            record_adjustment(
                user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("0.00")
            )
        self.assertEqual(self.adjustments(), 1)

    def test_existing_source_key_or_integrity_error_is_already_adjusted(self):
        BankMovement.objects.create(
            user=self.user,
            account=self.account,
            direction="DEBIT",
            kind="ADJUSTMENT",
            amount=D("1.00"),
            effective_date=date(2026, 9, 1),
            source_key=f"checkpoint:{self.checkpoint.pk}",
        )
        with self.assertRaises(AlreadyAdjusted):
            record_adjustment(
                user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-19.00")
            )
        BankMovement.objects.filter(source_key=f"checkpoint:{self.checkpoint.pk}").delete()
        with (
            patch("banking.reconciliation.create_movement", side_effect=IntegrityError("unique")),
            self.assertRaises(AlreadyAdjusted),
        ):
            record_adjustment(
                user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-20.00")
            )
        self.assertEqual(self.adjustments(), 0)

    def test_overflow_is_a_validation_error(self):
        BalanceCheckpoint.objects.filter(pk=self.checkpoint.pk).update(
            statement_balance=D("-99999999999990.00")
        )
        self.checkpoint.refresh_from_db()
        current = reconciliation.difference(self.checkpoint)
        self.assertEqual(len(str(abs(current)).replace(".", "")), 17)
        with self.assertRaisesMessage(
            ValidationError, "The difference is too large for an adjustment."
        ):
            record_adjustment(
                user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=current
            )
        self.assertEqual(self.adjustments(), 0)

    def test_foreign_movement_on_the_account_refuses_the_adjustment(self):
        stranger = get_user_model().objects.create_user("reconciliation-stranger")
        BankMovement.objects.create(
            user=stranger,
            account=self.account,
            direction="CREDIT",
            kind="INCOME",
            amount=D("1.00"),
            effective_date=date(2026, 10, 2),
        )
        with self.assertRaises(ValidationError):
            record_adjustment(
                user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-21.00")
            )
        self.assertEqual(self.adjustments(), 0)

    def test_services_refuse_another_owner(self):
        stranger = get_user_model().objects.create_user("reconciliation-intruder")
        for service in (
            lambda: record_adjustment(
                user=stranger, checkpoint_id=self.checkpoint.pk, expected_difference=D("-20.00")
            ),
            lambda: remove_adjustment(user=stranger, checkpoint_id=self.checkpoint.pk),
            lambda: delete_checkpoint(user=stranger, checkpoint_id=self.checkpoint.pk),
        ):
            with self.assertRaises(BalanceCheckpoint.DoesNotExist):
                service()
        self.assertTrue(BalanceCheckpoint.objects.filter(pk=self.checkpoint.pk).exists())

    def test_statement_match_blocks_removal(self):
        from ledger.statements import ImportBatch, ImportedRow

        movement = record_adjustment(
            user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-20.00")
        )
        batch = ImportBatch.objects.create(
            user=self.user,
            account=self.account,
            file_name="s.csv",
            file_hash="0" * 64,
            file_format="CSV",
            raw_text="",
        )
        ImportedRow.objects.create(
            batch=batch,
            number=1,
            date=date(2026, 10, 31),
            amount=D("-20.00"),
            description="Fee",
            currency="BRL",
            matched_movement=movement,
        )
        message = "This adjustment is linked to a bank statement import. Resolve the import before removing it."
        for service in (remove_adjustment, delete_checkpoint):
            with (
                self.subTest(service=service.__name__),
                self.assertRaisesMessage(ValidationError, message),
            ):
                service(user=self.user, checkpoint_id=self.checkpoint.pk)
        self.assertTrue(BankMovement.objects.filter(pk=movement.pk).exists())

    def test_mismatched_link_is_refused_and_deletes_nothing(self):
        movement = record_adjustment(
            user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-20.00")
        )
        BankMovement.objects.filter(pk=movement.pk).update(source_key="checkpoint:999999")
        with self.assertRaisesMessage(
            ValidationError, "The adjustment movement does not match this balance check."
        ):
            remove_adjustment(user=self.user, checkpoint_id=self.checkpoint.pk)
        self.assertTrue(BankMovement.objects.filter(pk=movement.pk).exists())

    def test_delete_checkpoint_removes_its_adjustment(self):
        movement = record_adjustment(
            user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-20.00")
        )
        delete_checkpoint(user=self.user, checkpoint_id=self.checkpoint.pk)
        self.assertFalse(BalanceCheckpoint.objects.filter(pk=self.checkpoint.pk).exists())
        self.assertFalse(BankMovement.objects.filter(pk=movement.pk).exists())

    def test_date_or_balance_cannot_change_while_adjusted(self):
        record_adjustment(
            user=self.user, checkpoint_id=self.checkpoint.pk, expected_difference=D("-20.00")
        )
        message = "Remove the adjustment to change the date or the statement balance."
        for values in (
            {"date": date(2026, 10, 30), "statement_balance": D("3780.00")},
            {"date": date(2026, 10, 31), "statement_balance": D("3781.00")},
        ):
            with self.subTest(values=values), self.assertRaisesMessage(ValidationError, message):
                save_checkpoint(
                    user=self.user, account=self.account, checkpoint=self.checkpoint, **values
                )
        saved = save_checkpoint(
            user=self.user,
            account=self.account,
            checkpoint=self.checkpoint,
            date=date(2026, 10, 31),
            statement_balance=D("3780.00"),
            note="Bank app",
        )
        self.assertEqual(saved.note, "Bank app")
        self.assertEqual(saved.checked_difference, D("0.00"))


class BaselineTests(ReconciliationCase):
    def status(self, checkpoint):
        checkpoint.refresh_from_db()
        return statuses(self.account, [checkpoint])[0]

    def test_a_later_edit_changes_the_difference_and_shows_the_time(self):
        self.worked_example()
        checkpoint = self.check(date(2026, 10, 31), "3780.00")
        self.assertFalse(self.status(checkpoint).changed)
        self.assertIsNone(self.status(checkpoint).last_change)
        movement = BankMovement.objects.get(amount=D("200.00"))
        movement.amount = D("210.00")
        movement.save()
        status = self.status(checkpoint)
        self.assertTrue(status.changed)
        self.assertEqual(status.difference, D("-10.00"))
        self.assertEqual(status.checkpoint.checked_difference, D("-20.00"))
        movement.refresh_from_db()
        self.assertEqual(status.last_change, movement.updated_at)
        self.assertEqual(status.last_change_on, timezone.localtime(movement.updated_at).date())

    def test_a_deleted_movement_shows_a_change_without_a_time(self):
        self.worked_example()
        checkpoint = self.check(date(2026, 10, 31), "3780.00")
        BankMovement.objects.get(amount=D("200.00")).delete()
        status = self.status(checkpoint)
        self.assertTrue(status.changed)
        self.assertIsNone(status.last_change)

    def test_a_later_movement_after_the_date_is_not_a_change(self):
        checkpoint = self.check(date(2026, 10, 5), "1000.00")
        self.move("5.00", date(2026, 10, 6))
        self.assertFalse(self.status(checkpoint).changed)

    def test_baseline_is_taken_on_edit_of_date_or_balance(self):
        self.worked_example()
        checkpoint = self.check(date(2026, 10, 31), "3780.00")
        first = checkpoint.checked_at
        self.move("-10.00", date(2026, 10, 20))
        checkpoint = save_checkpoint(
            user=self.user,
            account=self.account,
            checkpoint=checkpoint,
            date=checkpoint.date,
            statement_balance=D("3780.00"),
            note="Only the note",
        )
        self.assertEqual(
            (checkpoint.checked_difference, checkpoint.checked_at), (D("-20.00"), first)
        )
        checkpoint = save_checkpoint(
            user=self.user,
            account=self.account,
            checkpoint=checkpoint,
            date=checkpoint.date,
            statement_balance=D("3790.00"),
            note="",
        )
        self.assertEqual(checkpoint.checked_difference, D("0.00"))
        self.assertGreaterEqual(checkpoint.checked_at, first)

    def test_save_checkpoint_never_creates_a_movement(self):
        before = BankMovement.objects.count()
        checkpoint = self.check(date(2026, 10, 31), "1.00")
        save_checkpoint(
            user=self.user,
            account=self.account,
            checkpoint=checkpoint,
            date=date(2026, 10, 30),
            statement_balance=D("2.00"),
            note="",
        )
        self.assertEqual(BankMovement.objects.count(), before)

    def test_save_checkpoint_validates_the_model(self):
        with self.assertRaises(ValidationError) as caught:
            self.check(TODAY + timedelta(days=1), "1.00")
        self.assertIn("date", caught.exception.error_dict)
        self.assertFalse(BalanceCheckpoint.objects.exists())
        self.assertIsInstance(self.account, BankAccount)
