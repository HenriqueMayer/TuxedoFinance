"""Transfers coverage for banking."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from banking.models import BankMovement, BankTransfer
from banking.services import create_transfer
from banking.tests.factories import make_account


User = get_user_model()


class TransferTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('transfer', password='test')
        self.source = make_account(self.user, name='Source', opening='100.00')
        self.destination = make_account(self.user, name='Destination', opening='20.00')

    def test_transfer_creates_linked_debit_credit_pair_and_is_neutral(self):
        transfer = create_transfer(
            user=self.user,
            source_account=self.source,
            destination_account=self.destination,
            source_amount=Decimal('30.00'),
            destination_amount=Decimal('30.00'),
            date=timezone.localdate(),
            notes='Own transfer',
        )
        movements = list(transfer.movements.order_by('direction'))
        self.assertEqual(len(movements), 2)
        self.assertEqual({m.kind for m in movements}, {BankMovement.Kind.TRANSFER})
        self.assertEqual(self.source.current_balance(), Decimal('70.00'))
        self.assertEqual(self.destination.current_balance(), Decimal('50.00'))
        self.assertEqual(
            self.source.current_balance() + self.destination.current_balance(),
            Decimal('120.00'),
        )

    def test_cross_currency_transfer_preserves_two_native_amounts(self):
        usd = make_account(self.user, name='USD', currency='USD')
        transfer = create_transfer(
            user=self.user,
            source_account=self.source,
            destination_account=usd,
            source_amount=Decimal('50.00'),
            destination_amount=Decimal('10.00'),
            date=timezone.localdate(),
        )
        self.assertEqual(transfer.source_amount, Decimal('50.00'))
        self.assertEqual(transfer.destination_amount, Decimal('10.00'))
        self.assertEqual(usd.current_balance(), Decimal('10.00'))

    def test_transfer_rejects_same_account_and_different_owner(self):
        same = BankTransfer(
            user=self.user,
            source_account=self.source,
            destination_account=self.source,
            source_amount=1,
            destination_amount=1,
            date=date.today(),
        )
        with self.assertRaises(ValidationError):
            same.full_clean()
        other = User.objects.create_user('transfer-other')
        foreign = make_account(other)
        with self.assertRaises(ValidationError):
            create_transfer(
                user=self.user,
                source_account=self.source,
                destination_account=foreign,
                source_amount=1,
                destination_amount=1,
                date=date.today(),
            )
