"""Planning excludes reserved resources while retaining the complete cash ledger."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from banking.models import Bank, BankAccount, BankMovement, ExchangeRate
from banking.services import account_balances, create_transfer, get_planning_availability
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import sync_investment_ledger


class PlanningAvailabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('planning-owner')
        self.today = date(2026, 9, 20)
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.account = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Current', currency='BRL',
            opening_balance=Decimal('1000.00'), reserved_amount=Decimal('200.00'),
        )

    def test_partial_reserves_and_excluded_deficits_do_not_change_ledger(self):
        excluded = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Excluded', currency='BRL',
            opening_balance=Decimal('300'), planning_enabled=False,
        )
        deficit = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Deficit', currency='BRL',
            opening_balance=Decimal('-50'), planning_enabled=False,
        )
        result = get_planning_availability(self.user, self.today)
        self.assertEqual(result['bank_total'], Decimal('1250'))
        self.assertEqual(result['reserved_total'], Decimal('500'))
        self.assertEqual(result['available_total'], Decimal('750'))
        self.assertEqual(excluded.current_balance(self.today), Decimal('300'))
        self.assertEqual(deficit.current_balance(self.today), Decimal('-50'))

    def test_reserve_shortfall_is_explicit_and_never_creates_a_fictitious_deficit(self):
        self.account.reserved_amount = Decimal('1200')
        self.account.save()
        result = get_planning_availability(self.user, self.today)
        self.assertEqual(result['available_total'], Decimal('0'))
        self.assertEqual(result['reserved_total'], Decimal('1000'))
        self.assertEqual(result['reserve_shortfall'], Decimal('200'))
        self.account.reserved_amount = Decimal('-1')
        with self.assertRaises(ValidationError):
            self.account.full_clean()

    def test_cash_pot_transfer_yield_and_withdrawal_preserve_combined_availability(self):
        product = InvestmentProduct.objects.create(
            user=self.user, bank=self.bank, name='Monthly pot',
            purpose=InvestmentProduct.Purpose.MONTHLY_CASH,
        )
        asset = Asset.objects.create(
            user=self.user, name='Cash', code='CASH', currency='BRL',
            asset_class=Asset.AssetClass.LIQUIDITY, valuation_mode=Asset.ValuationMode.MONETARY,
        )
        for kind, amount, links in (
            (Investment.Kind.DEPOSIT, '300', {'source_account': self.account, 'cash_amount': Decimal('300')}),
            (Investment.Kind.YIELD, '5', {}),
            (Investment.Kind.WITHDRAWAL, '100', {'destination_account': self.account, 'cash_amount': Decimal('100')}),
        ):
            operation = Investment.objects.create(
                user=self.user, product=product, asset=asset, kind=kind,
                amount=Decimal(amount), date=self.today, **links,
            )
            sync_investment_ledger(operation)
        result = get_planning_availability(self.user, self.today)
        self.assertEqual(result['bank_total'], Decimal('800'))
        self.assertEqual(result['pot_total'], Decimal('205'))
        self.assertEqual(result['available_total'], Decimal('805'))
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 2)

    def test_same_asset_in_two_products_only_includes_monthly_cash_and_not_future_operations(self):
        cash = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Cash', purpose='MONTHLY_CASH')
        capital = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Capital')
        asset = Asset.objects.create(
            user=self.user, name='Same asset', code='SAME', currency='BRL',
            asset_class=Asset.AssetClass.LIQUIDITY, valuation_mode=Asset.ValuationMode.MONETARY,
            opening_balance=Decimal('300'), opening_product=cash,
        )
        Investment.objects.create(user=self.user, product=capital, asset=asset, kind='YIELD', amount=Decimal('700'), date=self.today)
        Investment.objects.create(user=self.user, product=cash, asset=asset, kind='YIELD', amount=Decimal('20'), date=self.today+timedelta(days=1))
        result = get_planning_availability(self.user, self.today)
        self.assertEqual(result['pot_total'], Decimal('300'))
        self.assertEqual(len(result['cash_pots']), 1)
        self.assertEqual(result['cash_pots'][0]['product'], cash)

    def test_transfer_to_excluded_account_changes_only_planning_availability(self):
        excluded = BankAccount.objects.create(user=self.user, bank=self.bank, name='Reserved', currency='BRL', planning_enabled=False)
        create_transfer(user=self.user, source_account=self.account, destination_account=excluded, source_amount=Decimal('100'), destination_amount=Decimal('100'), date=self.today)
        result = get_planning_availability(self.user, self.today)
        self.assertEqual(result['bank_total'], Decimal('1000'))
        self.assertEqual(result['available_total'], Decimal('700'))

    def test_missing_fx_is_explicit_and_known_fx_rows_reconcile_after_rounding(self):
        foreign = BankAccount.objects.create(user=self.user, bank=self.bank, name='Dollars', currency='USD', opening_balance=Decimal('1'), reserved_amount=Decimal('0.50'))
        result = get_planning_availability(self.user, self.today)
        row = next(row for row in result['account_rows'] if row['account'] == foreign)
        self.assertIsNone(row['converted_available'])
        self.assertEqual(result['missing_currencies'], ['USD'])
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate=Decimal('5.05'), effective_date=self.today)
        result = get_planning_availability(self.user, self.today)
        self.assertEqual(result['available_total'], result['bank_total']+result['pot_total']-result['reserved_total'])

    def test_grouped_balances_and_availability_have_constant_query_count_and_do_not_write(self):
        for number in range(20):
            BankAccount.objects.create(user=self.user, bank=self.bank, name=f'Account {number}', currency='BRL')
        other = get_user_model().objects.create_user('planning-other')
        other_bank = Bank.objects.create(user=other, name='Other')
        BankAccount.objects.create(user=other, bank=other_bank, name='Secret', currency='BRL', opening_balance=Decimal('99999'))
        with self.assertNumQueries(2):
            self.assertEqual(len(account_balances(self.user, self.today)), 21)
        with CaptureQueriesContext(connection) as queries:
            result = get_planning_availability(self.user, self.today)
        self.assertEqual(len(queries), 5)
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in queries))
        self.assertEqual(result['bank_total'], Decimal('1000'))
