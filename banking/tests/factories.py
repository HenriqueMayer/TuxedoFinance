"""Factories coverage for banking."""

from decimal import Decimal
from banking.models import Bank, BankAccount


def make_account(user, *, bank_name='Nubank', name='Checking', currency='BRL', opening='0.00'):
    bank, _ = Bank.objects.get_or_create(user=user, name=bank_name)
    return BankAccount.objects.create(
        user=user,
        bank=bank,
        name=name,
        currency=currency,
        opening_balance=Decimal(opening),
    )
