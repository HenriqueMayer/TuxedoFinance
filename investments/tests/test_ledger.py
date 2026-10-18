"""Ledger coverage for investments."""

from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from banking.models import BankMovement, LoyaltyEntry
from investments.models import Asset, Investment
from investments.services import cleanup_investment_ledger, get_portfolio_groups, sync_investment_ledger
from investments.tests.fixtures import InvestmentFixtureMixin


BASE = 'BRL'


class InvestmentLedgerTests(InvestmentFixtureMixin, TestCase):
    def save_and_sync(self, operation):
        operation.full_clean()
        operation.save()
        sync_investment_ledger(operation)
        operation.refresh_from_db()
        return operation

    def test_account_deposit_creates_investment_debit(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('103.50'),
        ))
        movement = operation.bank_movement
        self.assertEqual(movement.direction, BankMovement.Direction.DEBIT)
        self.assertEqual(movement.kind, BankMovement.Kind.INVESTMENT)
        self.assertEqual(movement.amount, Decimal('103.50'))
        self.assertEqual(movement.source_key, f'investment:{operation.pk}')

    def test_points_deposit_creates_redemption_debit(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_program=self.program,
            source_points=Decimal('2500.00'),
            cash_amount=Decimal('100.00'),
        ))
        entry = operation.loyalty_entry
        self.assertEqual(entry.direction, LoyaltyEntry.Direction.DEBIT)
        self.assertEqual(entry.kind, LoyaltyEntry.Kind.REDEMPTION)
        self.assertEqual(entry.amount, Decimal('2500.00'))
        self.assertIn(f'[investment:{operation.pk}]', entry.notes)
        self.assertIsNone(operation.bank_movement)

    def test_withdrawal_credit_and_yield_has_no_cash_ledger(self):
        self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        ))
        withdrawal = self.save_and_sync(self.operation(
            Investment.Kind.WITHDRAWAL,
            destination_account=self.account,
            cash_amount=Decimal('97.00'),
        ))
        self.assertEqual(withdrawal.bank_movement.direction, BankMovement.Direction.CREDIT)
        yield_operation = self.save_and_sync(self.operation(Investment.Kind.YIELD))
        self.assertIsNone(yield_operation.bank_movement)
        self.assertIsNone(yield_operation.loyalty_entry)

    def test_withdrawal_view_rejects_more_than_available_quantity(self):
        self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        ))
        self.client.force_login(self.user)
        response = self.client.post(reverse('investments:create'), {
            'product': self.product.pk,
            'asset': self.asset.pk,
            'kind': Investment.Kind.WITHDRAWAL,
            'quantity': '3.00000000',
            'unit_price': '40.00000000',
            'fees': '0.00',
            'cash_amount': '120.00',
            'source_account': '',
            'source_program': '',
            'source_points': '',
            'destination_account': self.account.pk,
            'date': timezone.localdate(),
            'reason': '',
            'notes': '',
        })

        self.assertContains(response, 'exceeds the available position', status_code=200)

    def test_sync_update_is_idempotent_and_replaces_only_linked_ledger(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        ))
        movement_id = operation.bank_movement_id
        operation.cash_amount = Decimal('125.00')
        operation.save()
        sync_investment_ledger(operation)
        sync_investment_ledger(operation)
        operation.refresh_from_db()
        self.assertEqual(operation.bank_movement_id, movement_id)
        self.assertEqual(BankMovement.objects.get(pk=movement_id).amount, Decimal('125.00'))
        self.assertEqual(
            BankMovement.objects.filter(source_key=f'investment:{operation.pk}').count(), 1
        )

    def test_cleanup_removes_linked_rows_before_operation_delete(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_program=self.program,
            source_points=Decimal('500.00'),
        ))
        entry_id = operation.loyalty_entry_id
        cleanup_investment_ledger(operation)
        operation.delete()
        self.assertFalse(LoyaltyEntry.objects.filter(pk=entry_id).exists())

    def test_monetary_opening_balance_is_available_for_withdrawal(self):
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
        withdrawal = self.save_and_sync(self.operation(
            Investment.Kind.WITHDRAWAL,
            asset=savings,
            quantity=None,
            unit_price=None,
            amount=Decimal('500.00'),
            destination_account=self.account,
            cash_amount=Decimal('500.00'),
        ))
        group = get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]
        self.assertEqual(withdrawal.bank_movement.amount, Decimal('500.00'))
        self.assertEqual(group['balance'], Decimal('1153.10'))

    def test_unit_opening_position_is_available_for_withdrawal(self):
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
        withdrawal = self.save_and_sync(self.operation(
            Investment.Kind.WITHDRAWAL,
            asset=bitcoin,
            quantity=Decimal('0.10000000'),
            unit_price=Decimal('62000.00000000'),
            destination_account=self.account,
            cash_amount=Decimal('6200.00'),
        ))

        self.assertIsNotNone(withdrawal.bank_movement)
        group = get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]
        self.assertEqual(group['quantity'], Decimal('0.15000000'))
        self.assertEqual(group['balance'], Decimal('9000'))
        self.assertEqual(group['realized_gain'], Decimal('200'))
