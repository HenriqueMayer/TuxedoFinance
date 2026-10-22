"""Models coverage for investments."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from banking.models import Bank, BankAccount
from investments.models import Asset, Investment, InvestmentProduct
from investments.tests.fixtures import InvestmentFixtureMixin


User = get_user_model()


BASE = 'BRL'


class InvestmentModelTests(InvestmentFixtureMixin, TestCase):
    def test_quantity_price_and_signed_values(self):
        deposit = self.operation(Investment.Kind.YIELD)
        withdrawal = self.operation(
            Investment.Kind.WITHDRAWAL,
            destination_account=self.account,
            cash_amount=Decimal('95.00'),
        )
        self.assertEqual(deposit.gross_value, Decimal('100.0000000000000000'))
        self.assertEqual(deposit.signed_quantity, Decimal('2.50000000'))
        self.assertEqual(withdrawal.signed_quantity, Decimal('-2.50000000'))
        self.assertEqual(withdrawal.signed_value, Decimal('-100.0000000000000000'))

    def test_validation_matrix_accepts_valid_operations(self):
        self.asset.opening_quantity = Decimal('2.5')
        self.asset.opening_unit_price = Decimal('40')
        self.asset.opening_product = self.product
        self.asset.save()
        cases = (
            self.operation(
                Investment.Kind.DEPOSIT,
                source_account=self.account,
                cash_amount=Decimal('101.00'),
            ),
            self.operation(
                Investment.Kind.DEPOSIT,
                source_program=self.program,
                source_points=Decimal('1200.00'),
                cash_amount=Decimal('100.00'),
            ),
            self.operation(
                Investment.Kind.WITHDRAWAL,
                destination_account=self.account,
                cash_amount=Decimal('98.00'),
            ),
            self.operation(Investment.Kind.YIELD),
        )
        for operation in cases:
            with self.subTest(kind=operation.kind, source=operation.source_account_id):
                operation.full_clean()

    def test_validation_matrix_rejects_missing_and_irrelevant_fields(self):
        cases = (
            self.operation(Investment.Kind.DEPOSIT),
            self.operation(
                Investment.Kind.DEPOSIT,
                source_account=self.account,
                source_program=self.program,
                source_points=Decimal('1.00'),
                cash_amount=Decimal('1.00'),
            ),
            self.operation(Investment.Kind.WITHDRAWAL, cash_amount=Decimal('1.00')),
            self.operation(Investment.Kind.YIELD, cash_amount=Decimal('1.00')),
        )
        for operation in cases:
            with self.subTest(kind=operation.kind):
                with self.assertRaises(ValidationError):
                    operation.full_clean()

    def test_ownership_and_product_bank_are_validated(self):
        other = User.objects.create_user('other')
        other_bank = Bank.objects.create(user=other, name='Other Bank')
        other_account = BankAccount.objects.create(
            user=other, bank=other_bank, name='Other Cash', currency=BASE
        )
        product = InvestmentProduct(user=self.user, bank=other_bank, name='Invalid')
        with self.assertRaises(ValidationError):
            product.full_clean()
        operation = self.operation(
            Investment.Kind.DEPOSIT,
            source_account=other_account,
            cash_amount=Decimal('100.00'),
        )
        with self.assertRaises(ValidationError):
            operation.full_clean()

    def test_monetary_asset_accepts_opening_balance_without_units(self):
        savings = Asset.objects.create(
            user=self.user,
            name='Savings pot',
            code='POT',
            asset_class=Asset.AssetClass.LIQUIDITY,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.MONETARY,
            opening_balance=Decimal('1653.10'),
            opening_product=self.product,
        )
        operation = self.operation(
            Investment.Kind.DEPOSIT,
            asset=savings,
            quantity=None,
            unit_price=None,
            amount=Decimal('100.00'),
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        )
        operation.full_clean()
        self.assertEqual(operation.gross_value, Decimal('100.00'))

    def test_unit_asset_accepts_opening_quantity_and_unit_price(self):
        bitcoin = Asset.objects.create(
            user=self.user,
            name='Bitcoin',
            code='BTC',
            asset_class=Asset.AssetClass.CRYPTO,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.UNITS,
            opening_quantity=Decimal('0.25000000'),
            opening_unit_price=Decimal('60000.00000000'),
            opening_product=self.product,
        )

        self.assertEqual(bitcoin.opening_quantity, Decimal('0.25000000'))
        self.assertEqual(bitcoin.opening_unit_price, Decimal('60000.00000000'))

    def test_unit_asset_requires_opening_quantity_and_price_together(self):
        bitcoin = Asset(
            user=self.user,
            name='Bitcoin',
            code='BTC',
            asset_class=Asset.AssetClass.CRYPTO,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.UNITS,
            opening_quantity=Decimal('0.25000000'),
            opening_unit_price=Decimal('0.00'),
            opening_product=self.product,
        )

        with self.assertRaises(ValidationError):
            bitcoin.full_clean()
