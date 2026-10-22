"""Loyalty funding coverage for banking."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from banking.models import CreditCard, LoyaltyEntry, LoyaltyProgram
from banking.services import sync_loyalty_entry_funding
from banking.tests.factories import make_account


User = get_user_model()


class LoyaltyPurchaseFundingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('point-purchase')
        self.account = make_account(self.user, opening='100.00')
        self.card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Rewards Card',
            closing_day=10,
            due_day=20,
        )
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Miles')

    def test_account_funded_purchase_debits_balance_once(self):
        entry = LoyaltyEntry.objects.create(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.PURCHASE,
            amount=Decimal('1000.00'),
            cash_amount=Decimal('25.00'),
            funding_account=self.account,
            date=timezone.localdate(),
        )
        sync_loyalty_entry_funding(entry)
        sync_loyalty_entry_funding(entry)

        entry.refresh_from_db()
        self.assertEqual(self.account.current_balance(), Decimal('75.00'))
        self.assertEqual(entry.funding_movement.source_key, f'loyalty-entry:{entry.pk}')

    def test_card_funded_purchase_has_no_immediate_movement(self):
        entry = LoyaltyEntry(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.PURCHASE,
            amount=Decimal('1000.00'),
            cash_amount=Decimal('25.00'),
            funding_credit_card=self.card,
            date=timezone.localdate(),
        )
        entry.full_clean()
        entry.save()
        sync_loyalty_entry_funding(entry)

        self.assertIsNone(entry.funding_movement)
        self.assertEqual(self.account.current_balance(), Decimal('100.00'))

    def test_invoice_award_must_be_credit(self):
        entry = LoyaltyEntry(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.DEBIT,
            kind=LoyaltyEntry.Kind.INVOICE_AWARD,
            amount=Decimal('10.00'),
            date=timezone.localdate(),
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()
