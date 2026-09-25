# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from banking.models import ExchangeRate
from banking.services import create_transfer
from banking.tests import make_account
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import refresh_fx_snapshot


class ExchangeRateViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('rate-owner')
        self.other = get_user_model().objects.create_user('other-rate-owner')
        self.client.force_login(self.user)
        self.rate = ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency='BRL',
            rate=Decimal('5.19'), effective_date=date(2026, 9, 24), notes='Original',
        )
        self.list_url = reverse('banking:exchange_rates')
        self.edit_url = reverse('banking:exchange_rate_update', args=[self.rate.pk])
        self.delete_url = reverse('banking:exchange_rate_delete', args=[self.rate.pk])
        self.data = dict(from_currency='USD', to_currency='BRL', rate='5.25',
                         effective_date='2026-09-24', notes='Corrected')

    def test_list_links_prefilled_form_and_cancel_destinations(self):
        response = self.client.get(self.list_url)
        self.assertContains(response, self.edit_url)
        self.assertContains(response, self.delete_url)
        response = self.client.get(self.edit_url)
        self.assertEqual(response.context['form'].instance, self.rate)
        self.assertEqual(response.context['cancel_url'], self.list_url)
        self.assertContains(response, 'novalidate')
        response = self.client.get(reverse('banking:exchange_rate_create'))
        self.assertEqual(response.context['cancel_url'], self.list_url)

    def test_update_changes_all_fields_and_preserves_owner(self):
        data = {**self.data, 'from_currency': 'EUR', 'to_currency': 'USD',
                'effective_date': '2026-09-23', 'user': self.other.pk}
        self.assertRedirects(self.client.post(self.edit_url, data), self.list_url)
        self.rate.refresh_from_db()
        self.assertEqual(self.rate.user, self.user)
        self.assertEqual(self.rate.from_currency, 'EUR')
        self.assertEqual(self.rate.to_currency, 'USD')
        self.assertEqual(self.rate.rate, Decimal('5.25'))
        self.assertEqual(self.rate.effective_date, date(2026, 9, 23))
        self.assertEqual(self.rate.notes, 'Corrected')

    def test_invalid_edit_preserves_bound_values_and_database(self):
        for values, field in [({'rate': '0'}, 'rate'), ({'rate': '-1'}, 'rate'),
                              ({'to_currency': 'USD'}, 'to_currency'),
                              ({'effective_date': 'invalid'}, 'effective_date')]:
            with self.subTest(values=values):
                response = self.client.post(self.edit_url, {**self.data, **values})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
                self.assertEqual(response.context['form'][field].value(), values[field])
                self.rate.refresh_from_db()
                self.assertEqual(self.rate.rate, Decimal('5.19'))
                self.assertEqual(self.rate.notes, 'Original')

    def test_duplicate_pair_date_rejected_and_other_users_pair_allowed(self):
        ExchangeRate.objects.create(user=self.user, from_currency='EUR', to_currency='BRL',
                                    rate=1, effective_date=self.rate.effective_date)
        duplicate = {**self.data, 'from_currency': 'EUR'}
        for url in [self.edit_url, reverse('banking:exchange_rate_create')]:
            response = self.client.post(url, duplicate)
            self.assertContains(response, 'A record with these values already exists.')
        ExchangeRate.objects.create(user=self.other, **self.data)
        self.assertRedirects(self.client.post(self.edit_url, self.data), self.list_url)

    def test_other_user_cannot_read_change_or_delete_rate(self):
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(self.list_url), self.edit_url)
        for url in [self.edit_url, self.delete_url]:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.data).status_code, 404)
        self.rate.refresh_from_db()
        self.assertEqual(self.rate.rate, Decimal('5.19'))

    def test_authentication_and_csrf_required(self):
        self.client.logout()
        for url in [self.edit_url, self.delete_url]:
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, self.data).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for url in [self.edit_url, self.delete_url]:
            self.assertEqual(client.post(url, self.data).status_code, 403)
        self.assertTrue(ExchangeRate.objects.filter(pk=self.rate.pk).exists())

    def test_delete_requires_post_and_returns_to_list(self):
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cancel_url'], self.list_url)
        self.assertContains(response, 'Conversions already saved')
        self.assertNotContains(response, 'will prevent deletion')
        self.assertTrue(ExchangeRate.objects.filter(pk=self.rate.pk).exists())
        self.assertRedirects(self.client.post(self.delete_url), self.list_url)
        self.assertFalse(ExchangeRate.objects.filter(pk=self.rate.pk).exists())

    def test_edit_and_delete_preserve_saved_transfer_and_investment_snapshots(self):
        source = make_account(self.user, name='Dollar', currency='USD', opening='100')
        destination = make_account(self.user, name='Real')
        transfer = create_transfer(user=self.user, source_account=source,
                                   destination_account=destination, source_amount=Decimal('10'),
                                   destination_amount=Decimal('51.90'), date=self.rate.effective_date)
        transfer.fx_source_rate = self.rate
        transfer.save(update_fields=['fx_source_rate'])
        product = InvestmentProduct.objects.create(user=self.user, bank=source.bank, name='Fund')
        asset = Asset.objects.create(user=self.user, name='Dollar asset', currency='USD')
        operation = Investment.objects.create(user=self.user, product=product, asset=asset,
                                               kind=Investment.Kind.YIELD, quantity=2, unit_price=10,
                                               date=self.rate.effective_date)
        refresh_fx_snapshot(operation)
        fields = ('fx_rate', 'fx_source_currency', 'fx_target_currency',
                  'fx_effective_date', 'fx_snapshot_status')
        snapshots = [tuple(getattr(obj, field) for field in fields) for obj in (transfer, operation)]
        for url, data in [(self.edit_url, self.data), (self.delete_url, {})]:
            self.assertRedirects(self.client.post(url, data), self.list_url)
            for obj, snapshot in zip((transfer, operation), snapshots):
                obj.refresh_from_db()
                self.assertEqual(tuple(getattr(obj, field) for field in fields), snapshot)
        self.assertIsNone(transfer.fx_source_rate_id)
        self.assertIsNone(operation.fx_source_rate_id)
        self.assertEqual(transfer.source_amount, Decimal('10'))
        self.assertEqual(transfer.destination_amount, Decimal('51.90'))
        self.assertEqual(operation.quantity * operation.unit_price, Decimal('20'))
