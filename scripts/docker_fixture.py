# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic v0.3.0-compatible records for disposable Docker upgrade rehearsals."""

SEED = r'''
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from accounts.models import UserPreference
from banking.models import Bank, BankAccount, CreditCard, ExchangeRate, LoyaltyProgram, LoyaltyEntry
from banking.services import create_transfer
from categories.models import Category
from investments.models import Asset, InvestmentProduct, Investment
from investments.services import refresh_fx_snapshot, sync_investment_ledger
from transactions.models import Transaction
from transactions.services import sync_user_ledger
user = get_user_model().objects.create_user('docker-persistence', password='Disposable-upgrade-check-2026!')
other = get_user_model().objects.create_user('docker-other-owner')
UserPreference.objects.update_or_create(user=user, defaults={'date_format': 'MDY', 'base_currency': 'BRL'})
bank = Bank.objects.create(user=user, name='Disposable bank')
account = BankAccount.objects.create(user=user, bank=bank, name='Rehearsal', currency='BRL', opening_balance='12345.67')
dollars = BankAccount.objects.create(user=user, bank=bank, name='Retained dollars', currency='USD', opening_balance='321.45')
other_bank = Bank.objects.create(user=other, name='Private other bank')
BankAccount.objects.create(user=other, bank=other_bank, name='Other account', currency='BRL', opening_balance='777.00')
category = Category.objects.create(user=user, name='Synthetic commitments', transaction_type='EXPENSE')
income_category = Category.objects.create(user=user, name='Synthetic pay', transaction_type='INCOME')
card = CreditCard.objects.create(user=user, account=account, name='Cycle card', closing_day=20, due_day=5)
for values in (
    dict(title='Opening-month salary', amount='4200.00', transaction_type='INCOME', category=income_category, payment_channel='ACCOUNT', bank_account=account, date=date(2026, 8, 3)),
    dict(title='Ambiguous display date', amount='18.75', transaction_type='EXPENSE', category=category, payment_channel='ACCOUNT', bank_account=account, date=date(2026, 4, 3)),
    dict(title='Future installments', amount='600.01', transaction_type='EXPENSE', category=category, payment_channel='CREDIT_CARD', credit_card=card, date=date(2026, 8, 21), installments=6),
    dict(title='Fixed commitment', amount='59.90', transaction_type='EXPENSE', category=category, payment_channel='ACCOUNT', bank_account=account, date=date(2026, 8, 10), is_fixed=True, fixed_until=date(2027, 3, 10)),
):
    record = Transaction(user=user, **values)
    record.full_clean()
    record.save()
ExchangeRate.objects.create(user=user, from_currency='USD', to_currency='BRL', rate='5.12345678', effective_date=date(2026, 8, 1))
create_transfer(user=user, source_account=account, destination_account=dollars, source_amount=Decimal('512.35'), destination_amount=Decimal('100'), date=date(2026, 8, 5))
product = InvestmentProduct.objects.create(user=user, bank=bank, name='Existing investments')
second_product = InvestmentProduct.objects.create(user=user, bank=bank, name='Second product')
pot = Asset.objects.create(user=user, name='Existing monetary position', code='CASH-POSITION', currency='BRL', asset_class='LIQUIDITY', valuation_mode='MONETARY', opening_balance='1000.00', opening_product=product)
pot.refresh_from_db()
Asset.objects.create(user=user, name='Existing units', code='UNIT-POSITION', currency='USD', asset_class='EQUITY', valuation_mode='UNITS', opening_quantity='3.125', opening_unit_price='20.50', opening_product=product)
for values in (
    dict(product=product, kind='DEPOSIT', amount='500.00', cash_amount='500.00', source_account=account, date=date(2026, 8, 6)),
    dict(product=second_product, kind='DEPOSIT', amount='100.00', cash_amount='100.00', source_account=account, date=date(2026, 8, 6)),
    dict(product=product, kind='YIELD', amount='15.25', date=date(2026, 8, 7)),
    dict(product=product, kind='WITHDRAWAL', amount='200.00', cash_amount='200.00', destination_account=account, date=date(2026, 8, 8)),
):
    operation = Investment(user=user, asset=pot, **values)
    operation.full_clean()
    operation.save()
    refresh_fx_snapshot(operation)
    sync_investment_ledger(operation)
program = LoyaltyProgram.objects.create(user=user, bank=bank, name='Retained rewards')
LoyaltyEntry.objects.create(user=user, program=program, direction='CREDIT', kind='ADJUSTMENT', amount='1200.00', date=date(2026, 8, 1))
sync_user_ledger(user, through_date=date(2026, 9, 20))
'''

MODELS = (
    'auth.User', 'accounts.UserPreference', 'categories.Category',
    'banking.Bank', 'banking.BankAccount', 'banking.CreditCard',
    'banking.ExchangeRate', 'banking.BankTransfer', 'banking.BankMovement',
    'banking.CardInvoice', 'banking.LoyaltyProgram', 'banking.LoyaltyEntry',
    'transactions.Transaction', 'investments.InvestmentProduct',
    'investments.Asset', 'investments.Investment',
)


def snapshot_code(fields=None):
    """Compare every pre-upgrade field, including IDs and historical FX evidence."""
    return f'''
import json
from datetime import date
from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
spec = {fields!r}
if spec is None:
    spec = {{label: [field.attname for field in apps.get_model(label)._meta.concrete_fields
                   if field.name not in ('created_at', 'updated_at', 'last_login')]
            for label in {MODELS!r}}}
records = {{label: list(apps.get_model(label).objects.order_by('pk').values(*names))
           for label, names in spec.items()}}
balances = {{str(account.pk): account.current_balance(as_of=date(2026, 9, 20))
            for account in apps.get_model('banking.BankAccount').objects.all()}}
points = {{str(program.pk): program.balance
          for program in apps.get_model('banking.LoyaltyProgram').objects.all()}}
print('TUXEDO_SNAPSHOT=' + json.dumps({{'fields': spec, 'records': records, 'balances': balances, 'points': points}}, cls=DjangoJSONEncoder, sort_keys=True))
'''


CHECK_DEFAULTS = r'''
from decimal import Decimal
from django.contrib.auth import get_user_model
from banking.models import BankAccount
from investments.models import InvestmentProduct
user = get_user_model().objects.get(username='docker-persistence')
assert user.check_password('Disposable-upgrade-check-2026!')
if hasattr(BankAccount, 'planning_enabled'):
    assert not BankAccount.objects.filter(planning_enabled=False).exists()
    assert not BankAccount.objects.exclude(reserved_amount=Decimal('0')).exists()
if hasattr(InvestmentProduct, 'Purpose'):
    assert not InvestmentProduct.objects.exclude(purpose=InvestmentProduct.Purpose.INVESTMENT).exists()
'''
