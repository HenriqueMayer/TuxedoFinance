# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Complete configuration and consultation retain their owned financial context."""
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank
from core.navigation import with_return_url
from investments.forms import AssetForm
from investments.models import Asset, InvestmentProduct, PriceObservation


class InvestmentSubareaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('subarea-owner')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Local bank', color='#315D50')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Brokerage')
        self.asset = Asset.objects.create(pk=1201, user=self.user, name='Local share', code='SHARE',
            valuation_mode='UNITS', asset_class='EQUITY', currency='BRL', opening_product=self.product,
            opening_quantity=Decimal('2'), opening_unit_price=Decimal('100'), opening_date=date(2020, 1, 1))

    def test_catalogue_actions_keep_precise_owned_origins_and_native_archive(self):
        origin = reverse('investments:settings')
        response = self.client.get(origin)
        for route, pk, fragment in [('investments:update_product', self.product.pk, f'product-{self.product.pk}'),
                                    ('investments:update_asset', self.asset.pk, f'asset-{self.asset.pk}')]:
            self.assertContains(response, with_return_url(reverse(route, args=[pk]), origin, fragment=fragment))
        self.assertContains(response, f'id="asset-availability-{self.asset.pk}"')
        self.assertContains(response, reverse('investments:archive_asset', args=[self.asset.pk]))
        self.assertContains(response, '#315D50')
        self.assertNotContains(response, reverse('investments:delete_asset', args=[self.asset.pk]))
        delete_product = with_return_url(reverse('investments:delete_product', args=[self.product.pk]),
            origin, fragment='investment-products')
        self.assertContains(response, delete_product)

    def test_complete_asset_preserves_all_fields_precision_errors_and_cancel(self):
        target = reverse('investments:create_asset')
        origin = reverse('investments:settings') + '#investment-assets'
        values = {'name': 'Fractional share', 'code': 'FRACTION', 'asset_class': 'EQUITY',
            'currency': 'BRL', 'valuation_mode': 'UNITS', 'opening_balance': '0',
            'opening_quantity': '1.12345678', 'opening_unit_price': '2.23456789',
            'opening_product': str(self.product.pk), 'opening_date': '', 'next': origin}
        response = self.client.post(target, values)
        self.assertEqual(response.status_code, 200)
        self.assertIn('opening_date', response.context['form'].errors)
        self.assertEqual(response.context['form']['opening_quantity'].value(), '1.12345678')
        self.assertEqual(response.context['form']['opening_unit_price'].value(), '2.23456789')
        self.assertContains(response, 'Investment details')
        self.assertContains(response, 'Valuation and opening position')
        for name in AssetForm(user=self.user).fields:
            self.assertContains(response, f'name="{name}"')
        self.assertEqual(response.context['return_url'], origin)
        values['opening_date'] = '2020-01-01'
        self.assertRedirects(self.client.post(target, values), origin)
        asset = Asset.objects.get(code='FRACTION', user=self.user)
        self.assertEqual(asset.opening_quantity, Decimal('1.12345678'))
        self.assertEqual(asset.opening_unit_price, Decimal('2.23456789'))

    def test_price_filter_includes_archived_owned_history_and_updates_editor_context(self):
        PriceObservation.objects.create(user=self.user, asset=self.asset, date=date(2026, 9, 1),
            unit_price=Decimal('123.12345678'), source='Local statement')
        self.asset.is_archived = True
        self.asset.save(update_fields=['is_archived'])
        path = reverse('investments:prices')
        response = self.client.get(path, {'asset': self.asset.pk})
        self.assertEqual(list(response.context['observations'])[0].unit_price, Decimal('123.12345678'))
        self.assertIn(self.asset, response.context['price_filter'].fields['asset'].queryset)
        self.assertEqual(response.context['selected_price_asset'], self.asset)
        self.assertContains(response, 'data-live-filters')
        self.assertContains(response, 'id="investment-price-create"')
        self.assertContains(response, 'value="1201" selected')
        target = urlsplit(response.context['price_create_url'])
        self.assertEqual(parse_qs(target.query)['next'], [f'{path}?asset={self.asset.pk}'])
        # An archived record stays consultable but is not offered for a new quote.
        create = self.client.get(response.context['price_create_url'])
        self.assertNotIn(self.asset, create.context['form'].fields['asset'].queryset)

    def test_invalid_or_foreign_price_filter_never_broadens_or_leaks_choices(self):
        PriceObservation.objects.create(user=self.user, asset=self.asset, date=date(2026, 9, 1),
            unit_price=Decimal('100'), source='Owned statement')
        other = get_user_model().objects.create_user('subarea-other')
        foreign = Asset.objects.create(user=other, name='Private share', code='PRIVATE',
            valuation_mode='UNITS', currency='BRL')
        for value in ['not-an-id', str(foreign.pk)]:
            with self.subTest(value=value):
                response = self.client.get(reverse('investments:prices'), {'asset': value})
                self.assertEqual(response.context['paginator'].count, 0)
                self.assertIn('asset', response.context['price_filter'].errors)
                self.assertIsNone(response.context['selected_price_asset'])
                self.assertNotContains(response, 'Private share')
                self.assertNotContains(response, 'Owned statement')
                self.assertNotIn('asset', parse_qs(urlsplit(response.context['price_create_url']).query))

    def test_position_cost_breakdown_is_available_with_its_existing_precision_and_sources(self):
        response = self.client.get(reverse('investments:position_detail', args=[self.product.pk, self.asset.pk]))
        self.assertContains(response, 'explanation-disclosure text-sm" open')
        self.assertContains(response, 'Remaining acquisition cost')
        self.assertContains(response, 'Average acquisition cost per unit')
        self.assertContains(response, reverse('investments:prices') + f'?asset={self.asset.pk}')
        self.assertEqual(response.context['position']['remaining_cost'], Decimal('200'))
