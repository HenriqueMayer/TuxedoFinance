"""Create disposable, localized data used only by preview screenshot capture."""

from __future__ import annotations

import os
import sys
from calendar import monthrange
from datetime import date
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django

django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone, translation

from accounts.models import UserPreference
from banking.models import (
    Bank,
    BankAccount,
    CreditCard,
    DebitCard,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
)
from banking.services import create_transfer
from categories.models import Category
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import refresh_fx_snapshot, sync_investment_ledger
from transactions.models import Transaction
from transactions.services import sync_user_ledger


COPY = {
    'en': {
        'username': 'preview-en',
        'date_format': 'MDY',
        'salary': 'Monthly salary',
        'housing': 'Housing',
        'rent': 'Apartment rent',
        'groceries': 'Groceries',
        'market': 'Weekly groceries',
        'utilities': 'Utilities',
        'energy': 'Energy and internet',
        'subscriptions': 'Subscriptions',
        'streaming': 'Streaming plan',
        'travel': 'Travel',
        'flight': 'Flight tickets',
        'technology': 'Technology',
        'laptop': 'Notebook computer',
        'checking': 'Everyday checking',
        'savings': 'Goals savings',
        'global': 'Global account',
        'debit': 'Everyday debit',
        'credit': 'Demo rewards card',
        'loyalty': 'Demo Miles',
        'brokerage': 'Demo Brokerage',
        'reserve': 'Reserve Fund',
        'equity': 'Global Equity ETF',
        'transfer': 'Monthly savings allocation',
        'investment_reason': 'Long-term allocation',
        'yield_reason': 'Monthly yield',
    },
    'pt-br': {
        'username': 'preview-pt',
        'date_format': 'DMY',
        'salary': 'Salário mensal',
        'housing': 'Moradia',
        'rent': 'Aluguel do apartamento',
        'groceries': 'Mercado',
        'market': 'Compras da semana',
        'utilities': 'Contas da casa',
        'energy': 'Energia e internet',
        'subscriptions': 'Assinaturas',
        'streaming': 'Plano de streaming',
        'travel': 'Viagens',
        'flight': 'Passagens aéreas',
        'technology': 'Tecnologia',
        'laptop': 'Notebook',
        'checking': 'Conta do dia a dia',
        'savings': 'Reserva para objetivos',
        'global': 'Conta global',
        'debit': 'Débito cotidiano',
        'credit': 'Cartão de recompensas',
        'loyalty': 'Milhas Demo',
        'brokerage': 'Corretora Demo',
        'reserve': 'Fundo de Reserva',
        'equity': 'ETF Global de Ações',
        'transfer': 'Aporte mensal na reserva',
        'investment_reason': 'Alocação de longo prazo',
        'yield_reason': 'Rendimento mensal',
    },
}


def add_months(value: date, offset: int, day: int | None = None) -> date:
    index = value.year * 12 + value.month - 1 + offset
    year, zero_based_month = divmod(index, 12)
    month = zero_based_month + 1
    requested_day = value.day if day is None else day
    return date(year, month, min(requested_day, monthrange(year, month)[1]))


def validate_capture_environment() -> str:
    if os.environ.get('PREVIEW_CAPTURE') != '1':
        raise SystemExit('Refusing to seed data without PREVIEW_CAPTURE=1.')
    password = os.environ.get('PREVIEW_PASSWORD', '')
    if not password:
        raise SystemExit('PREVIEW_PASSWORD is required for disposable users.')
    data_dir_value = os.environ.get('TUXEDO_DATA_DIR', '')
    if not data_dir_value:
        raise SystemExit('TUXEDO_DATA_DIR must point to the disposable preview directory.')
    data_dir = Path(data_dir_value).resolve()
    if data_dir == PROJECT_ROOT or PROJECT_ROOT in data_dir.parents:
        raise SystemExit('Refusing to use a data directory inside the project workspace.')
    if not data_dir.name.startswith('tuxedo-preview-data.'):
        raise SystemExit('Preview data directory does not have the expected safe prefix.')
    return password


def make_category(user, name: str, transaction_type: str) -> Category:
    return Category.objects.create(
        user=user,
        name=name,
        transaction_type=transaction_type,
    )


def make_transaction(
    *, user, title: str, amount: str, transaction_type: str, category: Category,
    transaction_date: date, payment_channel: str, bank_account=None,
    debit_card=None, credit_card=None, installments: int = 1, is_fixed: bool = False,
) -> Transaction:
    item = Transaction(
        user=user,
        title=title,
        amount=Decimal(amount),
        transaction_type=transaction_type,
        category=category,
        payment_channel=payment_channel,
        bank_account=bank_account,
        debit_card=debit_card,
        credit_card=credit_card,
        installments=installments,
        is_fixed=is_fixed,
        date=transaction_date,
    )
    item.full_clean()
    item.save()
    return item


def make_investment(**values) -> Investment:
    operation = Investment(**values)
    operation.full_clean()
    operation.save()
    refresh_fx_snapshot(operation)
    sync_investment_ledger(operation)
    return operation


def seed_profile(language: str, password: str) -> None:
    labels = COPY[language]
    today = timezone.localdate()
    User = get_user_model()

    with translation.override(language):
        user = User.objects.create_user(
            username=labels['username'],
            email=f"{labels['username']}@example.test",
            password=password,
        )
        UserPreference.objects.update_or_create(
            user=user,
            defaults={'base_currency': 'BRL', 'date_format': labels['date_format']},
        )
        user.categories.all().delete()

        salary_category = make_category(user, labels['salary'], Category.TransactionType.INCOME)
        housing_category = make_category(user, labels['housing'], Category.TransactionType.EXPENSE)
        grocery_category = make_category(user, labels['groceries'], Category.TransactionType.EXPENSE)
        utility_category = make_category(user, labels['utilities'], Category.TransactionType.EXPENSE)
        subscription_category = make_category(user, labels['subscriptions'], Category.TransactionType.EXPENSE)
        travel_category = make_category(user, labels['travel'], Category.TransactionType.EXPENSE)
        technology_category = make_category(user, labels['technology'], Category.TransactionType.EXPENSE)

        primary_bank = Bank.objects.create(user=user, name='Tuxedo Demo Bank')
        global_bank = Bank.objects.create(user=user, name='Northstar Demo Bank')
        checking = BankAccount.objects.create(
            user=user,
            bank=primary_bank,
            name=labels['checking'],
            currency='BRL',
            opening_balance=Decimal('4800.00'),
        )
        savings = BankAccount.objects.create(
            user=user,
            bank=primary_bank,
            name=labels['savings'],
            currency='BRL',
            opening_balance=Decimal('12000.00'),
        )
        global_account = BankAccount.objects.create(
            user=user,
            bank=global_bank,
            name=labels['global'],
            currency='USD',
            opening_balance=Decimal('1500.00'),
        )
        debit = DebitCard.objects.create(
            user=user,
            account=checking,
            name=labels['debit'],
        )
        credit = CreditCard.objects.create(
            user=user,
            account=checking,
            name=labels['credit'],
            closing_day=28,
            due_day=5,
        )

        for offset, rate in zip(range(-6, 1), ('4.95', '5.02', '5.08', '5.11', '5.07', '5.13', '5.15')):
            ExchangeRate.objects.create(
                user=user,
                from_currency='USD',
                to_currency='BRL',
                rate=Decimal(rate),
                effective_date=add_months(today, offset, 1),
                notes='Synthetic preview rate',
            )

        fixed_start = add_months(today, -5, 5)
        make_transaction(
            user=user, title=labels['salary'], amount='8200.00',
            transaction_type=Transaction.TransactionType.INCOME,
            category=salary_category, transaction_date=fixed_start,
            payment_channel=Transaction.PaymentChannel.ACCOUNT,
            bank_account=checking, is_fixed=True,
        )
        make_transaction(
            user=user, title=labels['rent'], amount='2300.00',
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=housing_category, transaction_date=add_months(today, -5, 8),
            payment_channel=Transaction.PaymentChannel.PIX,
            bank_account=checking, is_fixed=True,
        )
        make_transaction(
            user=user, title=labels['streaming'], amount='69.90',
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=subscription_category, transaction_date=add_months(today, -5, 10),
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            credit_card=credit, is_fixed=True,
        )

        grocery_amounts = ('486.70', '528.30', '564.10', '603.45', '575.80', '621.25')
        utility_amounts = ('182.40', '176.95', '194.20', '188.70', '205.10', '198.60')
        for offset, (grocery_amount, utility_amount) in enumerate(
            zip(grocery_amounts, utility_amounts), start=-5
        ):
            make_transaction(
                user=user, title=labels['market'], amount=grocery_amount,
                transaction_type=Transaction.TransactionType.EXPENSE,
                category=grocery_category, transaction_date=add_months(today, offset, 13),
                payment_channel=Transaction.PaymentChannel.PIX,
                bank_account=checking,
            )
            make_transaction(
                user=user, title=labels['energy'], amount=utility_amount,
                transaction_type=Transaction.TransactionType.EXPENSE,
                category=utility_category, transaction_date=add_months(today, offset, 17),
                payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
                debit_card=debit,
            )

        make_transaction(
            user=user, title=labels['laptop'], amount='4800.00',
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=technology_category, transaction_date=add_months(today, -2, 21),
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            credit_card=credit, installments=8,
        )
        make_transaction(
            user=user, title=labels['flight'], amount='680.00',
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=travel_category, transaction_date=today,
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            credit_card=credit,
        )

        program = LoyaltyProgram.objects.create(
            user=user,
            name=labels['loyalty'],
            bank=primary_bank,
            unit_name='Miles' if language == 'en' else 'Milhas',
        )
        program.cards.add(credit)
        LoyaltyEntry.objects.create(
            user=user,
            program=program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.ADJUSTMENT,
            amount=Decimal('12400.00'),
            date=add_months(today, -1, 20),
            notes='Synthetic preview balance',
        )

        create_transfer(
            user=user,
            source_account=checking,
            destination_account=savings,
            source_amount=Decimal('900.00'),
            destination_amount=Decimal('900.00'),
            date=add_months(today, 0, 18),
            notes=labels['transfer'],
        )

        brokerage = InvestmentProduct.objects.create(
            user=user,
            bank=global_bank,
            name=labels['brokerage'],
        )
        reserve_product = InvestmentProduct.objects.create(
            user=user,
            bank=primary_bank,
            name=labels['reserve'],
        )
        equity = Asset.objects.create(
            user=user,
            name=labels['equity'],
            code='GLOB',
            asset_class=Asset.AssetClass.EQUITY,
            currency='USD',
            valuation_mode=Asset.ValuationMode.UNITS,
            opening_quantity=Decimal('10.00000000'),
            opening_unit_price=Decimal('100.00000000'),
            opening_product=brokerage,
        )
        reserve = Asset.objects.create(
            user=user,
            name=labels['reserve'],
            code='RSV',
            asset_class=Asset.AssetClass.FIXED_INCOME,
            currency='BRL',
            valuation_mode=Asset.ValuationMode.MONETARY,
            opening_balance=Decimal('3000.00'),
            opening_product=reserve_product,
        )
        make_investment(
            user=user, product=brokerage, asset=equity,
            kind=Investment.Kind.DEPOSIT,
            quantity=Decimal('2.00000000'), unit_price=Decimal('105.00000000'),
            cash_amount=Decimal('210.00'), source_account=global_account,
            date=add_months(today, -2, 14), reason=labels['investment_reason'],
        )
        make_investment(
            user=user, product=brokerage, asset=equity,
            kind=Investment.Kind.YIELD,
            quantity=Decimal('0.10000000'), unit_price=Decimal('110.00000000'),
            date=add_months(today, -1, 19), reason=labels['yield_reason'],
        )
        make_investment(
            user=user, product=reserve_product, asset=reserve,
            kind=Investment.Kind.DEPOSIT,
            amount=Decimal('1200.00'), cash_amount=Decimal('1200.00'),
            source_account=checking, date=add_months(today, 0, 15),
            reason=labels['investment_reason'],
        )
        make_investment(
            user=user, product=reserve_product, asset=reserve,
            kind=Investment.Kind.YIELD,
            amount=Decimal('95.00'), date=add_months(today, 0, 20),
            reason=labels['yield_reason'],
        )

        sync_user_ledger(user)


def main() -> None:
    password = validate_capture_environment()
    seed_profile('en', password)
    seed_profile('pt-br', password)
    print('Disposable preview profiles created.')


if __name__ == '__main__':
    main()
