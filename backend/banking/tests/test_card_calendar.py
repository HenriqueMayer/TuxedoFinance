"""Unit tests of the credit-card statement calendar, banking.card_calendar.

The functions are pure, so these tests use SimpleTestCase: a database query
fails the test. The cards are unsaved synthetic values.
"""

from calendar import monthrange
from datetime import date, timedelta

from django.test import SimpleTestCase

from banking.card_calendar import days_in_month, due_date, due_month_offset, statement_month
from banking.models import CreditCard


class StatementMonthTests(SimpleTestCase):
    def test_purchase_on_or_after_the_closing_day_goes_to_the_next_statement(self):
        self.assertEqual(statement_month(24, date(2026, 1, 23)), date(2026, 1, 1))
        self.assertEqual(statement_month(24, date(2026, 1, 24)), date(2026, 2, 1))
        self.assertEqual(statement_month(24, date(2026, 12, 31)), date(2027, 1, 1))

    def test_closing_day_is_clamped_to_the_month_length(self):
        cases = (
            # February of a common year has 28 days, of a leap year 29.
            (31, date(2026, 2, 27), date(2026, 2, 1)),
            (31, date(2026, 2, 28), date(2026, 3, 1)),
            (31, date(2028, 2, 28), date(2028, 2, 1)),
            (31, date(2028, 2, 29), date(2028, 3, 1)),
            (30, date(2028, 2, 29), date(2028, 3, 1)),
            (29, date(2026, 2, 28), date(2026, 3, 1)),
            (29, date(2028, 2, 28), date(2028, 2, 1)),
            # April has 30 days.
            (31, date(2026, 4, 29), date(2026, 4, 1)),
            (31, date(2026, 4, 30), date(2026, 5, 1)),
            (30, date(2026, 1, 29), date(2026, 1, 1)),
            (30, date(2026, 1, 31), date(2026, 2, 1)),
        )
        for closing_day, purchase, expected in cases:
            with self.subTest(closing_day=closing_day, purchase=purchase):
                self.assertEqual(statement_month(closing_day, purchase), expected)

    def test_bill_choice_overrides_the_closing_day(self):
        self.assertEqual(statement_month(30, date(2026, 10, 31), 0), date(2026, 10, 1))
        self.assertEqual(statement_month(30, date(2026, 11, 2), 1), date(2026, 12, 1))
        self.assertEqual(statement_month(3, date(2026, 12, 2), 1), date(2027, 1, 1))

    def test_other_overrides_raise_value_error(self):
        for override in (2, -1, "next"):
            with self.subTest(override=override), self.assertRaises(ValueError):
                statement_month(10, date(2026, 1, 5), override)

    def test_statement_month_after_9999_raises_value_error(self):
        with self.assertRaises(ValueError):
            statement_month(30, date(9999, 12, 31))
        self.assertEqual(statement_month(30, date(9999, 12, 29)), date(9999, 12, 1))


class DueDateTests(SimpleTestCase):
    def test_due_day_after_the_closing_day_is_in_the_statement_month(self):
        self.assertEqual(due_date(3, 12, date(2026, 10, 1)), date(2026, 10, 12))
        self.assertEqual(due_date(3, 12, date(2026, 10, 20)), date(2026, 10, 12))
        # Equal days are not "before": the same month.
        self.assertEqual(due_date(10, 10, date(2026, 10, 1)), date(2026, 10, 10))

    def test_due_day_before_the_closing_day_is_in_the_next_month(self):
        self.assertEqual(due_date(24, 1, date(2026, 8, 1)), date(2026, 9, 1))
        self.assertEqual(due_date(30, 7, date(2026, 12, 1)), date(2027, 1, 7))

    def test_due_day_is_clamped_to_the_month_length(self):
        self.assertEqual(due_date(20, 31, date(2026, 2, 1)), date(2026, 2, 28))
        self.assertEqual(due_date(20, 31, date(2028, 2, 1)), date(2028, 2, 29))
        self.assertEqual(due_date(20, 30, date(2026, 4, 1)), date(2026, 4, 30))
        # Due in the next month, which is February.
        self.assertEqual(due_date(31, 30, date(2026, 1, 1)), date(2026, 2, 28))
        self.assertEqual(due_date(31, 29, date(2028, 1, 1)), date(2028, 2, 29))

    def test_due_month_offset(self):
        # Only a due day before the closing day moves the due month.
        self.assertEqual(due_month_offset(24, 1), 1)
        self.assertEqual((due_month_offset(10, 10), due_month_offset(3, 12)), (0, 0))

    def test_due_date_after_9999_raises_value_error(self):
        # A card due in the month after the statement month has its December
        # 9999 statement due in January 10000.
        with self.assertRaises(ValueError):
            due_date(30, 7, date(9999, 12, 1))
        with self.assertRaises(ValueError):
            CreditCard(closing_day=30, due_day=7).due_date_for(date(9999, 12, 15))
        self.assertEqual(due_date(30, 7, date(9999, 11, 1)), date(9999, 12, 7))
        self.assertEqual(due_date(3, 12, date(9999, 12, 1)), date(9999, 12, 12))


class CalendarHelperTests(SimpleTestCase):
    def test_days_in_month_equals_calendar_monthrange(self):
        for year in (1, 1900, 2000, 2024, 2026, 2100, 9999):
            for month in range(1, 13):
                with self.subTest(year=year, month=month):
                    self.assertEqual(days_in_month(year, month), monthrange(year, month)[1])

    def test_credit_card_methods_call_the_calendar(self):
        card = CreditCard(closing_day=30, due_day=7)
        day = date(2025, 12, 1)
        for _ in range(800):
            with self.subTest(day=day):
                for override in (None, 0, 1):
                    self.assertEqual(
                        card.statement_month(day, override=override),
                        statement_month(30, day, override),
                    )
                self.assertEqual(card.due_date_for(day), due_date(30, 7, day))
            day += timedelta(days=1)
