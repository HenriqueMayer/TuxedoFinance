from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from investments.models import Asset, ExchangeRate, Institution, Investment, InvestmentProduct
from investments.services import (
    TIMESERIES_MONTHS,
    get_monthly_flow_in_base,
    get_portfolio_groups,
    get_total_in_base_timeseries,
)

User = get_user_model()
BASE = settings.CURRENCY


def make_product(user, name='Savings'):
    institution = Institution.objects.create(user=user, name='Mercado Pago')
    return InvestmentProduct.objects.create(
        user=user,
        institution=institution,
        name=name,
    )


def make_asset(user, code=BASE, name=None):
    return Asset.objects.create(
        user=user,
        name=name or code,
        code=code,
        currency=code,
    )


def add_operation(user, **kwargs):
    defaults = {
        'title': 'Manual operation',
        'amount': Decimal('100.00'),
        'kind': Investment.Kind.DEPOSIT,
        'date': timezone.localdate(),
    }
    defaults.update(kwargs)
    product = defaults.pop('product', None) or make_product(user)
    asset = defaults.pop('asset', None) or make_asset(user)
    return Investment.objects.create(
        user=user,
        product=product,
        asset=asset,
        **defaults,
    )


class InvestmentServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('services', password='test')
        self.product = make_product(self.user)
        self.asset = make_asset(self.user)

    def test_manual_yield_is_added_to_balance_but_kept_separate(self):
        add_operation(
            self.user, product=self.product, asset=self.asset,
            amount=Decimal('1000.00'), kind=Investment.Kind.DEPOSIT,
        )
        add_operation(
            self.user, product=self.product, asset=self.asset,
            amount=Decimal('25.00'), kind=Investment.Kind.YIELD,
        )
        add_operation(
            self.user, product=self.product, asset=self.asset,
            amount=Decimal('100.00'), kind=Investment.Kind.WITHDRAWAL,
        )

        group = get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]
        self.assertEqual(group['deposits'], Decimal('1000.00'))
        self.assertEqual(group['yields'], Decimal('25.00'))
        self.assertEqual(group['withdrawals'], Decimal('100.00'))
        self.assertEqual(group['balance'], Decimal('925.00'))

    def test_monthly_flow_has_a_separate_yield_series(self):
        add_operation(
            self.user, product=self.product, asset=self.asset,
            amount=Decimal('12.50'), kind=Investment.Kind.YIELD,
        )
        rows, missing = get_monthly_flow_in_base(
            self.user, BASE, [BASE], months=TIMESERIES_MONTHS,
        )
        current = next(row for row in rows if row['date'] == date.today().replace(day=1))
        self.assertEqual(current['yields'], Decimal('12.50'))
        self.assertEqual(current['deposits'], Decimal('0.00'))
        self.assertEqual(missing, [])

    def test_foreign_asset_uses_historical_rate(self):
        asset = make_asset(self.user, code='USD')
        ExchangeRate.objects.create(
            user=self.user,
            from_currency='USD',
            to_currency=BASE,
            rate=Decimal('5.00'),
            effective_date=date(2024, 1, 1),
        )
        add_operation(
            self.user, product=self.product, asset=asset,
            amount=Decimal('100.00'), date=date(2024, 6, 1),
        )
        rows, missing = get_total_in_base_timeseries(
            self.user, BASE, [BASE, 'USD'], months=TIMESERIES_MONTHS,
        )
        self.assertEqual(missing, [])
        self.assertTrue(any(row['total'] == Decimal('500.00') for row in rows))


class InvestmentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('views', password='test')
        cls.product = make_product(cls.user)
        cls.asset = make_asset(cls.user)
        add_operation(
            cls.user,
            product=cls.product,
            asset=cls.asset,
            title='Monthly yield',
            kind=Investment.Kind.YIELD,
            amount=Decimal('20.00'),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_full_page_renders_grouped_investment(self):
        response = self.client.get(reverse('investments:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mercado Pago')
        self.assertContains(response, 'Manual yields')
        self.assertContains(response, 'Yield')

    def test_htmx_request_returns_chart_partial(self):
        response = self.client.get(
            reverse('investments:list'),
            {'flow_offset': '-3'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<html')
        self.assertContains(response, 'id="investments-charts"')
        self.assertContains(response, 'Yields')

    def test_operation_filter_can_select_yields(self):
        response = self.client.get(
            reverse('investments:list'), {'kind': Investment.Kind.YIELD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Monthly yield')

    def test_product_creation_is_user_scoped(self):
        other = User.objects.create_user('other', password='test')
        Institution.objects.create(user=other, name='Private Bank')
        response = self.client.get(reverse('investments:create'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Private Bank')
