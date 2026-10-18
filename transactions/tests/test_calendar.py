"""Calendar coverage for transactions."""

from datetime import date
from decimal import Decimal
from transactions.models import Transaction
from transactions.tests.fixtures import TransactionFixture


class TransactionCalendarTests(TransactionFixture):
    def credit_transaction(self, **overrides):
        return self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
            **overrides,
        )

    def test_card_payment_date_is_due_date_even_at_zero_offset(self):
        item = self.credit_transaction(date=date(2026, 1, 10))
        self.assertEqual(item.billing_offset, 0)
        self.assertEqual(item.payment_date, date(2026, 1, 31))

    def test_statement_offset_and_short_due_month_are_clamped(self):
        item = self.credit_transaction(date=date(2026, 1, 24))
        self.assertEqual(item.billed_month, date(2026, 2, 1))
        self.assertEqual(item.payment_date, date(2026, 2, 28))

    def test_billing_override_wins(self):
        current = self.credit_transaction(
            date=date(2026, 1, 25), billing_override=Transaction.BillChoice.CURRENT
        )
        self.assertEqual(current.billed_month, date(2026, 1, 1))

    def test_installments_round_to_exact_total(self):
        item = self.credit_transaction(amount=Decimal('100.00'), installments=3)
        amounts = [item.amount_for_month(2026, month) for month in (1, 2, 3)]
        self.assertEqual(amounts, [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')])
        self.assertEqual(sum(amounts), item.amount)

    def test_installment_rounding_remainder_is_added_to_first_installment(self):
        item = self.credit_transaction(amount=Decimal('339.80'), installments=3)

        amounts = [item.amount_for_month(2026, month) for month in (1, 2, 3)]

        self.assertEqual(amounts, [Decimal('113.28'), Decimal('113.26'), Decimal('113.26')])
        self.assertEqual(item.amount_through_month(2026, 1), Decimal('113.28'))
        self.assertEqual(item.amount_through_month(2026, 2), Decimal('226.54'))
        self.assertEqual(sum(amounts), item.amount)
