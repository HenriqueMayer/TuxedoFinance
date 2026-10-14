# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CreditCard, ExchangeRate
from banking.services import get_planning_availability
from investments.models import Asset, InvestmentProduct, PositionPlanningSetting


class BankingWorkspaceOrganizationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('organized-banking-owner')
        self.other = get_user_model().objects.create_user('organized-banking-other')
        self.bank = Bank.objects.create(user=self.user, name='Real bank', color='#24594A')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Current', currency='BRL', opening_balance=1000)
        self.reserve = BankAccount.objects.create(user=self.user, bank=self.bank, name='Emergency account', currency='BRL', opening_balance=200, planning_enabled=False)
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Daily application', purpose='MONTHLY_CASH')
        self.asset = Asset.objects.create(user=self.user, name='Emergency asset', code='EMERGENCY', currency='BRL', valuation_mode='MONETARY', opening_product=self.product, opening_balance=300)
        PositionPlanningSetting.objects.create(user=self.user, product=self.product, asset=self.asset, planning_enabled=False)
        self.card = CreditCard.objects.create(user=self.user, account=self.account, name='Daily card', closing_day=1, due_day=10)
        self.client.force_login(self.user)

    def test_bank_disclosures_and_separate_closed_reserves_keep_all_rows_reviewable(self):
        response = self.client.get(reverse('banking:list'))
        self.assertContains(response, f'<details id="bank-{self.bank.pk}" class="surface-panel bank-panel bank-disclosure" >')
        self.assertContains(response, f'id="bank-reserves-{self.bank.pk}" class="reserve-disclosure" >')
        self.assertContains(response, f'id="account-row-{self.account.pk}"', count=1)
        self.assertContains(response, f'id="account-row-{self.reserve.pk}"', count=1)
        self.assertContains(response, f'id="cash-position-{self.product.pk}-{self.asset.pk}"', count=1)
        bank = list(response.context['banks'])[0]
        self.assertEqual([row['account'] for row in bank.included_rows], [self.account])
        self.assertEqual([row['account'] for row in bank.reserved_rows], [self.reserve])
        self.assertEqual(response.context['availability']['available_total'], Decimal('1000'))
        searched = self.client.get(reverse('banking:list'), {'q': self.asset.name})
        self.assertEqual(list(searched.context['banks'])[0], self.bank)
        self.assertTrue(list(searched.context['banks'])[0].is_open)
        self.assertContains(searched, 'data-live-filters')

    def test_account_and_position_native_or_fragment_toggle_moves_rows_and_keeps_money(self):
        origin = reverse('banking:list') + '?q=Real'
        account_url = reverse('banking:account_planning', args=[self.account.pk])
        response = self.client.post(account_url, {'enabled': '0', 'return_to': 'list', 'next': origin})
        self.assertEqual(response.url, origin + f'&open={self.bank.pk}&reserves={self.bank.pk}#account-row-{self.account.pk}')
        self.assertEqual(self.account.current_balance(), Decimal('1000'))
        target = f'bank-positions-{self.bank.pk}'
        cash_url = reverse('banking:position_planning', args=[self.product.pk, self.asset.pk])
        response = self.client.post(cash_url, {'enabled': '1', 'return_to': 'list'}, HTTP_HX_TARGET=target)
        self.assertContains(response, f'id="{target}"')
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.assertTrue(PositionPlanningSetting.objects.get(product=self.product, asset=self.asset).planning_enabled)
        self.assertEqual(get_planning_availability(self.user)['available_total'], Decimal('300'))
        self.assertFalse(BankMovement.objects.exists())

    def test_position_toggle_requires_owned_known_pair_explicit_post_and_csrf(self):
        url = reverse('banking:position_planning', args=[self.product.pk, self.asset.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'enabled': 'invalid'}).status_code, 400)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(url, {'enabled': '1'}).status_code, 403)
        unknown = Asset.objects.create(user=self.user, name='Unlinked', code='UNKNOWN', currency='BRL', valuation_mode='MONETARY')
        self.assertEqual(self.client.post(reverse('banking:position_planning', args=[self.product.pk, unknown.pk]), {'enabled': '1'}).status_code, 404)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, {'enabled': '1'}).status_code, 404)
        self.assertFalse(PositionPlanningSetting.objects.get(product=self.product, asset=self.asset).planning_enabled)

    def test_invoice_filters_compose_owned_card_bank_month_status_and_search_without_writes(self):
        invoice = CardInvoice.objects.create(user=self.user, card=self.card, reference_month=date(2026, 10, 1), due_date=date(2026, 11, 10), amount=120, status='PARTIAL', manual_settlement=True)
        CardInvoice.objects.create(user=self.user, card=self.card, reference_month=date(2026, 9, 1), due_date=date(2026, 10, 10), amount=80, status='SCHEDULED')
        original = list(CardInvoice.objects.values())
        with patch('banking.views.sync_user_ledger'):
            response = self.client.get(reverse('banking:invoices'), {'q': 'Daily', 'bank': self.bank.pk, 'card': self.card.pk, 'month': '2026-10', 'status': 'PARTIAL'})
        self.assertEqual(list(response.context['invoices']), [invoice])
        self.assertEqual(response.context['selected_card'], self.card)
        self.assertContains(response, 'data-live-results="invoice-results"')
        self.assertContains(response, 'October 2026')
        self.assertEqual(list(CardInvoice.objects.values()), original)
        with patch('banking.views.sync_user_ledger'):
            for key, value in [('card', '9' * 5000), ('bank', '0' + str(self.bank.pk)), ('card', '١')]:
                self.assertEqual(self.client.get(reverse('banking:invoices'), {key: value}).status_code, 404)
            invalid = self.client.get(reverse('banking:invoices'), {'month': 'not-a-month'})
        self.assertIn('month', invalid.context['filter_form'].errors)
        self.assertContains(invalid, 'value="not-a-month"')
        self.assertEqual(list(invalid.context['invoices']), [])

    def test_foreign_invoice_filter_is_rejected_and_fx_filters_preserve_rate_evidence(self):
        private_bank = Bank.objects.create(user=self.other, name='Private')
        private_account = BankAccount.objects.create(user=self.other, bank=private_bank, name='Private', currency='BRL')
        private_card = CreditCard.objects.create(user=self.other, account=private_account, name='Private', closing_day=1, due_day=10)
        for key, value in [('bank', private_bank.pk), ('card', private_card.pk)]:
            self.assertEqual(self.client.get(reverse('banking:invoices'), {key: value}).status_code, 404)
        rate = ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='5.12', effective_date=date(2026, 10, 2), notes='Reference evidence')
        ExchangeRate.objects.create(user=self.user, from_currency='EUR', to_currency='BRL', rate='6.12', effective_date=date(2026, 10, 2))
        ExchangeRate.objects.create(user=self.other, from_currency='USD', to_currency='BRL', rate='9.12', effective_date=date(2026, 10, 2), notes='Reference evidence')
        original = list(ExchangeRate.objects.values())
        url = reverse('banking:exchange_rates')
        response = self.client.get(url, {'from_currency': 'USD', 'to_currency': 'BRL', 'date_from': '2026-10-01', 'date_to': '2026-10-03', 'q': 'evidence'})
        self.assertEqual(list(response.context['rates']), [rate])
        self.assertContains(response, 'data-live-results="rate-results"')
        invalid = self.client.get(url, {'date_from': '2026-10-03', 'date_to': '2026-10-01'})
        self.assertIn('date_to', invalid.context['filter_form'].errors)
        self.assertEqual(list(invalid.context['rates']), [])
        self.assertEqual(list(ExchangeRate.objects.values()), original)

    def test_rate_edit_delete_keep_filtered_origin_and_reject_external_return(self):
        rate = ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
            rate='5.12', effective_date=date(2026, 10, 2), notes='Evidence')
        origin = reverse('banking:exchange_rates') + '?from_currency=USD&q=Evidence'
        edit = reverse('banking:exchange_rate_update', args=[rate.pk])
        response = self.client.get(edit, {'next': origin})
        self.assertEqual(response.context['cancel_url'], origin)
        response = self.client.post(edit, {'from_currency': 'USD', 'to_currency': 'BRL', 'rate': '5.22',
            'effective_date': '2026-10-02', 'notes': 'Evidence', 'next': origin})
        self.assertEqual(response.url, origin)
        delete = reverse('banking:exchange_rate_delete', args=[rate.pk])
        response = self.client.get(delete, {'next': origin})
        self.assertEqual(response.context['cancel_url'], origin)
        self.assertContains(response, 'name="next"')
        self.assertEqual(self.client.post(delete, {'next': '//external.example/path'}).url, reverse('banking:exchange_rates'))
        self.assertFalse(ExchangeRate.objects.filter(pk=rate.pk).exists())
