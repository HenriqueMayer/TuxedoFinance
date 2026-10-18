"""Fixtures coverage for investments."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from banking.models import Bank, BankAccount, LoyaltyEntry, LoyaltyProgram
from investments.models import Asset, Investment, InvestmentProduct


User = get_user_model()


BASE = 'BRL'


class InvestmentFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('investor', password='test')
        cls.bank = Bank.objects.create(user=cls.user, name='Portfolio Bank')
        cls.account = BankAccount.objects.create(
            user=cls.user, bank=cls.bank, name='Cash', currency=BASE
        )
        cls.program = LoyaltyProgram.objects.create(
            user=cls.user, bank=cls.bank, name='Rewards'
        )
        LoyaltyEntry.objects.create(
            user=cls.user,
            program=cls.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.ADJUSTMENT,
            amount=Decimal('10000.00'),
            date=timezone.localdate(),
        )
        cls.product = InvestmentProduct.objects.create(
            user=cls.user, bank=cls.bank, name='Brokerage'
        )
        cls.asset = Asset.objects.create(
            user=cls.user,
            name='Treasury fund',
            code='FUND',
            asset_class=Asset.AssetClass.FIXED_INCOME,
            currency=BASE,
        )

    def operation(self, kind=Investment.Kind.YIELD, **overrides):
        data = {
            'user': self.user,
            'product': self.product,
            'asset': self.asset,
            'kind': kind,
            'quantity': Decimal('2.50000000'),
            'unit_price': Decimal('40.00000000'),
            'fees': Decimal('0.00'),
            'date': timezone.localdate(),
        }
        data.update(overrides)
        return Investment(**data)
