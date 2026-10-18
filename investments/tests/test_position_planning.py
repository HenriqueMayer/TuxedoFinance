# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from banking.models import Bank, BankAccount, BankMovement
from banking.services import get_planning_availability, set_position_planning
from dashboard.wealth import wealth_snapshot
from investments.models import Asset, Investment, InvestmentProduct, PositionPlanningSetting
from investments.positions import get_portfolio_valuation


class PositionPlanningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('position-reserve-owner')
        self.other = get_user_model().objects.create_user('position-reserve-other')
        self.bank = Bank.objects.create(user=self.user, name='Real bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash',
            currency='BRL', opening_balance=1000, opening_date=date(2020, 1, 1))
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Daily cash', purpose='MONTHLY_CASH')
        self.asset = Asset.objects.create(user=self.user, name='Emergency reserve', code='RESERVE',
            currency='BRL', valuation_mode='MONETARY', opening_balance=300,
            opening_product=self.product, opening_date=date(2020, 1, 1))

    def test_exclusion_is_idempotent_per_position_and_preserves_all_real_money(self):
        second = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Other cash', purpose='MONTHLY_CASH')
        Investment.objects.create(user=self.user, product=second, asset=self.asset, kind='YIELD', amount=50, date=date(2020, 1, 2))
        sources = list(Investment.objects.values()), list(Asset.objects.values()), list(BankMovement.objects.values())
        before = wealth_snapshot(self.user, date.today())['net_worth']
        for _ in range(2):
            set_position_planning(self.user, self.product.pk, self.asset.pk, False)
        result = get_planning_availability(self.user)
        self.assertEqual(result['available_total'], Decimal('1050'))
        self.assertEqual(result['pot_total'], Decimal('350'))
        self.assertEqual(result['reserved_total'], Decimal('300'))
        self.assertEqual([(row['product'].pk, row['asset'].pk) for row in result['reserved_cash_pots']], [(self.product.pk, self.asset.pk)])
        self.assertEqual(result['included_cash_pots'][0]['product'], second)
        self.assertEqual(PositionPlanningSetting.objects.count(), 1)
        self.assertEqual(wealth_snapshot(self.user, date.today())['net_worth'], before)
        self.assertEqual((list(Investment.objects.values()), list(Asset.objects.values()), list(BankMovement.objects.values())), sources)
        set_position_planning(self.user, self.product.pk, self.asset.pk, True)
        self.assertEqual(get_planning_availability(self.user)['available_total'], Decimal('1350'))

    def test_excluded_legacy_deficit_is_never_hidden(self):
        set_position_planning(self.user, self.product.pk, self.asset.pk, False)
        row = {'product': self.product, 'asset': self.asset, 'currency': 'BRL', 'balance': Decimal('-10')}
        with patch('investments.services.get_monthly_cash_positions', return_value=[row]):
            result = get_planning_availability(self.user)
        self.assertEqual(result['available_total'], Decimal('990'))
        self.assertEqual(result['reserved_total'], Decimal('0'))
        self.assertEqual(result['reserved_cash_pots'][0]['available'], Decimal('-10'))

    def test_named_reservation_and_whole_exclusion_never_double_count(self):
        from planning.models import FinancialGoal, GoalAllocation
        goal = FinancialGoal.objects.create(user=self.user, name='Emergency', target_amount=1000, currency='BRL')
        GoalAllocation.objects.create(user=self.user, goal=goal, product=self.product, asset=self.asset, amount=100)
        set_position_planning(self.user, self.product.pk, self.asset.pk, False)
        result = get_planning_availability(self.user)
        self.assertEqual(result['reserved_total'], Decimal('300'))
        self.assertEqual(result['available_total'], Decimal('1000'))

    def test_owner_compatibility_unique_and_unknown_pair_guards(self):
        foreign_bank = Bank.objects.create(user=self.other, name='Private')
        foreign_product = InvestmentProduct.objects.create(user=self.other, bank=foreign_bank, name='Private cash', purpose='MONTHLY_CASH')
        investment = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Long term')
        unit_asset = Asset.objects.create(user=self.user, name='Units', code='UNIT', currency='BRL', valuation_mode='UNITS')
        for product, asset in [(foreign_product, self.asset), (investment, self.asset), (self.product, unit_asset)]:
            with self.subTest(product=product, asset=asset), self.assertRaises(ValidationError):
                PositionPlanningSetting(user=self.user, product=product, asset=asset).full_clean()
        with self.assertRaises(ValidationError):
            set_position_planning(self.user, investment.pk, self.asset.pk, False)
        PositionPlanningSetting.objects.create(user=self.user, product=self.product, asset=self.asset)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PositionPlanningSetting.objects.create(user=self.user, product=self.product, asset=self.asset)

    def test_zero_configuration_link_has_no_opening_event_or_cash_and_keeps_guards(self):
        investment = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Configured only')
        before = get_portfolio_valuation(self.user)['total']
        for mode, product in [('UNITS', investment), ('MONETARY', self.product)]:
            asset = Asset(user=self.user, name=f'Empty {mode}', code=mode, currency='BRL', asset_class='OTHER',
                          valuation_mode=mode, opening_product=product)
            asset.full_clean()
            asset.save()
            self.assertFalse(asset.has_opening_position)
        self.assertEqual(get_portfolio_valuation(self.user)['total'], before)
        self.assertFalse(Investment.objects.exists())
        self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(self.account.current_balance(), Decimal('1000'))
        private_bank = Bank.objects.create(user=self.other, name='Private')
        private = InvestmentProduct.objects.create(user=self.other, bank=private_bank, name='Private')
        for product, mode in [(private, 'MONETARY'), (self.product, 'UNITS')]:
            with self.subTest(product=product, mode=mode), self.assertRaises(ValidationError):
                Asset(user=self.user, name='Invalid configuration', code='INVALID', currency='BRL', asset_class='OTHER',
                      valuation_mode=mode, opening_product=product).full_clean()
