"""Reward redemptions coverage for banking."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from banking.models import BankMovement, CreditCard, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from banking.services import create_reward_redemption
from banking.tests.factories import make_account


User = get_user_model()


class RewardRedemptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('rewards')
        self.target = make_account(self.user, name='Target')
        self.iof = make_account(self.user, name='IOF', opening='10.00')
        self.card = CreditCard.objects.create(
            user=self.user,
            account=self.iof,
            name='IOF card',
            closing_day=10,
            due_day=20,
        )
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Rewards')
        LoyaltyEntry.objects.create(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.ADJUSTMENT,
            amount=Decimal('1000.00'),
            date=date.today(),
        )

    def redeem(self, **kwargs):
        values = {
            'user': self.user,
            'program': self.program,
            'points': Decimal('100.00'),
            'target_account': self.target,
            'target_amount': Decimal('25.00'),
            'date': timezone.localdate(),
        }
        values.update(kwargs)
        return create_reward_redemption(**values)

    def test_redemption_creates_points_debit_and_target_reward_credit(self):
        redemption = self.redeem()
        self.assertEqual(self.program.balance, Decimal('900.00'))
        self.assertEqual(self.target.current_balance(), Decimal('25.00'))
        self.assertFalse(redemption.has_pending_credit_card_iof)
        self.assertEqual(
            BankMovement.objects.get(account=self.target).kind,
            BankMovement.Kind.REWARD,
        )

    def test_account_funded_iof_creates_immediate_expense_debit(self):
        self.redeem(iof_amount=Decimal('2.00'), iof_account=self.iof)
        self.assertEqual(self.iof.current_balance(), Decimal('8.00'))
        movement = BankMovement.objects.get(account=self.iof)
        self.assertEqual((movement.direction, movement.kind), ('DEBIT', 'EXPENSE'))

    def test_credit_card_iof_is_persisted_and_explicitly_pending(self):
        redemption = self.redeem(
            iof_amount=Decimal('2.00'), iof_credit_card=self.card
        )
        self.assertTrue(redemption.has_pending_credit_card_iof)
        self.assertFalse(BankMovement.objects.filter(account=self.iof).exists())

    def test_iof_requires_exactly_one_instrument_or_none_for_zero(self):
        invalid_values = (
            {'iof_amount': Decimal('1.00')},
            {'iof_amount': Decimal('1.00'), 'iof_account': self.iof, 'iof_credit_card': self.card},
            {'iof_amount': Decimal('0.00'), 'iof_account': self.iof},
        )
        for values in invalid_values:
            redemption = RewardRedemption(
                user=self.user,
                program=self.program,
                points=1,
                target_account=self.target,
                target_amount=1,
                date=date.today(),
                **values,
            )
            with self.subTest(values=values), self.assertRaises(ValidationError):
                redemption.full_clean()

    def test_redemption_rejects_insufficient_points(self):
        with self.assertRaises(ValidationError):
            self.redeem(points=Decimal('1001.00'))
