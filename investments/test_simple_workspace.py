# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from banking.models import Bank, BankMovement
from investments.models import Asset, Investment, InvestmentProduct, PositionPlanningSetting
from investments.positions import get_portfolio_valuation


class SimpleInvestmentWorkspaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('simple-investments')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Local institution')
        self.data = {'institution': self.bank.pk, 'name': 'My application', 'valuation_mode': 'MONETARY',
            'purpose': 'INVESTMENT', 'currency': 'BRL', 'opening_balance': '100',
            'opening_date': '2025-01-01', 'next': '/investments/?q=application'}

    def create(self, **changes):
        response = self.client.post(reverse('investments:guided_create'), {**self.data, **changes})
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.status_code == 200 else '')
        return Asset.objects.get(user=self.user), response

    def test_guided_opening_creates_owned_configuration_without_cash_debit(self):
        asset, response = self.create()
        self.assertEqual(asset.opening_balance, Decimal('100'))
        self.assertEqual(asset.opening_date, date(2025, 1, 1))
        self.assertEqual(asset.opening_product.bank, self.bank)
        self.assertEqual(asset.name, asset.opening_product.name)
        self.assertTrue(asset.code.startswith('APP-'))
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())
        self.assertFalse(Investment.objects.filter(user=self.user).exists())
        self.assertEqual(parse_qs(urlsplit(response.url).query)['next'], ['/investments/?q=application'])
        self.assertEqual(get_portfolio_valuation(self.user)['total'], Decimal('100'))

    def test_zero_registration_is_findable_without_opening_or_money(self):
        asset, _ = self.create(opening_balance='0', opening_date='')
        self.assertIsNone(asset.opening_date)
        self.assertFalse(asset.has_opening_position)
        self.assertEqual(get_portfolio_valuation(self.user)['positions'], [])
        response = self.client.get(reverse('investments:list'))
        self.assertEqual(response.context['position_count'], 1)
        self.assertEqual(response.context['simulated_total'], Decimal('0'))
        self.assertContains(response, 'Ready for the first operation')
        self.assertEqual(self.client.get(reverse('investments:position_update', args=[asset.opening_product_id, asset.pk])).status_code, 200)

    def test_unit_opening_is_cost_not_a_market_quote(self):
        asset, _ = self.create(valuation_mode='UNITS', purpose='', opening_balance='999',
            opening_quantity='2', opening_unit_price='50')
        self.assertEqual(asset.opening_balance, Decimal('0'))
        self.assertEqual(asset.opening_quantity, Decimal('2'))
        self.assertEqual(get_portfolio_valuation(self.user)['total'], Decimal('100'))
        response = self.client.get(reverse('investments:list'))
        self.assertContains(response, 'At remaining acquisition cost')
        self.assertContains(response, 'Some unit positions use acquisition cost')

    def test_invalid_opening_and_foreign_institution_create_nothing(self):
        response = self.client.post(reverse('investments:guided_create'), {**self.data, 'opening_date': ''})
        self.assertFormError(response.context['form'], 'opening_date', 'Enter the date of the opening position.')
        other = get_user_model().objects.create_user('foreign-institution')
        bank = Bank.objects.create(user=other, name='Private bank')
        response = self.client.post(reverse('investments:guided_create'), {**self.data, 'institution': bank.pk})
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(Asset.objects.filter(user=self.user).exists())
        self.assertFalse(InvestmentProduct.objects.filter(user=self.user).exists())

    def test_new_institution_and_all_configuration_roll_back_on_model_error(self):
        with patch('investments.models.Asset.full_clean', side_effect=ValidationError({'code': 'Invalid identifier'})):
            response = self.client.post(reverse('investments:guided_create'),
                {**self.data, 'new_institution': 'on', 'institution_name': 'New institution'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Bank.objects.filter(user=self.user, name='New institution').exists())
        self.assertFalse(InvestmentProduct.objects.filter(user=self.user).exists())

    def test_cash_planning_is_explicit_and_does_not_change_holdings(self):
        asset, _ = self.create(purpose='MONTHLY_CASH')
        self.assertFalse(PositionPlanningSetting.objects.get(user=self.user, asset=asset).planning_enabled)
        self.assertEqual(get_portfolio_valuation(self.user)['total'], Decimal('100'))
        self.assertEqual(self.client.get(reverse('investments:list')).context['position_count'], 1)
        self.assertEqual(self.client.get(reverse('investments:list'), {'scope': 'portfolio'}).context['position_count'], 0)
        self.assertEqual(self.client.get(reverse('investments:list'), {'section': 'cash'}).context['position_count'], 1)

    def test_search_filters_positions_and_leaves_scope_total_and_native_form(self):
        asset, _ = self.create()
        response = self.client.get(reverse('investments:list'), {'q': 'institution'})
        self.assertEqual(response.context['position_count'], 1)
        self.assertEqual(response.context['simulated_total'], Decimal('100'))
        self.assertContains(response, 'data-live-results="investment-position-list"')
        self.assertContains(response, 'method="get"')
        response = self.client.get(reverse('investments:list'), {'q': 'not found'})
        self.assertEqual(response.context['position_count'], 0)
        self.assertEqual(response.context['simulated_total'], Decimal('100'))
        self.assertContains(response, 'No positions match these filters.')

    def test_position_update_has_exact_owned_context_and_safe_return(self):
        asset, _ = self.create()
        path = reverse('investments:position_update', args=[asset.opening_product_id, asset.pk])
        response = self.client.get(path, {'next': '/investments/?q=application#position-1'})
        for kind in Investment.Kind.values:
            values = parse_qs(urlsplit(response.context['actions'][kind.lower()]).query)
            self.assertEqual(values['product'], [str(asset.opening_product_id)])
            self.assertEqual(values['asset'], [str(asset.pk)])
            self.assertEqual(values['kind'], [kind])
            self.assertEqual(values['next'], ['/investments/?q=application#position-1'])
        self.assertNotContains(response, 'Update price')
        response = self.client.get(path, {'next': '//foreign.test/'})
        self.assertEqual(response.context['return_url'], reverse('investments:position_detail', args=[asset.opening_product_id, asset.pk]))
        other = get_user_model().objects.create_user('private-position')
        bank = Bank.objects.create(user=other, name='Private')
        product = InvestmentProduct.objects.create(user=other, bank=bank, name='Private')
        self.assertEqual(self.client.get(reverse('investments:position_update', args=[product.pk, asset.pk])).status_code, 404)

    def test_archived_position_links_to_its_owned_restore_disclosure_without_posting(self):
        asset, _ = self.create()
        asset.is_archived = True
        asset.save(update_fields=['is_archived'])
        before = list(Asset.objects.filter(user=self.user).values())
        for route in ('investments:position_detail', 'investments:position_update'):
            path = reverse(route, args=[asset.opening_product_id, asset.pk])
            response = self.client.get(path, {'next': '//foreign.test/'})
            target = response.context['configuration_url']
            parts = urlsplit(target)
            self.assertEqual(parts.path, reverse('investments:settings'))
            self.assertEqual(parts.fragment, f'asset-{asset.pk}')
            self.assertEqual(parse_qs(parts.query)['archived'], [str(asset.pk)])
            self.assertTrue(parse_qs(parts.query)['next'][0].startswith(path))
            self.assertContains(response, f'href="{escape(target)}"')
            self.assertNotContains(response, 'You can edit this operation')
            settings = self.client.get(target)
            self.assertTrue(settings.context['show_archived_assets'])
            self.assertContains(settings, f'id="asset-availability-{asset.pk}"')
            self.assertContains(settings, 'Restore')
        self.assertEqual(list(Asset.objects.filter(user=self.user).values()), before)
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())
        self.assertFalse(Investment.objects.filter(user=self.user).exists())
        other = get_user_model().objects.create_user('private-archived-holding')
        bank = Bank.objects.create(user=other, name='Private archived institution')
        product = InvestmentProduct.objects.create(user=other, bank=bank, name='Private archived product')
        private = Asset.objects.create(user=other, name='Private archived holding', code='PRIVATE',
            currency='BRL', asset_class='OTHER', valuation_mode='MONETARY', opening_product=product,
            is_archived=True)
        for route in ('investments:position_detail', 'investments:position_update'):
            self.assertEqual(self.client.get(reverse(route, args=[product.pk, private.pk])).status_code, 404)
        settings = self.client.get(reverse('investments:settings'), {'archived': private.pk})
        self.assertFalse(settings.context['show_archived_assets'])
        self.assertNotContains(settings, private.name)

    def test_duplicate_configuration_is_recovered_and_advanced_routes_remain(self):
        self.create(code='MYAPP')
        response = self.client.post(reverse('investments:guided_create'), self.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(Asset.objects.filter(user=self.user).count(), 1)
        for route in ['investments:charts', 'investments:operations', 'investments:prices', 'investments:settings']:
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_brazilian_decimal_opening_retains_bound_input_before_recovery(self):
        self.client.cookies['django_language'] = 'pt-br'
        values = {**self.data, 'opening_balance': '1.000,00', 'opening_date': ''}
        response = self.client.post(reverse('investments:guided_create'), values)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['opening_balance'].value(), '1.000,00')
        self.assertTrue(response.context['form'].errors.get('opening_date'))
        self.assertFalse(Asset.objects.filter(user=self.user).exists())
        response = self.client.post(reverse('investments:guided_create'), {**values, 'opening_date': '01/01/2026'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Asset.objects.get(user=self.user).opening_balance, Decimal('1000'))
