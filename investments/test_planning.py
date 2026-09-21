"""Position classification and deletion safety across all application paths."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from banking.models import Bank
from investments.admin import AssetAdmin
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import get_asset_positions, get_portfolio_groups, get_total_in_base_timeseries


class PlanningPositionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('position-owner')
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Product')
        self.client.force_login(self.user)

    def asset(self, code='MONEY', **kwargs):
        data = dict(user=self.user, name=code, code=code, currency='BRL', asset_class=Asset.AssetClass.LIQUIDITY, valuation_mode=Asset.ValuationMode.MONETARY)
        data.update(kwargs)
        return Asset.objects.create(**data)

    def test_direct_and_bulk_deletion_preserve_initial_positions_atomically(self):
        money = self.asset(opening_balance=Decimal('500'), opening_product=self.product)
        units = self.asset('UNITS', valuation_mode=Asset.ValuationMode.UNITS, opening_quantity=Decimal('2'), opening_unit_price=Decimal('100'), opening_product=self.product)
        empty = self.asset('EMPTY')
        for held in (money, units):
            with self.assertRaises(ProtectedError), transaction.atomic():
                held.delete()
        with self.assertRaises(ProtectedError), transaction.atomic():
            Asset.objects.filter(pk__in=[money.pk, empty.pk]).delete()
        self.assertEqual(Asset.objects.count(), 3)
        empty.delete()
        self.assertEqual(Asset.objects.count(), 2)

    def test_stale_instance_cannot_delete_newer_opening_position(self):
        stale = self.asset()
        Asset.objects.filter(pk=stale.pk).update(opening_balance=Decimal('500'), opening_product=self.product)
        with self.assertRaises(ProtectedError), transaction.atomic():
            stale.delete()
        self.assertTrue(Asset.objects.filter(pk=stale.pk).exists())

    def test_view_and_admin_protect_opening_positions_without_operations(self):
        held = self.asset(opening_balance=Decimal('500'), opening_product=self.product)
        response = self.client.post(reverse('investments:delete_asset', args=[held.pk]))
        self.assertRedirects(response, reverse('investments:settings'))
        self.assertTrue(Asset.objects.filter(pk=held.pk).exists())
        response = self.client.post(reverse('investments:delete_product', args=[self.product.pk]))
        self.assertTrue(InvestmentProduct.objects.filter(pk=self.product.pk).exists())
        request = RequestFactory().get('/')
        request.user = get_user_model().objects.create_superuser('position-admin', password='test')
        asset_admin = AssetAdmin(Asset, admin.site)
        self.assertTrue(asset_admin.get_deleted_objects([held], request)[3])
        with self.assertRaises(ProtectedError), transaction.atomic():
            asset_admin.delete_queryset(request, Asset.objects.filter(pk=held.pk))

    def test_zero_position_with_history_remains_protected(self):
        held = self.asset()
        Investment.objects.create(user=self.user, product=self.product, asset=held, kind='YIELD', amount=Decimal('100'), date=date(2026, 9, 1))
        Investment.objects.create(user=self.user, product=self.product, asset=held, kind='WITHDRAWAL', amount=Decimal('100'), date=date(2026, 9, 2))
        with self.assertRaises(ProtectedError), transaction.atomic():
            held.delete()

    def test_other_user_cannot_delete_an_empty_asset(self):
        held = self.asset()
        self.client.force_login(get_user_model().objects.create_user('position-other'))
        self.assertEqual(self.client.post(reverse('investments:delete_asset', args=[held.pk])).status_code, 404)
        self.assertTrue(Asset.objects.filter(pk=held.pk).exists())

    def test_cash_product_rejects_unit_openings_operations_and_reclassification(self):
        self.product.purpose = InvestmentProduct.Purpose.MONTHLY_CASH
        self.product.save()
        units = self.asset('UNITS', valuation_mode=Asset.ValuationMode.UNITS)
        units.opening_quantity = Decimal('1')
        units.opening_unit_price = Decimal('100')
        units.opening_product = self.product
        with self.assertRaises(ValidationError):
            units.full_clean()
        operation = Investment(user=self.user, product=self.product, asset=units, kind='YIELD', quantity=Decimal('1'), unit_price=Decimal('100'), date=date(2026, 9, 1))
        with self.assertRaises(ValidationError):
            operation.full_clean()
        self.product.purpose = InvestmentProduct.Purpose.INVESTMENT
        self.product.save()
        operation.save()
        self.product.purpose = InvestmentProduct.Purpose.MONTHLY_CASH
        with self.assertRaises(ValidationError):
            self.product.full_clean()

    def test_opening_values_are_included_in_history_and_future_operations_not_in_current_position(self):
        asset = self.asset(opening_balance=Decimal('500'), opening_product=self.product)
        tomorrow = timezone.localdate() + timedelta(days=1)
        Investment.objects.create(user=self.user, product=self.product, asset=asset, kind='YIELD', amount=Decimal('20'), date=tomorrow)
        self.assertEqual(get_asset_positions(self.user)[0]['value_flow'], Decimal('500'))
        self.assertEqual(get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]['balance'], Decimal('500'))
        rows, missing = get_total_in_base_timeseries(self.user, 'BRL', months=2, offset=-1)
        self.assertEqual(rows[-1]['total'], Decimal('500'))
        self.assertEqual(missing, [])

    def test_section_scopes_positions_history_and_totals_and_boosted_navigation_is_a_page(self):
        cash = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Cash pot', purpose='MONTHLY_CASH')
        asset = self.asset(opening_balance=Decimal('700'), opening_product=self.product)
        Investment.objects.create(user=self.user, product=cash, asset=asset, kind='YIELD', amount=Decimal('300'), date=timezone.localdate())
        portfolio = self.client.get(reverse('investments:list'))
        self.assertEqual(portfolio.context['selected_section'], 'portfolio')
        self.assertEqual(portfolio.context['simulated_total'], Decimal('700'))
        self.assertEqual(portfolio.context['paginator'].count, 0)
        pots = self.client.get(reverse('investments:list'), {'section': 'cash'}, HTTP_HX_REQUEST='true', HTTP_HX_BOOSTED='true', HTTP_HX_TARGET='main-content')
        self.assertEqual(pots.context['simulated_total'], Decimal('300'))
        self.assertEqual(pots.context['paginator'].count, 1)
        self.assertEqual(pots.context['portfolio_groups'][0]['products'][0]['purpose'], 'MONTHLY_CASH')
        self.assertContains(pots, '<html')
