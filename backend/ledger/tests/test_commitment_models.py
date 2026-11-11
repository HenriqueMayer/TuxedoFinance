"""R4 models: database constraints, validation rules and deletion (transactions/models.py).

Each constraint has a test that bypasses ``full_clean`` and expects an
``IntegrityError``. The first-day rule of months has no database check
(SQLite would need a Python function for it), so ``clean`` rejects it.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from ledger.models import OccurrenceOverride, ScheduleAmount, Transaction, attach_schedule_rows
from ledger.tests.commitment_fixtures import TODAY, CommitmentFixture, clean_save

D = Decimal


class CommitmentConstraintTests(CommitmentFixture):
    def assert_integrity(self, create):
        with self.assertRaises(IntegrityError), transaction.atomic():
            create()

    def test_transaction_confirmation_constraints(self):
        values = {
            "user": self.user,
            "title": "Direct",
            "amount": D("1.00"),
            "transaction_type": "EXPENSE",
            "category": self.expense,
            "date": date(2026, 1, 1),
        }
        account = {"payment_channel": "ACCOUNT", "bank_account": self.account}
        # transactions_confirmation_has_start
        self.assert_integrity(
            lambda: Transaction.objects.create(
                **values, **account, is_fixed=True, requires_confirmation=True
            )
        )
        # transactions_confirmation_scope: a card, a source that is not fixed, installments.
        start = {"requires_confirmation": True, "confirmation_start": date(2026, 1, 1)}
        self.assert_integrity(
            lambda: Transaction.objects.create(
                **values,
                payment_channel="CREDIT_CARD",
                credit_card=self.card,
                is_fixed=True,
                **start,
            )
        )
        self.assert_integrity(lambda: Transaction.objects.create(**values, **account, **start))
        self.assert_integrity(
            lambda: Transaction.objects.create(
                **values,
                payment_channel="CREDIT_CARD",
                credit_card=self.card,
                installments=3,
                **start,
            )
        )
        for channel, instrument in (
            ("ACCOUNT", {"bank_account": self.account}),
            ("PIX", {"bank_account": self.account}),
            ("DEBIT_CARD", {"debit_card": self.debit}),
        ):
            with self.subTest(channel=channel), transaction.atomic():
                Transaction.objects.create(
                    **values, payment_channel=channel, **instrument, is_fixed=True, **start
                )
                transaction.set_rollback(True)

    def test_schedule_amount_constraints(self):
        ScheduleAmount.objects.create(
            user=self.user,
            transaction=self.rent,
            effective_month=date(2026, 3, 1),
            amount=D("110.00"),
        )
        self.assert_integrity(
            lambda: ScheduleAmount.objects.create(
                user=self.user,
                transaction=self.rent,
                effective_month=date(2026, 3, 1),
                amount=D("120.00"),
            )
        )
        self.assert_integrity(
            lambda: ScheduleAmount.objects.create(
                user=self.user,
                transaction=self.rent,
                effective_month=date(2026, 4, 1),
                amount=D("0.00"),
            )
        )
        # A day other than the first passes the database; clean rejects it below.
        ScheduleAmount.objects.create(
            user=self.user,
            transaction=self.rent,
            effective_month=date(2026, 5, 2),
            amount=D("1.00"),
        )

    def test_override_constraints(self):
        def create(month, **values):
            return lambda: OccurrenceOverride.objects.create(
                user=self.user, transaction=self.rent, month=month, **values
            )

        create(date(2026, 3, 1), status="SKIPPED")()
        self.assert_integrity(create(date(2026, 3, 1), status="ADJUSTED", amount=D("1.00")))
        self.assert_integrity(create(date(2026, 4, 1), status="PAUSED"))
        self.assert_integrity(create(date(2026, 4, 1), status="CONFIRMED", amount=D("0.00")))
        self.assert_integrity(create(date(2026, 4, 1), status="SKIPPED", amount=D("1.00")))
        self.assert_integrity(create(date(2026, 4, 1), status="SKIPPED", date=date(2026, 4, 2)))
        self.assert_integrity(create(date(2026, 4, 1), status="ADJUSTED"))
        create(date(2026, 4, 1), status="ADJUSTED", date=date(2026, 4, 2))()
        create(date(2026, 5, 1), status="CONFIRMED")()
        create(date(2026, 6, 2), status="SKIPPED")()


class CommitmentValidationTests(CommitmentFixture):
    def amount(self, month, value, item=None, user=None):
        return ScheduleAmount(
            user=user or self.user,
            transaction=item or self.rent,
            effective_month=month,
            amount=D(value),
        )

    def override(self, month, status, item=None, *, validation_today=None, **values):
        row = OccurrenceOverride(
            user=self.user, transaction=item or self.rent, month=month, status=status, **values
        )
        if validation_today is not None:
            row.validation_today = validation_today
        return row

    def errors(self, instance):
        with self.assertRaises(ValidationError) as raised:
            instance.full_clean()
        return raised.exception.message_dict

    def test_transaction_confirmation_rules(self):
        item = self.fresh(self.rent)
        item.requires_confirmation, item.confirmation_start = True, date(2026, 3, 2)
        self.assertEqual(
            self.errors(item), {"confirmation_start": ["Use the first day of the month."]}
        )
        item.confirmation_start = None
        self.assertEqual(
            self.errors(item), {"confirmation_start": ["Choose the first month to confirm."]}
        )
        card = self.fresh(self.gym)
        card.requires_confirmation, card.confirmation_start = True, date(2026, 3, 1)
        self.assertEqual(list(self.errors(card)), ["requires_confirmation"])
        item.confirmation_start = date(2026, 3, 1)
        item.full_clean()

    def test_amount_change_rules(self):
        self.assertEqual(
            self.errors(self.amount(date(2026, 3, 2), "1.00")),
            {"effective_month": ["Use the first day of the month."]},
        )
        self.assertIn(
            "Choose a month after the first month",
            self.errors(self.amount(date(2026, 1, 1), "1.00"))["effective_month"][0],
        )
        # The card source starts in its February statement.
        self.assertIn(
            "effective_month", self.errors(self.amount(date(2026, 2, 1), "1.00", self.gym))
        )
        clean_save(self.amount(date(2026, 3, 1), "1.00", self.gym))
        self.assertEqual(
            self.errors(self.amount(date(2026, 5, 1), "100.00")),
            {"amount": ["This amount already applies from that month."]},
        )
        clean_save(self.amount(date(2026, 5, 1), "120.00"))
        self.assertEqual(
            self.errors(self.amount(date(2026, 7, 1), "120.00")),
            {"amount": ["This amount already applies from that month."]},
        )
        # The row itself does not count: a new amount for the same month is valid.
        row = ScheduleAmount.objects.get(transaction=self.rent, effective_month=date(2026, 5, 1))
        row.amount = D("125.00")
        row.full_clean()
        ended = self.source(
            "Course", "30.00", "ACCOUNT", date(2026, 1, 10), fixed_until=date(2026, 6, 30)
        )
        self.assertEqual(
            self.errors(self.amount(date(2026, 7, 1), "31.00", ended)),
            {"effective_month": ["This month is after the end of the schedule."]},
        )
        clean_save(self.amount(date(2026, 6, 1), "31.00", ended))

    def test_owner_and_source_rules(self):
        self.assertEqual(
            self.errors(self.amount(date(2026, 3, 1), "1.00", user=self.other)),
            {"transaction": ["This selection must belong to the transaction owner."]},
        )
        plan = self.source(
            "Laptop", "600.00", "CREDIT_CARD", date(2026, 1, 20), is_fixed=False, installments=6
        )
        self.assertEqual(
            self.errors(self.amount(date(2026, 4, 1), "1.00", plan)),
            {"transaction": ["Installment plans keep their amounts."]},
        )
        single = self.source("Once", "9.00", "ACCOUNT", date(2026, 1, 20), is_fixed=False)
        self.assertEqual(
            self.errors(self.override(date(2026, 1, 1), "SKIPPED", single)),
            {"transaction": ["Only monthly recurring transactions have a monthly schedule."]},
        )

    def test_override_rules(self):
        self.assertEqual(
            self.errors(self.override(date(2025, 12, 1), "SKIPPED")),
            {"month": ["This month has no occurrence of the schedule."]},
        )
        self.assertEqual(
            self.errors(self.override(date(2026, 3, 2), "SKIPPED")),
            {"month": ["Use the first day of the month."]},
        )
        clean_save(self.override(date(2026, 3, 1), "SKIPPED"))
        # The skipped month still has an occurrence without its own override.
        self.override(date(2026, 3, 1), "ADJUSTED", amount=D("1.00")).clean()
        self.assertEqual(
            self.errors(self.override(date(2026, 4, 1), "ADJUSTED", date=date(2026, 5, 1))),
            {"date": ["The date must be in April 2026."]},
        )
        self.assertEqual(
            self.errors(
                self.override(
                    date(2026, 4, 1), "ADJUSTED", amount=D("100.00"), date=date(2026, 4, 10)
                )
            ),
            {"amount": ["Change the amount or the date, or cancel."]},
        )
        self.assertEqual(
            self.errors(
                self.override(date(2026, 3, 1), "ADJUSTED", self.gym, date=date(2026, 3, 2))
            ),
            {"date": ["A card purchase keeps its statement; only its amount can change."]},
        )
        clean_save(self.override(date(2026, 3, 1), "ADJUSTED", self.gym, amount=D("55.00")))
        early = self.source("Early", "10.00", "ACCOUNT", date(2026, 1, 1))
        self.assertEqual(
            self.errors(
                self.override(date(2026, 1, 1), "ADJUSTED", early, date=date(2025, 12, 31))
            ),
            {"date": ["The date must be in January 2026."]},
        )

    def test_confirmation_rules(self):
        self.assertEqual(
            self.errors(self.override(date(2026, 9, 1), "CONFIRMED", date=date(2026, 9, 10))),
            {"status": ["This transaction does not ask for confirmation."]},
        )
        item = self.fresh(self.rent)
        item.requires_confirmation, item.confirmation_start = True, date(2026, 6, 1)
        item.save()
        item = self.fresh(item)
        self.assertEqual(
            self.errors(self.override(date(2026, 5, 1), "CONFIRMED", item, date=date(2026, 5, 10))),
            {"month": ["This month is before the first month to confirm."]},
        )
        self.assertEqual(
            self.errors(
                self.override(date(2026, 9, 1), "CONFIRMED", item, date=TODAY.replace(day=21))
            ),
            {"date": ["A confirmation date cannot be in the future."]},
        )
        self.assertEqual(
            self.errors(self.override(date(2026, 9, 1), "CONFIRMED", item, date=date(2026, 8, 31))),
            {"date": ["The confirmation date cannot precede September 2026."]},
        )
        # Without a date, the scheduled cash date must not be in the future.
        self.assertEqual(
            list(
                self.errors(
                    self.override(
                        date(2026, 10, 1), "CONFIRMED", item, validation_today=date(2026, 10, 9)
                    )
                )
            ),
            ["date"],
        )
        clean_save(
            self.override(
                date(2026, 9, 1), "CONFIRMED", item, date=date(2026, 10, 2), amount=D("101.00")
            )
        )
        self.account.opening_date = date(2026, 6, 15)
        self.account.save()
        self.assertEqual(
            self.errors(
                self.override(
                    date(2026, 6, 1), "CONFIRMED", self.fresh(item), date=date(2026, 6, 10)
                )
            ),
            {"date": ["The transaction cannot precede the account opening balance date."]},
        )


class CommitmentDeletionTests(CommitmentFixture):
    def test_rows_follow_their_transaction_and_owner(self):
        ScheduleAmount.objects.create(
            user=self.user,
            transaction=self.rent,
            effective_month=date(2026, 3, 1),
            amount=D("110.00"),
        )
        OccurrenceOverride.objects.create(
            user=self.user, transaction=self.rent, month=date(2026, 4, 1), status="SKIPPED"
        )
        OccurrenceOverride.objects.create(
            user=self.other, transaction=self.foreign, month=date(2026, 4, 1), status="SKIPPED"
        )
        self.rent.delete()
        self.assertEqual(
            (ScheduleAmount.objects.count(), OccurrenceOverride.objects.count()), (0, 1)
        )
        self.foreign.delete()
        self.assertEqual(OccurrenceOverride.objects.count(), 0)
        # Bank rows protect a user, so the owner CASCADE is checked on the field.
        for model in (ScheduleAmount, OccurrenceOverride):
            self.assertIs(model._meta.get_field("user").remote_field.on_delete, models.CASCADE)

    def test_rows_stay_and_are_ignored_when_the_source_is_no_longer_fixed(self):
        ScheduleAmount.objects.create(
            user=self.user,
            transaction=self.rent,
            effective_month=date(2026, 3, 1),
            amount=D("110.00"),
        )
        item = self.fresh(self.rent)
        item.is_fixed = False
        item.save()
        item = self.fresh(item)
        self.assertEqual(item.schedule_rows(), ((), ()))
        self.assertEqual(ScheduleAmount.objects.count(), 1)
        item.is_fixed = True
        item.clear_schedule_rows()
        self.assertEqual(str(item.amount_for_month(2026, 3)), "110.00")


class ScheduleRowLoadingTests(CommitmentFixture):
    """``with_schedule_flags``, ``attach_schedule_rows`` and the lazy fallback of ``schedule_rows``."""

    def test_flags_mark_only_commitment_sources_with_rows(self):
        plan = self.source(
            "Laptop", "600.00", "CREDIT_CARD", date(2026, 2, 3), is_fixed=False, installments=6
        )
        ScheduleAmount.objects.create(
            user=self.user,
            transaction=self.rent,
            effective_month=date(2026, 3, 1),
            amount=D("110.00"),
        )
        OccurrenceOverride.objects.create(
            user=self.user, transaction=self.salary, month=date(2026, 4, 1), status="SKIPPED"
        )
        ScheduleAmount.objects.create(
            user=self.user,
            transaction=self.gym,
            effective_month=date(2026, 3, 1),
            amount=D("60.00"),
        )
        OccurrenceOverride.objects.create(
            user=self.user, transaction=self.gym, month=date(2026, 4, 1), status="SKIPPED"
        )
        # The engine ignores the rows of an installment plan, so it gets no flag.
        OccurrenceOverride.objects.create(
            user=self.user, transaction=plan, month=date(2026, 4, 1), status="SKIPPED"
        )
        flags = dict(
            Transaction.objects.with_schedule_flags().values_list("pk", "schedule_row_flags")
        )
        self.assertEqual(
            flags,
            {self.rent.pk: 1, self.salary.pk: 2, self.gym.pk: 3, plan.pk: 0, self.foreign.pk: 0},
        )
        with self.assertNumQueries(3):
            items = attach_schedule_rows(
                Transaction.objects.filter(user=self.user).with_schedule_flags()
            )
        rows = {item.pk: item.schedule_rows() for item in items}
        self.assertEqual(rows[self.rent.pk], (((date(2026, 3, 1), D("110.00")),), ()))
        self.assertEqual(rows[plan.pk], ((), ()))
        self.assertEqual(len(rows[self.gym.pk][0]) + len(rows[self.gym.pk][1]), 2)

    def test_lazy_rows_refuse_a_row_of_another_owner(self):
        row = ScheduleAmount.objects.create(
            user=self.user,
            transaction=self.rent,
            effective_month=date(2026, 3, 1),
            amount=D("110.00"),
        )
        self.assertEqual(
            self.fresh(self.rent).schedule_rows(), (((date(2026, 3, 1), D("110.00")),), ())
        )
        ScheduleAmount.objects.filter(pk=row.pk).update(user=self.other)
        for item in (
            self.fresh(self.rent),
            Transaction.objects.with_schedule_flags().get(pk=self.rent.pk),
        ):
            with (
                self.subTest(flags="schedule_row_flags" in item.__dict__),
                self.assertRaises(ValidationError),
            ):
                item.schedule_rows()
        OccurrenceOverride.objects.create(
            user=self.other, transaction=self.salary, month=date(2026, 4, 1), status="SKIPPED"
        )
        with self.assertRaises(ValidationError):
            self.fresh(self.salary).schedule_rows()
