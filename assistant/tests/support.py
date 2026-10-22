# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic financial fixtures, never installation data."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from accounts.models import UserPreference
from banking.models import Bank, BankAccount, BankMovement
from categories.models import Category
from transactions.models import Transaction


def make_owner(name):
    user = get_user_model().objects.create_user(username=name, password='synthetic-password')
    UserPreference.objects.create(user=user, base_currency='USD')
    return user


def make_finances(user, name='Owned', currency='BRL'):
    bank = Bank.objects.create(user=user, name=f'{name} bank')
    account = BankAccount.objects.create(user=user, bank=bank, name=f'{name} account', currency=currency,
                                         opening_balance=Decimal('100.00'), opening_date=date(2026, 10, 1))
    category = Category.objects.create(user=user, name=f'{name} category')
    item = Transaction.objects.create(user=user, title=f'{name} purchase', amount=Decimal('12.34'),
                                      transaction_type='EXPENSE', category=category, payment_channel='ACCOUNT',
                                      bank_account=account, date=date(2026, 10, 10), notes='DO NOT COPY PRIVATE NOTES')
    BankMovement.objects.create(user=user, account=account, direction='DEBIT', kind='EXPENSE',
                                amount=Decimal('12.34'), effective_date=date(2026, 10, 10),
                                description='DO NOT COPY RAW DESCRIPTION')
    return bank, account, category, item
