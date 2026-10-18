"""Ownership coverage for banking."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from banking.models import Bank, BankAccount, BankMovement, CreditCard, DebitCard
from banking.tests.factories import make_account


User = get_user_model()


class OwnershipAndConstraintTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', password='test')
        self.other = User.objects.create_user('other', password='test')
        self.account = make_account(self.user)

    def test_bank_name_is_unique_per_user_only(self):
        Bank.objects.create(user=self.other, name='Nubank')
        with self.assertRaises(IntegrityError):
            Bank.objects.create(user=self.user, name='Nubank')

    def test_account_rejects_bank_from_another_owner(self):
        foreign_bank = Bank.objects.create(user=self.other, name='Private')
        account = BankAccount(
            user=self.user, bank=foreign_bank, name='Forged', currency='BRL'
        )
        with self.assertRaises(ValidationError):
            account.full_clean()

    def test_cards_reject_account_from_another_owner(self):
        for model, extra in (
            (DebitCard, {}),
            (CreditCard, {'closing_day': 10, 'due_day': 20}),
        ):
            card = model(user=self.other, account=self.account, name=model.__name__, **extra)
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                card.full_clean()

    def test_positive_amount_database_checks(self):
        with self.assertRaises(IntegrityError):
            BankMovement.objects.create(
                user=self.user,
                account=self.account,
                direction=BankMovement.Direction.CREDIT,
                kind=BankMovement.Kind.ADJUSTMENT,
                amount=Decimal('0.00'),
                effective_date=date.today(),
            )
