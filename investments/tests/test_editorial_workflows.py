# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Investment consultation and editor context stay coherent after partial GETs."""
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from banking.models import Bank, ExchangeRate
from core.navigation import with_return_url
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation


class InvestmentEditorialWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('investment-editorial-owner')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Local institution', color='#315D50')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Portfolio')
        self.cash = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Cash pot', purpose='MONTHLY_CASH')
        self.share = Asset.objects.create(user=self.user, name='Local share', code='LOCAL',
            currency='BRL', valuation_mode='UNITS', asset_class='EQUITY',
            opening_product=self.product, opening_quantity='2', opening_unit_price='200', opening_date=date(2020, 1, 1))
        Asset.objects.create(user=self.user, name='Cash reserve', code='CASH',
            currency='BRL', valuation_mode='MONETARY', opening_product=self.cash,
            opening_balance='100', opening_date=date(2020, 1, 1))

    def foreign_asset(self):
        return Asset.objects.create(user=self.user, name='Foreign holding', code='FOREIGN',
            currency='USD', valuation_mode='MONETARY', opening_product=self.product,
            opening_balance='10', opening_date=date(2020, 1, 1))

    def test_chart_partial_includes_scoped_results_and_evidence_notices(self):
        chart_url = reverse('analytics:investments')
        overall = self.client.get(chart_url)
        self.assertEqual(overall.context['portfolio_snapshot']['cost_total'], Decimal('500'))
        self.assertContains(overall, 'id="investment-performance"', count=1)
        response = self.client.get(chart_url, {'scope': 'cash', 'total_offset': '-1', 'flow_offset': '0'},
            HTTP_HX_REQUEST='true', HTTP_HX_TARGET='investments-charts')
        self.assertNotContains(response, '<html')
        self.assertContains(response, 'id="investment-performance"', count=1)
        self.assertContains(response, 'id="investment-evolution"')
        self.assertContains(response, 'id="investment-cashflow"')
        self.assertEqual(response.context['portfolio_snapshot']['cost_total'], Decimal('100'))
        self.assertNotContains(response, 'Results are limited to the recorded evidence.')
        self.assertContains(overall, 'Results are limited to the recorded evidence.')

    def test_rate_editor_from_holdings_keeps_scope_search_and_return_anchor(self):
        self.foreign_asset()
        rate = ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
            rate='5', effective_date=date(2020, 1, 1))
        origin = reverse('investments:list') + '?scope=portfolio&q=Foreign'
        target = with_return_url(reverse('banking:exchange_rate_update', args=[rate.pk]),
            origin, fragment='position-value-summary')
        response = self.client.get(origin)
        self.assertContains(response, f'href="{escape(target)}"')
        editor = self.client.get(target)
        destination = origin + '#position-value-summary'
        self.assertEqual(editor.context['return_url'], destination)
        self.assertRedirects(self.client.post(target, {'from_currency': 'USD', 'to_currency': 'BRL',
            'rate': '5', 'effective_date': '2020-01-01', 'next': destination}), destination,
            fetch_redirect_response=False)

    def test_fx_review_links_and_operation_rate_registration_keep_chart_context(self):
        foreign = self.foreign_asset()
        operation = Investment.objects.create(user=self.user, product=self.product, asset=foreign,
            kind='YIELD', amount='2', date=date(2026, 1, 10))
        origin = reverse('analytics:investments') + '?scope=portfolio&total_offset=-1&flow_offset=0'
        response = self.client.get(origin)
        self.assertTrue(response.context['chart_fx_issues'])
        for issue in response.context['chart_fx_issues']:
            if issue['reason'] != 'base':
                expected = with_return_url(issue['rate_url'], origin, fragment='investments-charts')
                self.assertContains(response, f'href="{escape(expected)}"')
            if issue.get('operation_url'):
                expected = with_return_url(issue['operation_url'], origin, fragment='investments-charts')
                self.assertContains(response, f'href="{escape(expected)}"')
        editor_url = with_return_url(reverse('investments:update', args=[operation.pk]), origin,
            fragment='investments-charts')
        editor = self.client.get(editor_url)
        self.assertIn('capture_missing_fx', editor.context['form'].fields)
        self.assertContains(editor, escape(editor.context['exchange_rate_create_url']))
        rate_query = parse_qs(urlsplit(editor.context['exchange_rate_create_url']).query)
        self.assertEqual(rate_query['next'], [editor_url + '#investment-operation-form'])
        self.assertEqual(rate_query['from_currency'], ['USD'])

    def test_price_history_exposes_owned_asset_and_preserves_precise_editor_origin(self):
        observation = PriceObservation.objects.create(user=self.user, asset=self.share,
            date=date(2026, 1, 10), unit_price='123.12345678', source='Local statement')
        origin = reverse('investments:prices') + '?' + urlencode({'asset': self.share.pk, 'page': '1'})
        response = self.client.get(origin)
        self.assertEqual(response.context['selected_price_asset'], self.share)
        self.assertContains(response, 'Local share · LOCAL')
        self.assertContains(response, 'href="/investments/prices/" aria-label="Clear filters"')
        editor_url = with_return_url(reverse('investments:update_price', args=[observation.pk]), origin)
        self.assertContains(response, escape(editor_url))
        invalid = self.client.post(editor_url, {'asset': self.share.pk, 'date': '2026-01-10',
            'unit_price': '123.12345678', 'source': '', 'next': origin})
        self.assertEqual(invalid.context['return_url'], origin)
        self.assertEqual(invalid.context['form']['unit_price'].value(), '123.12345678')
        self.assertTrue(invalid.context['form']['source'].errors)
        self.assertRedirects(self.client.post(editor_url, {'asset': self.share.pk, 'date': '2026-01-10',
            'unit_price': '123.12345678', 'source': 'Local statement', 'next': origin}),
            origin, fetch_redirect_response=False)

    def test_positions_use_general_emoji_and_institutions_keep_registered_color(self):
        response = self.client.get(reverse('investments:list'))
        self.assertContains(response, '💰')
        self.assertNotContains(response, 'class="bank-marker shrink-0"')
        configuration = self.client.get(reverse('investments:settings'))
        self.assertContains(configuration, '#315D50')
        detail = self.client.get(reverse('investments:position_detail', args=[self.product.pk, self.share.pk]))
        self.assertContains(detail, '💰')

    def test_archived_configuration_links_keep_the_owned_record_and_origin(self):
        self.share.is_archived = True
        self.share.save(update_fields=['is_archived'])
        for route in ('investments:position_detail', 'investments:position_update'):
            with self.subTest(route=route):
                origin = reverse(route, args=[self.product.pk, self.share.pk])
                response = self.client.get(origin)
                target = response.context['configuration_url']
                parsed = urlsplit(target)
                self.assertEqual(parsed.path, reverse('investments:settings'))
                self.assertEqual(parsed.fragment, f'asset-{self.share.pk}')
                self.assertEqual(parse_qs(parsed.query), {'archived': [str(self.share.pk)], 'next': [origin]})
                self.assertContains(response, f'href="{escape(target)}" hx-swap="innerHTML show:none"')
                configuration = self.client.get(target)
                self.assertTrue(configuration.context['show_archived_assets'])
                self.assertIn(self.share, configuration.context['archived_assets'])
