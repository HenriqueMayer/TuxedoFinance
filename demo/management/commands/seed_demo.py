from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from banking.models import (
    Bank,
    BankAccount,
    BankMovement,
    BankTransfer,
    CardInvoice,
    CreditCard,
    DebitCard,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from banking.services import create_transfer
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import sync_investment_ledger
from categories.models import Category
from transactions.models import Transaction
from transactions.services import sync_user_ledger


MONTHS = (2, 3, 4, 5, 6, 7, 8)
VARIABLES = {
    2: ('Supermarket and household', '620.00', 'Dinner with friends', '185.00', 'Ride sharing', '96.00'),
    3: ('Supermarket and household', '655.00', 'Weekend trip', '420.00', 'Pharmacy', '138.00'),
    4: ('Supermarket and household', '590.00', 'Home office equipment', '760.00', 'Fuel and parking', '210.00'),
    5: ('Supermarket and household', '680.00', 'Birthday gifts', '310.00', 'Dental appointment', '245.00'),
    6: ('Supermarket and household', '635.00', 'Winter clothes', '540.00', 'Concert tickets', '260.00'),
    7: ('Supermarket and household', '705.00', 'Family lunch', '230.00', 'Car maintenance', '480.00'),
    8: ('Supermarket and household', '690.00', 'Streaming device', '285.00', 'School supplies', '175.00'),
}
RATES = {2: '5.80', 3: '5.72', 4: '5.65', 5: '5.61', 6: '5.55', 7: '5.48', 8: '5.52'}


class Command(BaseCommand):
    help = 'Create or complete the deterministic synthetic demo dataset.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Rebuild only the demo user.')

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(username='demo').first()
        if options['reset'] and user:
            self._clear_demo(user)
        if user is None:
            user = User.objects.create_user(
                username='demo', password='DemoCashFlow2026!', email='demo@example.invalid'
            )
        user.set_password('DemoCashFlow2026!')
        user.save(update_fields=['password'])

        categories = {
            category.name: category
            for category in Category.objects.filter(user=user)
        }
        for name in ('Groceries', 'Food & Dining', 'Subscriptions', 'Transportation', 'Services'):
            categories[name], _ = Category.objects.get_or_create(user=user, name=name)

        nubank, _ = Bank.objects.get_or_create(user=user, name='Nubank')
        wise, _ = Bank.objects.get_or_create(user=user, name='Wise')
        xp, _ = Bank.objects.get_or_create(user=user, name='XP Investimentos')
        checking, _ = BankAccount.objects.get_or_create(
            user=user, bank=nubank, name='Everyday Checking', currency='BRL',
            defaults={'opening_balance': Decimal('8500.00')},
        )
        reserve, _ = BankAccount.objects.get_or_create(
            user=user, bank=nubank, name='Emergency Reserve', currency='BRL',
            defaults={'opening_balance': Decimal('12000.00')},
        )
        usd, _ = BankAccount.objects.get_or_create(
            user=user, bank=wise, name='International Account', currency='USD',
            defaults={'opening_balance': Decimal('450.00')},
        )
        debit, _ = DebitCard.objects.get_or_create(user=user, account=checking, name='Everyday Debit')
        credit, _ = CreditCard.objects.get_or_create(
            user=user, account=checking, name='Aurora Platinum',
            defaults={'closing_day': 24, 'due_day': 10},
        )

        for month in MONTHS:
            month_start = date(2026, month, 1)
            if month == 2:
                Transaction.objects.get_or_create(
                    user=user, title='Monthly salary', date=date(2026, 2, 5),
                    defaults={'amount': Decimal('8500.00'), 'transaction_type': Transaction.TransactionType.INCOME,
                              'category': categories['Services'], 'payment_channel': Transaction.PaymentChannel.ACCOUNT,
                              'bank_account': checking, 'is_fixed': True, 'fixed_until': date(2026, 12, 1)},
                )
                Transaction.objects.get_or_create(
                    user=user, title='Apartment rent', date=date(2026, 2, 7),
                    defaults={'amount': Decimal('2100.00'), 'transaction_type': Transaction.TransactionType.EXPENSE,
                              'category': categories['Services'], 'payment_channel': Transaction.PaymentChannel.PIX,
                              'bank_account': checking, 'is_fixed': True, 'fixed_until': date(2026, 12, 1)},
                )
            if month == 2:
                Transaction.objects.get_or_create(
                    user=user, title='Digital subscriptions', date=date(2026, 2, 12),
                    defaults={'amount': Decimal('149.90'), 'transaction_type': Transaction.TransactionType.EXPENSE,
                              'category': categories['Subscriptions'], 'payment_channel': Transaction.PaymentChannel.CREDIT_CARD,
                              'credit_card': credit, 'is_fixed': True, 'fixed_until': date(2026, 12, 1)},
                )
            grocery, card_title, pix_title = VARIABLES[month][0], VARIABLES[month][2], VARIABLES[month][4]
            values = VARIABLES[month]
            Transaction.objects.get_or_create(
                user=user, title=grocery, date=date(2026, month, 14),
                defaults={'amount': Decimal(values[1]), 'transaction_type': Transaction.TransactionType.EXPENSE,
                          'category': categories['Groceries'], 'payment_channel': Transaction.PaymentChannel.DEBIT_CARD,
                          'debit_card': debit},
            )
            Transaction.objects.get_or_create(
                user=user, title=card_title, date=date(2026, month, 20),
                defaults={'amount': Decimal(values[3]), 'transaction_type': Transaction.TransactionType.EXPENSE,
                          'category': categories['Food & Dining'], 'payment_channel': Transaction.PaymentChannel.CREDIT_CARD,
                          'credit_card': credit},
            )
            Transaction.objects.get_or_create(
                user=user, title=pix_title, date=date(2026, month, 25),
                defaults={'amount': Decimal(values[5]), 'transaction_type': Transaction.TransactionType.EXPENSE,
                          'category': categories['Transportation'], 'payment_channel': Transaction.PaymentChannel.PIX,
                          'bank_account': checking},
            )
            ExchangeRate.objects.get_or_create(
                user=user, from_currency='USD', to_currency='BRL', effective_date=month_start,
                defaults={'rate': Decimal(RATES[month])},
            )

        program, _ = LoyaltyProgram.objects.get_or_create(user=user, name='Aurora Rewards', defaults={'bank': nubank})
        LoyaltyEntry.objects.get_or_create(
            user=user, program=program, kind=LoyaltyEntry.Kind.ADJUSTMENT,
            date=date(2026, 1, 31), defaults={'direction': LoyaltyEntry.Direction.CREDIT, 'amount': Decimal('15000.00')},
        )
        for month in MONTHS:
            invoice_date = date(2026, month, 28)
            LoyaltyEntry.objects.get_or_create(
                user=user, program=program, kind=LoyaltyEntry.Kind.INVOICE_AWARD,
                date=invoice_date, defaults={'direction': LoyaltyEntry.Direction.CREDIT, 'amount': Decimal(str(700 + month * 70))},
            )

        product, _ = InvestmentProduct.objects.get_or_create(user=user, bank=xp, name='Tesouro Selic')
        asset, _ = Asset.objects.get_or_create(
            user=user, code='LFT', defaults={'name': 'Tesouro Selic 2029', 'asset_class': Asset.AssetClass.FIXED_INCOME, 'currency': 'BRL'},
        )
        for month in MONTHS:
            deposit_date = date(2026, month, 26)
            deposit, created = Investment.objects.get_or_create(
                user=user, product=product, asset=asset, kind=Investment.Kind.DEPOSIT, date=deposit_date,
                defaults={'quantity': Decimal('0.00150000'), 'unit_price': Decimal(str(90000 + month * 2500)), 'cash_amount': Decimal(str(850 + month * 50)), 'source_account': checking},
            )
            if created:
                sync_investment_ledger(deposit)
            withdrawal, created = Investment.objects.get_or_create(
                user=user, product=product, asset=asset, kind=Investment.Kind.WITHDRAWAL, date=date(2026, month, 28),
                defaults={'quantity': Decimal('0.00020000'), 'unit_price': Decimal(str(90000 + month * 2500)), 'cash_amount': Decimal(str(100 + month * 20)), 'destination_account': checking},
            )
            if created:
                sync_investment_ledger(withdrawal)

        sync_user_ledger(user, through_date=date(2026, 8, 31), projection_months=4)
        self.stdout.write(self.style.SUCCESS('Demo seeded through August 2026.'))

    def _clear_demo(self, user):
        """Delete protected financial rows in dependency order, keeping other users intact."""
        Transaction.objects.filter(user=user).delete()
        RewardRedemption.objects.filter(user=user).delete()
        Investment.objects.filter(user=user).delete()
        LoyaltyEntry.objects.filter(user=user).delete()
        BankMovement.objects.filter(user=user).delete()
        CardInvoice.objects.filter(user=user).delete()
        DebitCard.objects.filter(user=user).delete()
        CreditCard.objects.filter(user=user).delete()
        BankTransfer.objects.filter(user=user).delete()
        ExchangeRate.objects.filter(user=user).delete()
        BankAccount.objects.filter(user=user).delete()
        InvestmentProduct.objects.filter(user=user).delete()
        Asset.objects.filter(user=user).delete()
        LoyaltyProgram.objects.filter(user=user).delete()
        Bank.objects.filter(user=user).delete()
        Category.objects.filter(user=user).delete()
