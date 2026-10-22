"""Balances coverage for banking."""

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from banking.models import BankMovement
from banking.services import create_movement
from banking.tests.factories import make_account


User = get_user_model()


class BalanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('balance', password='test')
        self.account = make_account(self.user, opening='100.00')

    def movement(self, direction, amount, on):
        return create_movement(
            user=self.user,
            account=self.account,
            direction=direction,
            kind=BankMovement.Kind.ADJUSTMENT,
            amount=Decimal(amount),
            effective_date=on,
        )

    def test_balance_uses_opening_and_signed_movements_through_date(self):
        self.movement(BankMovement.Direction.CREDIT, '25.00', date(2026, 1, 10))
        self.movement(BankMovement.Direction.DEBIT, '8.00', date(2026, 1, 20))
        self.assertEqual(self.account.current_balance(date(2026, 1, 15)), Decimal('125.00'))
        self.assertEqual(self.account.current_balance(date(2026, 1, 20)), Decimal('117.00'))

    def test_current_balance_excludes_future_movements(self):
        self.movement(
            BankMovement.Direction.CREDIT,
            '999.00',
            timezone.localdate() + timedelta(days=1),
        )
        self.assertEqual(self.account.current_balance(), Decimal('100.00'))

    def test_movement_affects_balance_immediately_on_effective_date(self):
        today = timezone.localdate()
        self.movement(BankMovement.Direction.DEBIT, '12.50', today)
        self.assertEqual(self.account.current_balance(), Decimal('87.50'))
