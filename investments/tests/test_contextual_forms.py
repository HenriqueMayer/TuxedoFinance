# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankMovement
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation


class ContextualInvestmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('contextual-investments')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Local bank')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Portfolio')
        self.asset = Asset.objects.create(user=self.user, name='Cash fund', code='CASH', currency='BRL',
            asset_class='FIXED_INCOME', valuation_mode='MONETARY', opening_balance='100',
            opening_product=self.product, opening_date=date(2026, 1, 1))
        self.share = Asset.objects.create(user=self.user, name='Share', code='SHARE', currency='BRL',
            asset_class='EQUITY', valuation_mode='UNITS', opening_quantity='2', opening_unit_price='100',
            opening_product=self.product, opening_date=date(2026, 1, 1))
        self.origin = f'/investments/?section=portfolio#position-{self.product.pk}-{self.asset.pk}'
        self.data = {'product': str(self.product.pk), 'asset': str(self.asset.pk), 'kind': 'YIELD',
            'date': '2026-01-10', 'yield_input_mode': 'YIELD_AMOUNT', 'amount': '5', 'fees': '0', 'next': self.origin}

    def test_position_actions_are_explicit_owned_and_return_to_correct_device_anchor(self):
        response = self.client.get(reverse('investments:list'))
        product = response.context['portfolio_groups'][0]['products'][0]
        row = next(asset for asset in product['assets'] if asset['id'] == self.asset.pk)
        for kind in Investment.Kind.values:
            query = parse_qs(urlsplit(row['action_urls'][kind.lower()]).query)
            self.assertEqual(query['kind'], [kind])
            self.assertEqual(query['product'], [str(self.product.pk)])
            self.assertEqual(query['asset'], [str(self.asset.pk)])
            self.assertEqual(query['next'], [f'/investments/#position-{self.product.pk}-{self.asset.pk}'])
        query = parse_qs(urlsplit(row['mobile_action_urls']['yield']).query)
        self.assertTrue(query['next'][0].endswith('-mobile'))
        self.assertContains(response, row['update_url'].replace('&', '&amp;'))
        chooser = self.client.get(reverse('investments:position_update', args=[self.product.pk, self.share.pk]))
        self.assertContains(chooser, 'Contribute')
        self.assertContains(chooser, 'Redeem')
        self.assertContains(chooser, 'Record yield')
        self.assertContains(chooser, 'Update price')

    def test_shortcut_keeps_yield_input_and_funding_explicit(self):
        response = self.client.get(reverse('investments:create'), {'product': self.product.pk,
            'asset': self.asset.pk, 'kind': 'YIELD', 'next': self.origin})
        form = response.context['form']
        self.assertEqual(str(form['asset'].value()), str(self.asset.pk))
        self.assertEqual(str(form['product'].value()), str(self.product.pk))
        self.assertEqual(form['kind'].value(), 'YIELD')
        self.assertFalse(form['yield_input_mode'].value())
        self.assertFalse(form['funding_source'].value())
        self.assertEqual(response.context['return_url'], self.origin)

    def test_save_and_invalid_post_preserve_origin_without_bank_movement(self):
        url = reverse('investments:create') + '?' + urlencode({'next': self.origin})
        invalid = self.client.post(url, {**self.data, 'amount': ''})
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.context['return_url'], self.origin)
        self.assertEqual(str(invalid.context['form']['asset'].value()), str(self.asset.pk))
        self.assertFalse(Investment.objects.filter(user=self.user).exists())
        response = self.client.post(url, self.data)
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        self.assertEqual(Investment.objects.get(user=self.user).amount, Decimal('5'))
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_foreign_shortcut_records_and_unknown_kinds_are_not_preselected(self):
        other = get_user_model().objects.create_user('private-investment-owner')
        other_bank = Bank.objects.create(user=other, name='Private bank')
        product = InvestmentProduct.objects.create(user=other, bank=other_bank, name='Private product')
        asset = Asset.objects.create(user=other, name='Private asset', code='PRIVATE')
        response = self.client.get(reverse('investments:create'), {'product': product.pk, 'asset': asset.pk, 'kind': 'UNKNOWN'})
        self.assertFalse(response.context['form']['product'].value())
        self.assertFalse(response.context['form']['asset'].value())
        self.assertFalse(response.context['form']['kind'].value())
        response = self.client.post(reverse('investments:create'), {**self.data, 'asset': asset.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Investment.objects.filter(user=self.user).exists())

    def test_observed_price_save_cancel_and_error_return_to_position(self):
        origin = f'/investments/#position-{self.product.pk}-{self.share.pk}'
        url = reverse('investments:create_price') + '?' + urlencode({'asset': self.share.pk, 'next': origin})
        response = self.client.get(url)
        self.assertEqual(response.context['return_url'], origin)
        self.assertEqual(str(response.context['form']['asset'].value()), str(self.share.pk))
        payload = {'asset': self.share.pk, 'date': '2026-01-10', 'unit_price': '125', 'source': '', 'next': origin}
        invalid = self.client.post(url, payload)
        self.assertEqual(invalid.context['return_url'], origin)
        self.assertFalse(PriceObservation.objects.filter(user=self.user).exists())
        self.assertRedirects(self.client.post(url, {**payload, 'source': 'Statement'}), origin, fetch_redirect_response=False)
        self.share.refresh_from_db()
        self.assertEqual(self.share.opening_quantity, Decimal('2'))
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_price_list_add_edit_and_delete_keep_selected_asset_and_page(self):
        observation = PriceObservation.objects.create(user=self.user, asset=self.share,
            date=date(2026, 1, 10), unit_price='120', source='Statement')
        origin = reverse('investments:prices') + '?' + urlencode({'asset': self.share.pk, 'page': '1'})
        response = self.client.get(origin)
        self.assertEqual(parse_qs(urlsplit(response.context['price_create_url']).query)['next'], [origin])
        self.assertEqual(self.client.get(reverse('investments:update_price', args=[observation.pk]), {'next': origin}).context['return_url'], origin)
        self.assertRedirects(self.client.post(reverse('investments:delete_price', args=[observation.pk]), {'next': origin}),
                             origin, fetch_redirect_response=False)

    def test_external_return_falls_back_to_history(self):
        self.assertRedirects(self.client.post(reverse('investments:create'), {**self.data, 'next': '//external.test/'}),
                             reverse('investments:operations'), fetch_redirect_response=False)

    def test_unused_asset_delete_submits_the_origin_in_the_primary_form(self):
        asset = Asset.objects.create(user=self.user, name='Unused', code='UNUSED')
        url = reverse('investments:delete_asset', args=[asset.pk])
        response = self.client.get(url, {'next': self.origin})
        self.assertContains(response, f'name="next" value="{self.origin}"')
        self.assertRedirects(self.client.post(url, {'next': self.origin}), self.origin, fetch_redirect_response=False)
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())
