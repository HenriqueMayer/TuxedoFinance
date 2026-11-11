"""Unit tests of the occurrence engine, ledger.schedule.

The engine is pure, so these tests use SimpleTestCase: a database query
fails the test. Sources are frozen values or unsaved transactions with
instruments that have explicit primary keys. All values are synthetic.
Amounts are compared as exact text, because str() of a Decimal shows its
exponent and saved scenario drafts compare amount texts.
"""

import ast
import json
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from banking.models import BankAccount, CreditCard, DebitCard
from ledger import schedule
from ledger.consultation import billed_month_occurrence as _billed_month_occurrence
from ledger.consultation import filter_by_billed_month as _filter_transactions_by_billed_month
from ledger.consultation import financial_effect
from ledger.models import Transaction
from ledger.projection import (
    MAX_MONTHLY_OCCURRENCES,
    ProjectionLimitExceeded,
    occurrence_months,
    occurrence_window,
    validate_occurrences,
)
from ledger.projection_plan import build_projection_plan, loyalty_purchase_source
from ledger.schedule import Instrument, ScheduleSource, Window, expand, statement_totals

D = Decimal
ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = Instrument("ACCOUNT", 1, 10)
PIX = Instrument("PIX", 1, 10)
DEBIT = Instrument("DEBIT_CARD", 2, 10)
# The due day is before the closing day: each statement is due in the next month.
LATE = Instrument("CREDIT_CARD", 3, 10, closing_day=30, due_day=7)
# The due day is after the closing day: each statement is due in its own month.
EARLY = Instrument("CREDIT_CARD", 4, 10, closing_day=3, due_day=12)
# The closing day 31 is clamped to the length of shorter months.
MONTH_END = Instrument("CREDIT_CARD", 5, 10, closing_day=31, due_day=10)
FAR = date(2200, 12, 31)


def source(when, amount="100.00", instrument=ACCOUNT, *, pk=1, flow="EXPENSE", **values):
    return ScheduleSource(
        schedule.TRANSACTION, pk, when, D(amount), "BRL", flow, instrument, **values
    )


def summary(occurrences):
    """Return (reference month, amount text, cash date, economic date) for each occurrence."""
    return [
        (item.reference_month, str(item.amount), item.cash_date, item.economic_date)
        for item in occurrences
    ]


def months(first, last=None):
    return Window.months(first, last)


class SingleSourceTests(SimpleTestCase):
    def test_account_channels_settle_on_the_source_date(self):
        for instrument in (ACCOUNT, PIX, DEBIT):
            with self.subTest(channel=instrument.channel):
                item = source(date(2026, 10, 31), "310.45", instrument)
                (occurrence,) = expand([item], months(date(2026, 10, 1)))
                self.assertEqual(occurrence.key, "transaction:1:2026-10")
                self.assertEqual((occurrence.source_type, occurrence.source_id), ("transaction", 1))
                self.assertEqual(
                    summary([occurrence]),
                    [(date(2026, 10, 1), "310.45", date(2026, 10, 31), date(2026, 10, 31))],
                )
                self.assertEqual(
                    (occurrence.currency, occurrence.flow, occurrence.instrument),
                    ("BRL", "EXPENSE", instrument),
                )
                self.assertEqual(
                    (occurrence.installment, occurrence.status, occurrence.allocations),
                    (None, schedule.SCHEDULED, None),
                )
                self.assertEqual(expand([item], months(date(2026, 11, 1))), [])
                self.assertEqual(expand([item], Window.through(date(2026, 10, 30))), [])
                self.assertEqual(len(expand([item], Window.through(date(2026, 10, 31)))), 1)

    def test_credit_card_statement_month_and_bill_choice(self):
        cases = (
            # Day 2 is before the closing day 30: the statement of November.
            (date(2026, 11, 2), None, date(2026, 11, 1), date(2026, 12, 7)),
            (date(2026, 11, 2), 0, date(2026, 11, 1), date(2026, 12, 7)),
            (date(2026, 11, 2), 1, date(2026, 12, 1), date(2027, 1, 7)),
            # Day 30 is on the closing day: the statement of the next month.
            (date(2026, 9, 30), None, date(2026, 10, 1), date(2026, 11, 7)),
            (date(2026, 9, 30), 0, date(2026, 9, 1), date(2026, 10, 7)),
        )
        for when, override, reference, due in cases:
            with self.subTest(date=when, override=override):
                item = source(when, "200.00", LATE, billing_override=override)
                (occurrence,) = expand([item], months(date(2026, 1, 1), date(2027, 12, 1)))
                self.assertEqual(summary([occurrence]), [(reference, "200.00", due, when)])
                self.assertEqual(occurrence.key, f"transaction:1:{reference:%Y-%m}")

    def test_current_bill_can_be_due_before_the_purchase(self):
        item = source(date(2026, 10, 20), "450.00", EARLY, billing_override=0)
        (occurrence,) = expand([item], Window.through(date(2026, 10, 31)))
        self.assertEqual(
            (occurrence.reference_month, occurrence.cash_date),
            (date(2026, 10, 1), date(2026, 10, 12)),
        )

    def test_an_invalid_bill_choice_raises(self):
        with self.assertRaises(ValueError):
            expand(
                [source(date(2026, 1, 5), instrument=LATE, billing_override=2)],
                months(date(2026, 1, 1)),
            )


class FixedSourceTests(SimpleTestCase):
    def test_source_day_is_clamped_in_short_months_of_leap_and_other_years(self):
        for day, expected in (
            (29, [date(2027, 1, 29), date(2027, 2, 28), date(2028, 1, 29), date(2028, 2, 29)]),
            (30, [date(2027, 1, 30), date(2027, 2, 28), date(2028, 1, 30), date(2028, 2, 29)]),
            (31, [date(2027, 1, 31), date(2027, 2, 28), date(2028, 1, 31), date(2028, 2, 29)]),
        ):
            with self.subTest(day=day):
                item = source(date(2026, 12, day), "39.90", PIX, is_fixed=True)
                found = [
                    occurrence.cash_date
                    for occurrence in expand([item], months(date(2027, 1, 1), date(2028, 2, 1)))
                    if occurrence.reference_month.month in (1, 2)
                ]
                self.assertEqual(found, expected)
        item = source(date(2026, 1, 31), "1800.00", is_fixed=True)
        self.assertEqual(
            [occurrence.cash_date for occurrence in expand([item], months(date(2026, 4, 1)))],
            [date(2026, 4, 30)],
        )

    def test_card_occurrence_keeps_its_event_date_and_moves_to_the_statement(self):
        # Day 30 is on the closing day 30, so each event month goes to the next statement.
        item = source(date(2026, 4, 30), "21.90", LATE, is_fixed=True)
        occurrences = expand([item], months(date(2026, 5, 1), date(2026, 6, 1)))
        self.assertEqual(
            summary(occurrences),
            [
                (date(2026, 5, 1), "21.90", date(2026, 6, 7), date(2026, 4, 30)),
                (date(2026, 6, 1), "21.90", date(2026, 7, 7), date(2026, 5, 30)),
            ],
        )
        self.assertEqual(
            [occurrence.key for occurrence in occurrences],
            ["transaction:1:2026-05", "transaction:1:2026-06"],
        )
        self.assertEqual(expand([item], months(date(2026, 4, 1))), [])

    def test_fixed_until_ends_the_event_months_and_billing_shifts_the_last_statement(self):
        account = source(date(2026, 3, 29), "99.90", is_fixed=True, fixed_until=date(2026, 12, 1))
        references = [
            item.reference_month
            for item in expand([account], months(date(2026, 1, 1), date(2027, 3, 1)))
        ]
        self.assertEqual(
            (references[0], references[-1], len(references)),
            (date(2026, 3, 1), date(2026, 12, 1), 10),
        )
        # The purchase day 2 is before the closing day 3: no billing shift.
        unshifted = source(
            date(2026, 1, 2), "150.00", EARLY, is_fixed=True, fixed_until=date(2026, 12, 31)
        )
        references = [
            item.reference_month
            for item in expand([unshifted], months(date(2025, 1, 1), date(2027, 6, 1)))
        ]
        self.assertEqual(
            (references[0], references[-1], len(references)),
            (date(2026, 1, 1), date(2026, 12, 1), 12),
        )
        # The purchase day 31 is after the closing day 30: the final event
        # month March goes to the April statement.
        shifted = source(
            date(2026, 1, 31), "10.00", LATE, is_fixed=True, fixed_until=date(2026, 3, 1)
        )
        self.assertEqual(
            summary(expand([shifted], months(date(2026, 1, 1), date(2026, 12, 1)))),
            [
                (date(2026, 2, 1), "10.00", date(2026, 3, 7), date(2026, 1, 31)),
                (date(2026, 3, 1), "10.00", date(2026, 4, 7), date(2026, 2, 28)),
                (date(2026, 4, 1), "10.00", date(2026, 5, 7), date(2026, 3, 31)),
            ],
        )
        self.assertEqual(schedule.occurrence_window(shifted, FAR), (date(2026, 2, 1), 3))
        self.assertEqual(len(expand([shifted], Window.through(FAR))), 3)


class InstallmentTests(SimpleTestCase):
    def test_first_installment_receives_the_rounding_remainder(self):
        item = source(date(2026, 10, 29), "1999.99", EARLY, installments=3)
        occurrences = expand([item], months(date(2026, 1, 1), date(2027, 12, 1)))
        self.assertEqual(
            summary(occurrences),
            [
                (date(2026, 11, 1), "666.67", date(2026, 11, 12), date(2026, 10, 29)),
                (date(2026, 12, 1), "666.66", date(2026, 12, 12), date(2026, 10, 29)),
                (date(2027, 1, 1), "666.66", date(2027, 1, 12), date(2026, 10, 29)),
            ],
        )
        self.assertEqual(
            [occurrence.installment for occurrence in occurrences], [(1, 3), (2, 3), (3, 3)]
        )
        self.assertEqual(
            sum((occurrence.amount for occurrence in occurrences), schedule.ZERO), D("1999.99")
        )

    def test_a_later_first_installment_keeps_numbering_and_skips_earlier_statements(self):
        item = source(date(2026, 3, 10), "2500.00", LATE, installments=12, installment_start=5)
        occurrences = expand([item], months(date(2026, 1, 1), date(2027, 12, 1)))
        self.assertEqual(
            [occurrence.installment for occurrence in occurrences],
            [(number, 12) for number in range(5, 13)],
        )
        self.assertEqual(
            (occurrences[0].reference_month, occurrences[-1].reference_month),
            (date(2026, 7, 1), date(2027, 2, 1)),
        )
        # The first installment is not tracked, so its remainder is not charged.
        self.assertEqual({str(occurrence.amount) for occurrence in occurrences}, {"208.33"})
        self.assertEqual(
            schedule.occurrence_window(item, date(2026, 10, 20)), (date(2026, 7, 1), 4)
        )
        self.assertEqual(len(expand([item], Window.through(date(2026, 10, 20)))), 4)
        self.assertEqual(
            str(schedule.amount_through(11, item.amount, False, None, 12, 5)), "1666.64"
        )
        self.assertEqual(
            str(schedule.amount_through(11, item.amount, False, None, 12, 1)), "2500.00"
        )

    def test_small_amounts_can_leave_later_installments_without_an_amount(self):
        item = source(date(2026, 1, 5), "0.05", EARLY, installments=6)
        self.assertEqual(
            summary(expand([item], months(date(2026, 1, 1), date(2026, 12, 1)))),
            [(date(2026, 2, 1), "0.05", date(2026, 2, 12), date(2026, 1, 5))],
        )

    def test_a_legacy_fixed_source_with_installments_has_no_installment_number(self):
        # Model validation rejects this row. Its amounts follow the fixed
        # rule, and its economic date stays the source date, as in the
        # readers before the engine. Day 2 is before the closing day 3.
        item = source(date(2026, 1, 2), "100.00", EARLY, is_fixed=True, installments=2)
        occurrences = expand([item], months(date(2026, 1, 1), date(2026, 6, 1)))
        self.assertEqual(
            [
                (str(occurrence.amount), occurrence.installment, occurrence.economic_date)
                for occurrence in occurrences
            ],
            [("100.00", None, date(2026, 1, 2))] * 6,
        )


class WindowTests(SimpleTestCase):
    def test_synchronization_window_uses_cash_dates_without_a_card(self):
        item = source(date(2026, 1, 31), "1800.00", is_fixed=True)
        self.assertEqual(
            [
                occurrence.cash_date
                for occurrence in expand([item], Window.through(date(2026, 3, 30)))
            ],
            [date(2026, 1, 31), date(2026, 2, 28)],
        )
        self.assertEqual(len(expand([item], Window.through(date(2026, 3, 31)))), 3)

    def test_synchronization_window_uses_reference_months_for_a_card(self):
        item = source(date(2026, 1, 15), "30.00", LATE, is_fixed=True)
        occurrences = expand([item], Window.through(date(2026, 3, 1)))
        self.assertEqual(
            [occurrence.reference_month for occurrence in occurrences],
            [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
        )
        # The due dates follow the horizon; the statement months do not.
        self.assertEqual(occurrences[-1].cash_date, date(2026, 4, 7))

    def test_month_window_selects_reference_months(self):
        card = source(date(2026, 9, 30), "120.00", LATE, pk=2)
        account = source(date(2026, 9, 30), "88.20", DEBIT, pk=3)
        self.assertEqual(
            [item.key for item in expand([card, account], months(date(2026, 9, 1)))],
            ["transaction:3:2026-09"],
        )
        self.assertEqual(
            [item.key for item in expand([card, account], months(date(2026, 10, 15)))],
            ["transaction:2:2026-10"],
        )

    def test_installments_without_a_card_post_cash_only_once(self):
        # Model validation allows installments only on a credit card. A
        # legacy row keeps the readers' months and posts one movement.
        item = source(date(2026, 2, 10), "100.00", installments=3)
        self.assertEqual(
            summary(expand([item], months(date(2026, 1, 1), date(2026, 12, 1)))),
            [
                (date(2026, 2, 1), "33.34", date(2026, 2, 10), date(2026, 2, 10)),
                (date(2026, 3, 1), "33.33", date(2026, 2, 10), date(2026, 2, 10)),
                (date(2026, 4, 1), "33.33", date(2026, 2, 10), date(2026, 2, 10)),
            ],
        )
        self.assertEqual(
            summary(expand([item], Window.through(FAR))),
            [(date(2026, 2, 1), "33.34", date(2026, 2, 10), date(2026, 2, 10))],
        )

    def test_window_values_are_validated(self):
        for values in (
            {},
            {"horizon": FAR, "first_month": FAR, "last_month": FAR},
            {"first_month": FAR},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Window(**values)
        with self.assertRaises(ValueError):
            Window.months(date(2026, 2, 1), date(2026, 1, 31))
        with self.assertRaises(TypeError):
            expand([source(date(2026, 1, 1))], FAR)

    def test_overrides_are_reserved(self):
        with self.assertRaises(ValueError):
            expand([source(date(2026, 1, 1))], Window.through(FAR), overrides=[object()])

    def test_order_is_source_order_then_month_order(self):
        items = [
            source(date(2026, 3, 1), pk=2, is_fixed=True),
            source(date(2026, 1, 1), pk=1, is_fixed=True),
        ]
        self.assertEqual(
            [item.key for item in expand(items, months(date(2026, 3, 1), date(2026, 4, 1)))],
            [
                "transaction:2:2026-03",
                "transaction:2:2026-04",
                "transaction:1:2026-03",
                "transaction:1:2026-04",
            ],
        )


class LimitsAndKeysTests(SimpleTestCase):
    def transaction(self, when, **values):
        account = BankAccount(id=10, currency="BRL")
        values.setdefault("bank_account", account)
        return Transaction(
            id=50,
            title="Synthetic",
            amount=D("17.23"),
            transaction_type="EXPENSE",
            payment_channel=values.pop("payment_channel", "ACCOUNT"),
            date=when,
            **values,
        )

    def test_validate_occurrences_accepts_1200_and_rejects_1201(self):
        self.assertEqual(MAX_MONTHLY_OCCURRENCES, 1200)
        horizon = date(2099, 12, 31)
        validate_occurrences(self.transaction(date(2000, 1, 1), is_fixed=True), horizon)
        with self.assertRaises(ProjectionLimitExceeded):
            validate_occurrences(self.transaction(date(1999, 12, 1), is_fixed=True), horizon)
        # A billing shift moves the first statement into the window limit.
        card = CreditCard(
            id=20, closing_day=24, due_day=31, account=BankAccount(id=11, currency="BRL")
        )
        shifted = self.transaction(
            date(1999, 12, 31),
            is_fixed=True,
            payment_channel="CREDIT_CARD",
            bank_account=None,
            credit_card=card,
        )
        self.assertEqual(occurrence_window(shifted, horizon), (date(2000, 1, 1), 1200))
        validate_occurrences(shifted, horizon)
        shifted.billing_override = Transaction.BillChoice.CURRENT
        self.assertEqual(occurrence_window(shifted, horizon), (date(1999, 12, 1), 1201))
        with self.assertRaises(ProjectionLimitExceeded):
            validate_occurrences(shifted, horizon)
        # An ended schedule counts only its own months, not the gap to the horizon.
        validate_occurrences(
            self.transaction(date.min, is_fixed=True, fixed_until=date(1, 3, 31)), horizon
        )
        self.assertEqual(
            list(
                occurrence_months(
                    self.transaction(date.min, is_fixed=True, fixed_until=date(1, 3, 31)), horizon
                )
            ),
            [date(1, 1, 1), date(1, 2, 1), date(1, 3, 1)],
        )

    def test_date_max_guard(self):
        late_start = source(
            date(9999, 6, 15), "120.00", EARLY, installments=12, installment_start=12
        )
        self.assertEqual(schedule.occurrence_window(late_start, date.max), (None, 0))
        self.assertEqual(expand([late_start], Window.through(date.max)), [])
        self.assertEqual(expand([late_start], months(date(9999, 1, 1), date(9999, 12, 1))), [])
        open_fixed = source(date(9999, 11, 30), "5.00", is_fixed=True)
        self.assertEqual(
            [item.cash_date for item in expand([open_fixed], months(date(9999, 1, 1), date.max))],
            [date(9999, 11, 30), date(9999, 12, 30)],
        )
        self.assertEqual(schedule.offset_month(date.max, 1), None)
        with self.assertRaises(ValueError):
            schedule.billing_offset(date(9999, 12, 31), 30, None)

    def test_a_due_date_after_date_max_gives_no_cash_date(self):
        # LATE is due in the month after the statement month, so its December
        # 9999 statement is due in January 10000. EARLY is due in the
        # statement month.
        cases = (
            source(date(9999, 6, 15), "5.00", LATE, is_fixed=True),
            # Day 30 is on the closing day 30: the December statement.
            source(date(9999, 11, 30), "5.00", LATE),
            source(date(9999, 12, 1), "5.00", LATE),
        )
        for item in cases:
            with self.subTest(date=item.date, fixed=item.is_fixed):
                (occurrence,) = expand([item], months(date(9999, 12, 1)), allocations=True)
                self.assertEqual(
                    (occurrence.reference_month, str(occurrence.amount), occurrence.cash_date),
                    (date(9999, 12, 1), "5.00", None),
                )
                self.assertEqual(occurrence.key, "transaction:1:9999-12")
                self.assertIsNone(expand([item], Window.through(date.max))[-1].cash_date)
        fixed = expand([cases[0]], Window.through(date.max))
        self.assertEqual([item.cash_date for item in fixed[-2:]], [date(9999, 12, 7), None])
        (early,) = expand([source(date(9999, 12, 2), "5.00", EARLY)], months(date(9999, 12, 1)))
        self.assertEqual(early.cash_date, date(9999, 12, 12))
        self.assertIsNone(schedule.statement_due_date(LATE, date(9999, 12, 31)))
        self.assertIsNone(
            schedule.statement_due_date(Instrument("CREDIT_CARD", None, None), date(2026, 1, 1))
        )

    def test_keys(self):
        self.assertEqual(
            expand([source(date(2026, 1, 5), pk=None)], months(date(2026, 1, 1)))[0].key, None
        )
        (ancient,) = expand([source(date(1, 1, 1))], months(date(1, 1, 1)))
        # Years before 1000 keep the strftime text of the existing movement keys.
        self.assertEqual(ancient.key, f"transaction:1:{date(1, 1, 1):%Y-%m}")
        self.assertEqual(
            expand([source(date(2026, 12, 31))], months(date(2026, 12, 1)))[0].key,
            "transaction:1:2026-12",
        )

    def test_loyalty_purchase_source_has_one_statement_occurrence(self):
        card = CreditCard(id=3, account_id=10, closing_day=30, due_day=7)
        entry = SimpleNamespace(
            pk=77, date=date(2026, 10, 30), cash_amount=D("175.00"), funding_credit_card=card
        )
        item = loyalty_purchase_source(entry)
        (occurrence,) = expand([item], Window.through(date(2026, 11, 10)))
        self.assertEqual(
            (occurrence.key, occurrence.source_type, occurrence.flow, occurrence.currency),
            ("loyalty_purchase:77:2026-11", "loyalty_purchase", "EXPENSE", ""),
        )
        self.assertEqual(
            summary([occurrence]),
            [(date(2026, 11, 1), "175.00", date(2026, 12, 7), date(2026, 10, 30))],
        )
        self.assertEqual(loyalty_purchase_source(entry, "USD").currency, "USD")


class StatementTotalTests(SimpleTestCase):
    def test_totals_group_card_occurrences_by_card_and_month(self):
        occurrences = expand(
            [
                # Both purchases are on or after the closing day 30: the November statement.
                source(date(2026, 10, 31), "95.50", LATE, pk=1),
                source(date(2026, 10, 30), "4.50", LATE, pk=2),
                # Day 5 is after the closing day 3: the December statement.
                source(date(2026, 11, 5), "10", EARLY, pk=3),
                source(date(2026, 11, 5), "432.10", ACCOUNT, pk=4),
            ],
            months(date(2026, 11, 1), date(2026, 12, 1)),
        )
        totals = statement_totals(occurrences)
        self.assertEqual(list(totals), [(3, date(2026, 11, 1)), (4, date(2026, 12, 1))])
        # Each total starts at ZERO, so a whole amount shows two decimal places.
        self.assertEqual(
            {key: str(value) for key, value in totals.items()},
            {(3, date(2026, 11, 1)): "100.00", (4, date(2026, 12, 1)): "10.00"},
        )
        existing = {(9, date(2026, 1, 1)): D("1.00")}
        self.assertIs(statement_totals(occurrences, existing), existing)
        self.assertEqual(
            list(existing), [(9, date(2026, 1, 1)), (3, date(2026, 11, 1)), (4, date(2026, 12, 1))]
        )
        self.assertEqual(statement_totals([]), {})


class AllocationTests(SimpleTestCase):
    def test_installment_split_closes_exactly_on_each_category(self):
        capacities = ((7, D("500.00")), (8, D("333.33")), (9, D("166.67")))
        item = source(
            date(2026, 2, 27), "1000.00", LATE, installments=6, category_id=7, splits=capacities
        )
        occurrences = expand([item], months(date(2026, 1, 1), date(2026, 12, 1)), allocations=True)
        self.assertEqual(
            [str(occurrence.amount) for occurrence in occurrences],
            ["166.70", "166.66", "166.66", "166.66", "166.66", "166.66"],
        )
        self.assertEqual(
            [
                [str(value) for _category, value in occurrence.allocations]
                for occurrence in occurrences[:2]
            ],
            [["83.35", "55.57", "27.78"], ["83.33", "55.55", "27.78"]],
        )
        for occurrence in occurrences:
            self.assertEqual([category for category, _value in occurrence.allocations], [7, 8, 9])
            self.assertEqual(
                sum((value for _category, value in occurrence.allocations), schedule.ZERO),
                occurrence.amount,
            )
            self.assertTrue(all(value >= 0 for _category, value in occurrence.allocations))
        totals = [
            sum((occurrence.allocations[index][1] for occurrence in occurrences), schedule.ZERO)
            for index in range(3)
        ]
        self.assertEqual([str(value) for value in totals], ["500.00", "333.33", "166.67"])
        # The purchase is in the February statement. A window that starts at
        # the fourth installment (May) replays the earlier installments first.
        (fourth,) = expand([item], months(date(2026, 5, 1)), allocations=True)
        self.assertEqual(fourth.installment, (4, 6))
        self.assertEqual(fourth.allocations, occurrences[3].allocations)
        self.assertEqual(
            list(
                schedule.installment_split(
                    3, [D("500.00"), D("333.33"), D("166.67")], D("166.70"), D("166.66")
                )
            ),
            [value for _category, value in fourth.allocations],
        )

    def test_fixed_split_repeats_the_source_split_and_unsplit_sources_keep_their_category(self):
        split = source(
            date(2026, 9, 15),
            "49.90",
            EARLY,
            is_fixed=True,
            category_id=1,
            splits=((1, D("30.00")), (2, D("19.90"))),
        )
        allocations = {
            occurrence.allocations
            for occurrence in expand(
                [split], months(date(2026, 10, 1), date(2027, 3, 1)), allocations=True
            )
        }
        self.assertEqual(allocations, {((1, D("30.00")), (2, D("19.90")))})
        plain = source(date(2026, 11, 5), "45.30", PIX, category_id=4)
        self.assertEqual(
            expand([plain], months(date(2026, 11, 1)), allocations=True)[0].allocations,
            ((4, D("45.30")),),
        )
        self.assertIsNone(expand([plain], months(date(2026, 11, 1)))[0].allocations)

    def test_largest_remainder_split(self):
        self.assertEqual(
            [
                str(value)
                for value in schedule.split_amount(D("432.10"), [D("300.00"), D("132.10")])
            ],
            ["300.00", "132.10"],
        )
        self.assertEqual(
            [str(value) for value in schedule.split_amount(D("0.10"), [D("1"), D("1"), D("1")])],
            ["0.04", "0.03", "0.03"],
        )
        self.assertEqual(
            [str(value) for value in schedule.split_amount(schedule.ZERO, [D("1"), D("2")])],
            ["0.00", "0.00"],
        )

    def test_allocations_need_split_capacities(self):
        item = source(date(2026, 1, 5), splits=None)
        with self.assertRaises(ValueError):
            expand([item], months(date(2026, 1, 1)), allocations=True)
        self.assertEqual(len(expand([item], months(date(2026, 1, 1)))), 1)


class TransactionWrapperTests(SimpleTestCase):
    """The Transaction helpers answer one month with the same rules as expand."""

    def setUp(self):
        self.account = BankAccount(id=10, currency="USD")
        self.debit = DebitCard(id=2, account=self.account)
        self.late = CreditCard(id=3, account=self.account, closing_day=30, due_day=7)

    def transaction(self, **values):
        values = {
            "id": 40,
            "title": "Synthetic",
            "amount": D("1000.00"),
            "transaction_type": "EXPENSE",
            "payment_channel": "ACCOUNT",
            "bank_account": self.account,
            "date": date(2026, 2, 27),
            "category_id": 6,
            **values,
        }
        return Transaction(**values)

    def cases(self):
        yield self.transaction()
        yield self.transaction(
            payment_channel="PIX",
            is_fixed=True,
            date=date(2026, 1, 31),
            fixed_until=date(2026, 9, 1),
        )
        yield self.transaction(
            payment_channel="DEBIT_CARD", bank_account=None, debit_card=self.debit, is_fixed=True
        )
        for override in (None, 0, 1):
            yield self.transaction(
                payment_channel="CREDIT_CARD",
                bank_account=None,
                credit_card=self.late,
                date=date(2026, 3, 30),
                installments=12,
                installment_start=3,
                billing_override=override,
            )
        yield self.transaction(
            payment_channel="CREDIT_CARD",
            bank_account=None,
            credit_card=self.late,
            date=date(2026, 1, 31),
            is_fixed=True,
            fixed_until=date(2026, 6, 1),
        )

    def test_month_helpers_equal_the_expanded_occurrences(self):
        for item in self.cases():
            with self.subTest(
                channel=item.payment_channel, fixed=item.is_fixed, override=item.billing_override
            ):
                found = {
                    occurrence.reference_month: occurrence
                    for occurrence in expand(
                        [item.schedule_source()], months(date(2025, 6, 1), date(2028, 6, 1))
                    )
                }
                for index in range(
                    schedule.month_index(date(2025, 6, 1)), schedule.month_index(date(2028, 7, 1))
                ):
                    month = schedule.month_at(index)
                    amount = item.amount_for_month(month.year, month.month)
                    occurrence = found.get(month)
                    self.assertEqual(str(amount), str(occurrence.amount) if occurrence else "0.00")
                first = min(found)
                if item.is_credit_card:
                    self.assertEqual(
                        item.billed_month,
                        self.late.statement_month(item.date, item.billing_override),
                    )
                    self.assertEqual(item.payment_date, self.late.due_date_for(item.billed_month))
                    self.assertEqual(found[first].cash_date, self.late.due_date_for(first))
                else:
                    self.assertEqual(
                        (item.billed_month, item.payment_date),
                        (item.date.replace(day=1), item.date),
                    )

    def test_schedule_source_describes_the_transaction(self):
        item = self.transaction(
            payment_channel="CREDIT_CARD",
            bank_account=None,
            credit_card=self.late,
            installments=6,
            installment_start=2,
            billing_override=1,
            is_fixed=False,
        )
        value = item.schedule_source()
        self.assertEqual(
            value,
            ScheduleSource(
                "transaction",
                40,
                date(2026, 2, 27),
                D("1000.00"),
                "USD",
                "EXPENSE",
                Instrument("CREDIT_CARD", 3, 10, 30, 7),
                False,
                None,
                6,
                2,
                1,
                6,
                None,
            ),
        )
        unsaved = self.transaction(
            id=None, payment_channel="DEBIT_CARD", bank_account=None, debit_card=self.debit
        )
        self.assertEqual(unsaved.schedule_source(splits=True).splits, ())
        self.assertEqual(unsaved.schedule_source().instrument, Instrument("DEBIT_CARD", 2, 10))


class CallerTests(SimpleTestCase):
    """The engine callers with unsaved synthetic values, so no query runs."""

    def setUp(self):
        self.account = BankAccount(id=10, currency="BRL")
        # The due day 7 is before the closing day 30: each statement is due
        # in the next month. The due day 12 is after the closing day 3.
        self.late = CreditCard(id=3, user_id=1, account=self.account, closing_day=30, due_day=7)
        self.early = CreditCard(id=4, user_id=1, account=self.account, closing_day=3, due_day=12)

    def purchase(self, when, card, **values):
        return Transaction(
            **{
                "user_id": 1,
                "title": "Synthetic",
                "amount": D("39.90"),
                "transaction_type": "EXPENSE",
                "category_id": 6,
                "payment_channel": "CREDIT_CARD",
                "credit_card": card,
                "date": when,
                **values,
            }
        )

    def test_billed_month_filter_export_and_preview_read_december_9999(self):
        fixed = self.purchase(date(2026, 1, 15), self.late, is_fixed=True)
        single = self.purchase(date(9999, 12, 1), self.late)
        early = self.purchase(date(9999, 12, 2), self.early)
        november = self.purchase(date(9999, 11, 2), self.late)
        self.assertEqual(
            _filter_transactions_by_billed_month([fixed, single, early, november], "9999-12"),
            [fixed, single, early],
        )
        # The CSV export reads the amount and the allocations of the month.
        occurrence = _billed_month_occurrence(fixed, 9999, 12, allocations=True)
        self.assertEqual(
            (str(occurrence.amount), occurrence.allocations, occurrence.cash_date),
            ("39.90", ((6, D("39.90")),), None),
        )
        # The effect preview shows no due date after 31 December 9999.
        self.assertEqual(
            [
                (effect["billed_month"], effect["payment_date"])
                for effect in map(financial_effect, (single, early, november))
            ],
            [
                (date(9999, 12, 1), None),
                (date(9999, 12, 1), date(9999, 12, 12)),
                (date(9999, 11, 1), date(9999, 12, 7)),
            ],
        )

    def test_a_legacy_stored_statement_day_counts_no_points_purchase(self):
        # Day 2 is before the closing day 3: each purchase is in the statement of its month.
        gym = self.purchase(date(2026, 11, 2), self.early, id=41, amount=D("99.00"), is_fixed=True)
        purchases = [
            SimpleNamespace(
                pk=pk,
                date=when,
                cash_amount=D("175.00"),
                funding_credit_card=self.early,
                funding_credit_card_id=4,
            )
            for pk, when in ((77, date(2033, 5, 2)), (78, date(2033, 6, 2)))
        ]
        payments = SimpleNamespace(
            all=lambda: [SimpleNamespace(amount=D("10.00"), date=date(2033, 5, 12))]
        )
        # CardInvoice.clean requires the first day of a month; the first stored
        # invoice is a legacy row with the day 15.
        stored = [
            SimpleNamespace(
                pk=pk,
                card_id=4,
                card=self.early,
                reference_month=reference,
                payments=payments,
                manual_settlement=False,
                paid_at=None,
            )
            for pk, reference in ((90, date(2033, 5, 15)), (91, date(2033, 6, 1)))
        ]
        plan = build_projection_plan(
            [gym], purchases, [], stored, date(2026, 11, 2), date(2027, 1, 31)
        )
        gross = {key: str(value["gross_amount"]) for key, value in plan["invoices"].items()}
        # The legacy day keeps the rule before the engine: the transaction
        # counts by month, the points purchase only on the exact date.
        self.assertEqual(
            gross,
            {
                (4, date(2026, 11, 1)): "99.00",
                (4, date(2026, 12, 1)): "99.00",
                (4, date(2027, 1, 1)): "99.00",
                (4, date(2033, 5, 15)): "99.00",
                (4, date(2033, 6, 1)): "274.00",
            },
        )


def imported_modules(path):
    """Return the modules that a source file imports; ``from banking import x`` imports ``banking.x``."""
    found = set()
    for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.update(
                f"{node.module}.{alias.name}" if node.module == "banking" else node.module
                for alias in node.names
            )
    return found


class PurityTests(SimpleTestCase):
    def test_engine_modules_import_only_the_standard_library_and_the_card_calendar(self):
        stdlib = set(sys.stdlib_module_names)
        for path, first_party in (
            ("ledger/schedule.py", {"banking.card_calendar"}),
            ("banking/card_calendar.py", set()),
        ):
            with self.subTest(path=path):
                modules = imported_modules(path)
                self.assertEqual(
                    {module for module in modules if module.partition(".")[0] not in stdlib},
                    first_party,
                )

    def test_importing_the_engine_loads_no_django_module(self):
        code = (
            "import json, sys; sys.path.insert(0, sys.argv[1]); import ledger.schedule; "
            'print(json.dumps(sorted(name for name in sys.modules if name.partition(".")[0] in '
            '{"django", "core", "accounts", "categories"} or name in {"banking.models", "ledger.models"})))'
        )
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(ROOT)],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        self.assertEqual(json.loads(result.stdout), [])


def fields_of(occurrence):
    """Return every field of an occurrence, with amount texts, for exact comparisons."""
    return (
        occurrence.key,
        occurrence.source_type,
        occurrence.source_id,
        occurrence.economic_date,
        occurrence.reference_month,
        occurrence.cash_date,
        str(occurrence.amount),
        occurrence.currency,
        occurrence.flow,
        occurrence.instrument,
        None
        if occurrence.allocations is None
        else tuple((category, str(value)) for category, value in occurrence.allocations),
        occurrence.installment,
        occurrence.status,
    )


class CommitmentEngineTests(SimpleTestCase):
    """R4: amount changes, month overrides and confirmation."""

    def rent(self, instrument=ACCOUNT, **values):
        return source(
            date(2026, 1, 31), "100.00", instrument, is_fixed=True, category_id=3, **values
        )

    def test_amount_steps_apply_from_their_month_until_the_next_step(self):
        item = self.rent(amounts=((date(2026, 3, 1), D("120.00")), (date(2026, 6, 1), D("90.50"))))
        found = expand([item], months(date(2026, 1, 1), date(2026, 7, 1)))
        self.assertEqual(
            [str(occurrence.amount) for occurrence in found],
            ["100.00", "100.00", "120.00", "120.00", "120.00", "90.50", "90.50"],
        )
        self.assertEqual({occurrence.status for occurrence in found}, {schedule.SCHEDULED})
        self.assertEqual(
            schedule.amount_steps(item),
            (
                (date(2026, 1, 1), D("100.00")),
                (date(2026, 3, 1), D("120.00")),
                (date(2026, 6, 1), D("90.50")),
            ),
        )
        self.assertEqual(
            [
                str(schedule.scheduled_amount(item, month))
                for month in (
                    date(2025, 12, 1),
                    date(2026, 2, 1),
                    date(2026, 3, 1),
                    date(2030, 1, 1),
                )
            ],
            ["100.00", "100.00", "120.00", "90.50"],
        )
        # A window that starts after a step reads that step (the bisect).
        (july,) = expand([item], months(date(2026, 7, 1)))
        self.assertEqual(str(july.amount), "90.50")

    def test_an_override_after_the_last_step_uses_its_own_amount_and_the_step_after_it(self):
        item = self.rent(
            amounts=((date(2026, 3, 1), D("120.00")),),
            overrides=(schedule.Override(date(2026, 5, 1), schedule.ADJUSTED, D("130.00")),),
        )
        found = expand([item], months(date(2026, 4, 1), date(2026, 6, 1)))
        self.assertEqual(
            [(str(occurrence.amount), occurrence.status) for occurrence in found],
            [
                ("120.00", schedule.SCHEDULED),
                ("130.00", schedule.ADJUSTED),
                ("120.00", schedule.SCHEDULED),
            ],
        )

    def test_a_skip_removes_the_month_unless_skipped_months_are_requested(self):
        item = self.rent(overrides=(schedule.Override(date(2026, 2, 1), schedule.SKIPPED),))
        window = months(date(2026, 1, 1), date(2026, 3, 1))
        self.assertEqual(
            [occurrence.key for occurrence in expand([item], window)],
            ["transaction:1:2026-01", "transaction:1:2026-03"],
        )
        skipped = expand([item], window, include_skipped=True)[1]
        self.assertEqual(
            (skipped.key, skipped.status, str(skipped.amount), skipped.cash_date),
            ("transaction:1:2026-02", schedule.SKIPPED, "100.00", date(2026, 2, 28)),
        )
        self.assertEqual(len(expand([item], Window.through(date(2026, 3, 31)))), 2)

    def test_adjusted_amount_date_and_both(self):
        cases = (
            (
                schedule.Override(date(2026, 2, 1), schedule.ADJUSTED, D("80.00")),
                ("80.00", date(2026, 2, 28)),
            ),
            (
                schedule.Override(date(2026, 2, 1), schedule.ADJUSTED, None, date(2026, 2, 3)),
                ("100.00", date(2026, 2, 3)),
            ),
            (
                schedule.Override(
                    date(2026, 2, 1), schedule.ADJUSTED, D("75.25"), date(2026, 2, 14)
                ),
                ("75.25", date(2026, 2, 14)),
            ),
        )
        for override, (amount, day) in cases:
            with self.subTest(override=override):
                (occurrence,) = expand([self.rent(overrides=(override,))], months(date(2026, 2, 1)))
                self.assertEqual(
                    (
                        str(occurrence.amount),
                        occurrence.cash_date,
                        occurrence.economic_date,
                        occurrence.status,
                        occurrence.key,
                    ),
                    (amount, day, day, schedule.ADJUSTED, "transaction:1:2026-02"),
                )

    def test_a_confirmation_dated_in_a_later_month_keeps_its_key_and_reference_month(self):
        item = self.rent(
            confirmation_start=date(2026, 2, 1),
            overrides=(
                schedule.Override(
                    date(2026, 2, 1), schedule.CONFIRMED, D("101.00"), date(2026, 3, 4)
                ),
            ),
        )
        found = expand([item], months(date(2026, 1, 1), date(2026, 3, 1)))
        self.assertEqual(
            [(occurrence.key, occurrence.status) for occurrence in found],
            [
                ("transaction:1:2026-01", schedule.SCHEDULED),
                ("transaction:1:2026-02", schedule.CONFIRMED),
                ("transaction:1:2026-03", schedule.EXPECTED),
            ],
        )
        confirmed = found[1]
        self.assertEqual(
            (
                confirmed.reference_month,
                confirmed.cash_date,
                confirmed.economic_date,
                str(confirmed.amount),
            ),
            (date(2026, 2, 1), date(2026, 3, 4), date(2026, 3, 4), "101.00"),
        )
        # In a synchronization window, the confirmed month needs its final cash date.
        self.assertEqual(
            [occurrence.key for occurrence in expand([item], Window.through(date(2026, 3, 3)))],
            ["transaction:1:2026-01"],
        )
        self.assertIn(
            "transaction:1:2026-02",
            [occurrence.key for occurrence in expand([item], Window.through(date(2026, 3, 4)))],
        )

    def test_expected_starts_at_the_confirmation_month_and_never_applies_to_a_card(self):
        item = self.rent(
            confirmation_start=date(2026, 3, 1),
            overrides=(schedule.Override(date(2026, 4, 1), schedule.ADJUSTED, D("99.00")),),
        )
        found = expand([item], months(date(2026, 2, 1), date(2026, 5, 1)))
        self.assertEqual(
            [(occurrence.status, str(occurrence.amount)) for occurrence in found],
            [
                (schedule.SCHEDULED, "100.00"),
                (schedule.EXPECTED, "100.00"),
                (schedule.EXPECTED, "99.00"),
                (schedule.EXPECTED, "100.00"),
            ],
        )
        card = self.rent(EARLY, confirmation_start=date(2026, 1, 1))
        self.assertEqual(
            {
                occurrence.status
                for occurrence in expand([card], months(date(2026, 1, 1), date(2026, 6, 1)))
            },
            {schedule.SCHEDULED},
        )

    def test_rows_of_installment_plans_and_legacy_fixed_rows_with_installments_are_ignored(self):
        rows = {
            "amounts": ((date(2026, 4, 1), D("1.00")),),
            "overrides": (schedule.Override(date(2026, 3, 1), schedule.SKIPPED),),
            "confirmation_start": date(2026, 1, 1),
        }
        for values in ({"installments": 6}, {"installments": 3, "is_fixed": True}):
            with self.subTest(values=values):
                window = months(date(2026, 1, 1), date(2026, 12, 1))
                plain = source(date(2026, 2, 27), "600.00", LATE, **values)
                with_rows = source(date(2026, 2, 27), "600.00", LATE, **values, **rows)
                self.assertEqual(
                    [fields_of(item) for item in expand([with_rows], window)],
                    [fields_of(item) for item in expand([plain], window)],
                )
                self.assertEqual(
                    schedule.amount_steps(with_rows), ((date(2026, 2, 1), D("600.00")),)
                )

    def test_rows_outside_the_window_or_the_schedule_are_ignored(self):
        item = self.rent(
            fixed_until=date(2026, 4, 30),
            amounts=((date(2027, 1, 1), D("5.00")),),
            overrides=(
                schedule.Override(date(2026, 8, 1), schedule.SKIPPED),
                schedule.Override(date(2025, 6, 1), schedule.ADJUSTED, D("3.00")),
            ),
        )
        found = expand([item], months(date(2025, 1, 1), date(2027, 6, 1)))
        self.assertEqual(
            [(occurrence.reference_month, str(occurrence.amount)) for occurrence in found],
            [(date(2026, month, 1), "100.00") for month in (1, 2, 3, 4)],
        )

    def test_through_window_last_month_uses_the_adjusted_cash_date(self):
        # The source day 31 is after the horizon, 2026-03-10; the adjusted date is not.
        moved = self.rent(
            overrides=(
                schedule.Override(date(2026, 3, 1), schedule.ADJUSTED, None, date(2026, 3, 9)),
            )
        )
        self.assertEqual(
            [
                occurrence.cash_date
                for occurrence in expand([moved], Window.through(date(2026, 3, 10)))
            ],
            [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 9)],
        )
        later = self.rent(
            overrides=(
                schedule.Override(date(2026, 2, 1), schedule.ADJUSTED, None, date(2026, 2, 27)),
            )
        )
        self.assertEqual(
            [
                occurrence.cash_date
                for occurrence in expand([later], Window.through(date(2026, 2, 26)))
            ],
            [date(2026, 1, 31)],
        )

    def test_split_cents_follow_the_final_amount_in_proportion(self):
        splits = ((1, D("66.67")), (2, D("33.33")))
        item = self.rent(
            splits=splits,
            amounts=((date(2026, 2, 1), D("100.01")),),
            overrides=(schedule.Override(date(2026, 3, 1), schedule.ADJUSTED, D("0.05")),),
        )
        found = expand([item], months(date(2026, 1, 1), date(2026, 3, 1)), allocations=True)
        self.assertEqual(
            [
                [(category, str(value)) for category, value in occurrence.allocations]
                for occurrence in found
            ],
            [
                [(1, "66.67"), (2, "33.33")],
                [(1, "66.68"), (2, "33.33")],
                [(1, "0.03"), (2, "0.02")],
            ],
        )
        for occurrence in found:
            self.assertEqual(
                sum((value for _category, value in occurrence.allocations), schedule.ZERO),
                occurrence.amount,
            )
        (plain,) = expand(
            [self.rent(amounts=((date(2026, 2, 1), D("7.00")),))],
            months(date(2026, 2, 1)),
            allocations=True,
        )
        self.assertEqual(plain.allocations, ((3, D("7.00")),))

    def test_statement_totals_use_final_amounts_and_drop_skipped_months(self):
        item = self.rent(
            EARLY,
            overrides=(
                schedule.Override(date(2026, 3, 1), schedule.ADJUSTED, D("40.00")),
                schedule.Override(date(2026, 4, 1), schedule.SKIPPED),
            ),
        )
        window = months(date(2026, 2, 1), date(2026, 4, 1))
        self.assertEqual(
            {key: str(value) for key, value in statement_totals(expand([item], window)).items()},
            {(4, date(2026, 2, 1)): "100.00", (4, date(2026, 3, 1)): "40.00"},
        )
        self.assertEqual(
            {
                key: str(value)
                for key, value in statement_totals(
                    expand([item], window, include_skipped=True)
                ).items()
            },
            {(4, date(2026, 2, 1)): "100.00", (4, date(2026, 3, 1)): "40.00"},
        )
        # A card month has no date override: its statement and due date stay.
        (march,) = expand([item], months(date(2026, 3, 1)))
        self.assertEqual(march.cash_date, schedule.statement_due_date(EARLY, date(2026, 3, 1)))

    def test_a_card_source_ignores_an_override_date(self):
        # clean() refuses such a date; the engine also ignores a row that bypassed it.
        plain = self.rent(EARLY)
        (expected,) = expand([plain], months(date(2026, 3, 1)))
        moved = self.rent(
            EARLY,
            overrides=(
                schedule.Override(
                    date(2026, 3, 1), schedule.ADJUSTED, D("40.00"), date(2026, 3, 2)
                ),
            ),
        )
        (march,) = expand([moved], months(date(2026, 3, 1)))
        self.assertEqual(
            (march.key, march.cash_date, march.economic_date, str(march.amount)),
            (expected.key, expected.cash_date, expected.economic_date, "40.00"),
        )
        self.assertNotEqual(march.cash_date, date(2026, 3, 2))

    def test_no_op_rows_take_the_commitments_path_with_fast_path_results(self):
        windows = (
            months(date(2025, 12, 1), date(2027, 2, 1)),
            Window.through(date(2026, 9, 15)),
            Window.through(date(2026, 9, 30)),
        )
        for instrument in (ACCOUNT, DEBIT, LATE, EARLY, MONTH_END):
            plain = self.rent(
                instrument, fixed_until=date(2026, 11, 1), splits=((3, D("60.00")), (4, D("40.00")))
            )
            no_ops = (
                {"amounts": ((date(2026, 5, 1), D("100.00")),)},
                {"overrides": (schedule.Override(date(2030, 1, 1), schedule.SKIPPED),)},
                {"confirmation_start": date(2031, 1, 1)},
            )
            for values in no_ops:
                variant = ScheduleSource(
                    **{**{name: getattr(plain, name) for name in plain.__slots__}, **values}
                )
                for window in windows:
                    with self.subTest(channel=instrument.channel, rows=values, window=window):
                        self.assertEqual(
                            [
                                fields_of(item)
                                for item in expand([variant], window, allocations=True)
                            ],
                            [fields_of(item) for item in expand([plain], window, allocations=True)],
                        )
