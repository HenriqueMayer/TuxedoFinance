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


class InvestmentSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('settings', password='test')
        cls.institution = Institution.objects.create(
            user=cls.user,
            name='Original Bank',
        )
        cls.other_institution = Institution.objects.create(
            user=cls.user,
            name='Second Broker',
        )
        cls.product = InvestmentProduct.objects.create(
            user=cls.user,
            institution=cls.institution,
            name='Wrong Product',
        )
        cls.asset = Asset.objects.create(
            user=cls.user,
            name='Wrong Asset',
            code='WRONG',
            currency=BASE,
        )

        cls.other_user = User.objects.create_user(
            'settings-other',
            password='test',
        )
        cls.foreign_institution = Institution.objects.create(
            user=cls.other_user,
            name='Private Bank',
        )
        cls.foreign_product = InvestmentProduct.objects.create(
            user=cls.other_user,
            institution=cls.foreign_institution,
            name='Private Product',
        )
        cls.foreign_asset = Asset.objects.create(
            user=cls.other_user,
            name='Private Asset',
            code='PRIVATE',
            currency=BASE,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def create_operation(self):
        return Investment.objects.create(
            user=self.user,
            product=self.product,
            asset=self.asset,
            title='Historical operation',
            amount=Decimal('100.00'),
            kind=Investment.Kind.DEPOSIT,
            date=date(2026, 8, 10),
        )

    def test_settings_lists_only_current_user_entities(self):
        response = self.client.get(reverse('investments:settings'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Original Bank')
        self.assertContains(response, 'Wrong Product')
        self.assertContains(response, 'Wrong Asset')
        self.assertNotContains(response, 'Private Bank')
        self.assertNotContains(response, 'Private Product')
        self.assertNotContains(response, 'Private Asset')
        self.assertContains(response, reverse('investments:exchange_rates'))

    def test_main_settings_button_opens_entity_settings(self):
        response = self.client.get(reverse('investments:list'))

        self.assertContains(response, reverse('investments:settings'))

    def test_setup_create_views_assign_current_user(self):
        institution_response = self.client.post(
            reverse('investments:create_institution'),
            {'name': 'Created Bank'},
        )
        self.assertRedirects(
            institution_response,
            reverse('investments:settings'),
        )
        institution = Institution.objects.get(name='Created Bank')
        self.assertEqual(institution.user, self.user)

        product_response = self.client.post(
            reverse('investments:create_product'),
            {'institution': institution.pk, 'name': 'Created Product'},
        )
        self.assertRedirects(product_response, reverse('investments:settings'))
        self.assertTrue(
            InvestmentProduct.objects.filter(
                user=self.user,
                institution=institution,
                name='Created Product',
            ).exists()
        )

        asset_response = self.client.post(
            reverse('investments:create_asset'),
            {'name': 'Created Asset', 'code': 'NEW', 'currency': BASE},
        )
        self.assertRedirects(asset_response, reverse('investments:settings'))
        self.assertTrue(
            Asset.objects.filter(user=self.user, code='NEW').exists()
        )

    def test_institution_can_be_renamed_and_duplicate_is_friendly(self):
        rename_response = self.client.post(
            reverse('investments:update_institution', args=[self.institution.pk]),
            {'name': 'Correct Bank'},
        )
        self.assertRedirects(rename_response, reverse('investments:settings'))
        self.institution.refresh_from_db()
        self.assertEqual(self.institution.name, 'Correct Bank')

        duplicate_response = self.client.post(
            reverse('investments:update_institution', args=[self.institution.pk]),
            {'name': self.other_institution.name},
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertContains(
            duplicate_response,
            'You already have an institution with this name.',
        )

    def test_product_can_move_to_another_owned_institution(self):
        self.create_operation()

        response = self.client.post(
            reverse('investments:update_product', args=[self.product.pk]),
            {
                'institution': self.other_institution.pk,
                'name': 'Correct Product',
            },
        )

        self.assertRedirects(response, reverse('investments:settings'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Correct Product')
        self.assertEqual(self.product.institution, self.other_institution)
        self.assertEqual(
            Investment.objects.get(title='Historical operation').product,
            self.product,
        )

    def test_product_rejects_foreign_institution(self):
        response = self.client.post(
            reverse('investments:update_product', args=[self.product.pk]),
            {
                'institution': self.foreign_institution.pk,
                'name': self.product.name,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.product.refresh_from_db()
        self.assertEqual(self.product.institution, self.institution)

    def test_product_and_asset_duplicates_are_field_errors(self):
        duplicate_product = InvestmentProduct.objects.create(
            user=self.user,
            institution=self.institution,
            name='Other Product',
        )
        product_response = self.client.post(
            reverse('investments:update_product', args=[duplicate_product.pk]),
            {
                'institution': self.institution.pk,
                'name': self.product.name,
            },
        )
        self.assertEqual(product_response.status_code, 200)
        self.assertContains(
            product_response,
            'already has an investment product with this name',
        )

        duplicate_asset = Asset.objects.create(
            user=self.user,
            name='Other Asset',
            code='OTHER',
            currency=BASE,
        )
        asset_response = self.client.post(
            reverse('investments:update_asset', args=[duplicate_asset.pk]),
            {
                'name': duplicate_asset.name,
                'code': self.asset.code,
                'currency': BASE,
            },
        )
        self.assertEqual(asset_response.status_code, 200)
        self.assertContains(
            asset_response,
            'You already have an asset with this code.',
        )

    def test_asset_name_and_code_can_be_corrected(self):
        response = self.client.post(
            reverse('investments:update_asset', args=[self.asset.pk]),
            {
                'name': 'Correct Asset',
                'code': 'RIGHT',
                'currency': BASE,
            },
        )

        self.assertRedirects(response, reverse('investments:settings'))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.name, 'Correct Asset')
        self.assertEqual(self.asset.code, 'RIGHT')

    def test_asset_currency_change_is_blocked_after_use(self):
        self.create_operation()
        other_currency = next(code for code in ('USD', 'EUR', 'GBP') if code != BASE)

        response = self.client.post(
            reverse('investments:update_asset', args=[self.asset.pk]),
            {
                'name': self.asset.name,
                'code': self.asset.code,
                'currency': other_currency,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Currency cannot be changed')
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.currency, BASE)

    def test_unused_asset_currency_can_change(self):
        other_currency = next(code for code in ('USD', 'EUR', 'GBP') if code != BASE)

        response = self.client.post(
            reverse('investments:update_asset', args=[self.asset.pk]),
            {
                'name': self.asset.name,
                'code': self.asset.code,
                'currency': other_currency,
            },
        )

        self.assertRedirects(response, reverse('investments:settings'))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.currency, other_currency)

    def test_referenced_entities_cannot_be_deleted(self):
        self.create_operation()
        cases = (
            ('delete_institution', self.institution),
            ('delete_product', self.product),
            ('delete_asset', self.asset),
        )

        for route_name, entity in cases:
            with self.subTest(route_name=route_name):
                response = self.client.post(
                    reverse(f'investments:{route_name}', args=[entity.pk]),
                    follow=True,
                )
                self.assertContains(response, 'cannot be deleted')
                self.assertTrue(type(entity).objects.filter(pk=entity.pk).exists())
        self.assertTrue(
            Investment.objects.filter(title='Historical operation').exists()
        )

    def test_protected_institution_delete_keeps_unused_siblings(self):
        self.create_operation()
        unused_product = InvestmentProduct.objects.create(
            user=self.user,
            institution=self.institution,
            name='Unused sibling',
        )

        response = self.client.post(
            reverse(
                'investments:delete_institution',
                args=[self.institution.pk],
            ),
            follow=True,
        )

        self.assertContains(response, 'cannot be deleted')
        self.assertTrue(
            Institution.objects.filter(pk=self.institution.pk).exists()
        )
        self.assertTrue(
            InvestmentProduct.objects.filter(pk=unused_product.pk).exists()
        )

    def test_deleting_institution_cascades_only_unused_products(self):
        unused_institution = Institution.objects.create(
            user=self.user,
            name='Unused Bank',
        )
        unused_product = InvestmentProduct.objects.create(
            user=self.user,
            institution=unused_institution,
            name='Unused Product',
        )

        response = self.client.post(
            reverse(
                'investments:delete_institution',
                args=[unused_institution.pk],
            )
        )

        self.assertRedirects(response, reverse('investments:settings'))
        self.assertFalse(
            Institution.objects.filter(pk=unused_institution.pk).exists()
        )
        self.assertFalse(
            InvestmentProduct.objects.filter(pk=unused_product.pk).exists()
        )

    def test_delete_confirmation_get_does_not_delete(self):
        response = self.client.get(
            reverse('investments:delete_asset', args=[self.asset.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Asset.objects.filter(pk=self.asset.pk).exists())

    def test_cross_user_update_and_delete_return_404(self):
        cases = (
            (
                'update_institution',
                self.foreign_institution,
                {'name': 'Attacker rename'},
            ),
            ('delete_institution', self.foreign_institution, {}),
            (
                'update_product',
                self.foreign_product,
                {
                    'institution': self.foreign_institution.pk,
                    'name': 'Attacker product',
                },
            ),
            ('delete_product', self.foreign_product, {}),
            (
                'update_asset',
                self.foreign_asset,
                {'name': 'Attacker asset', 'code': 'HACK', 'currency': BASE},
            ),
            ('delete_asset', self.foreign_asset, {}),
        )

        for route_name, entity, payload in cases:
            with self.subTest(route_name=route_name):
                response = self.client.post(
                    reverse(f'investments:{route_name}', args=[entity.pk]),
                    payload,
                )
                self.assertEqual(response.status_code, 404)

        self.foreign_institution.refresh_from_db()
        self.foreign_product.refresh_from_db()
        self.foreign_asset.refresh_from_db()
        self.assertEqual(self.foreign_institution.name, 'Private Bank')
        self.assertEqual(self.foreign_product.name, 'Private Product')
        self.assertEqual(self.foreign_asset.code, 'PRIVATE')

    def test_inconsistent_cross_owner_product_blocks_institution_delete(self):
        institution = Institution.objects.create(
            user=self.user,
            name='Inconsistent Institution',
        )
        foreign_product = InvestmentProduct.objects.create(
            user=self.other_user,
            institution=institution,
            name='Cross-owner Product',
        )

        settings_response = self.client.get(reverse('investments:settings'))
        self.assertNotContains(settings_response, 'Cross-owner Product')

        delete_response = self.client.post(
            reverse(
                'investments:delete_institution',
                args=[institution.pk],
            ),
            follow=True,
        )
        self.assertContains(delete_response, 'owned by another user')
        self.assertTrue(Institution.objects.filter(pk=institution.pk).exists())
        self.assertTrue(
            InvestmentProduct.objects.filter(pk=foreign_product.pk).exists()
        )
