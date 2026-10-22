"""Cards invoices coverage for banking."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from banking.models import CardInvoice, CreditCard
from banking.tests.factories import make_account


User = get_user_model()


class CardAndInvoiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('cards')
        self.account = make_account(self.user)
        self.card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Platinum',
            closing_day=31,
            due_day=31,
        )

    def test_statement_month_clamps_closing_day_in_short_month(self):
        self.assertEqual(self.card.statement_month(date(2025, 2, 27)), date(2025, 2, 1))
        self.assertEqual(self.card.statement_month(date(2025, 2, 28)), date(2025, 3, 1))

    def test_best_purchase_day_matches_the_configured_closing_day(self):
        self.assertEqual(self.card.best_purchase_day, 31)
        self.card.closing_day = 24
        self.assertEqual(self.card.best_purchase_day, 24)

    def test_statement_override_preserves_explicit_current_or_next(self):
        purchase = date(2026, 1, 31)
        self.assertEqual(self.card.statement_month(purchase, override=0), date(2026, 1, 1))
        self.assertEqual(self.card.statement_month(purchase, override=1), date(2026, 2, 1))
        with self.assertRaises(ValueError):
            self.card.statement_month(purchase, override=2)

    def test_due_date_clamps_short_month(self):
        self.assertEqual(self.card.due_date_for(date(2024, 2, 18)), date(2024, 2, 29))

    def test_due_date_moves_to_next_month_when_due_day_precedes_closing_day(self):
        self.card.closing_day = 24
        self.card.due_day = 1
        self.assertEqual(self.card.due_date_for(date(2026, 8, 1)), date(2026, 9, 1))

    def test_invoice_requires_first_day_and_is_unique_per_card_month(self):
        invalid = CardInvoice(
            user=self.user,
            card=self.card,
            reference_month=date(2026, 1, 2),
            due_date=date(2026, 1, 31),
            amount=Decimal('0.00'),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        CardInvoice.objects.create(
            user=self.user,
            card=self.card,
            reference_month=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            amount=Decimal('0.00'),
        )
        with self.assertRaises(IntegrityError):
            CardInvoice.objects.create(
                user=self.user,
                card=self.card,
                reference_month=date(2026, 1, 1),
                due_date=date(2026, 1, 31),
                amount=Decimal('1.00'),
            )

    def test_invoice_is_aggregate_and_account_property_is_linked_account(self):
        invoice = CardInvoice.objects.create(
            user=self.user,
            card=self.card,
            reference_month=date(2026, 2, 1),
            due_date=date(2026, 2, 28),
            amount=Decimal('200.00'),
        )
        self.assertEqual(invoice.account, self.account)
        self.assertEqual(self.account.current_balance(), Decimal('0.00'))
