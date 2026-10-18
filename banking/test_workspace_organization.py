# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CreditCard, DebitCard, ExchangeRate
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

    def test_overview_links_to_owned_banks_and_details_keep_separate_reserves(self):
        response = self.client.get(reverse('banking:list'))
        self.assertContains(response, f'id="bank-{self.bank.pk}"')
        self.assertContains(response, reverse('banking:detail', args=[self.bank.pk]))
        self.assertNotContains(response, 'bank-filter-form')
        self.assertNotContains(response, 'account-row-')
        self.assertEqual(response.context['availability']['available_total'], Decimal('1000'))
        # Retired search links show the complete owned overview, never a hidden subset.
        response = self.client.get(reverse('banking:list'), {'q': 'missing'})
        self.assertEqual(list(response.context['banks']), [self.bank])
        detail = self.client.get(reverse('banking:detail', args=[self.bank.pk]))
        for marker in [f'account-row-{self.account.pk}', f'account-row-{self.reserve.pk}',
                       f'cash-position-{self.product.pk}-{self.asset.pk}']:
            self.assertContains(detail, f'id="{marker}"', count=1)
        self.assertContains(detail, f'id="bank-reserves-{self.bank.pk}" class="reserve-disclosure" >')
        self.assertContains(detail, 'id="planning-availability"', count=1)

    def test_bank_sections_keep_primary_actions_and_consolidate_card_management(self):
        debit_card = DebitCard.objects.create(user=self.user, account=self.account, name='Daily debit')
        before = list(CreditCard.objects.values())
        response = self.client.get(reverse('banking:list'))
        self.assertNotContains(response, '/roadmap/')
        with patch('banking.views.sync_user_ledger'):
            detail = self.client.get(reverse('banking:detail', args=[self.bank.pk]))
        # One credit-card presentation retains daily and administrative actions.
        self.assertContains(detail, f'id="credit-card-{self.card.pk}"', count=1)
        self.assertContains(detail, f'<p class="text-sm font-medium">{self.card.name}</p>', count=1, html=True)
        self.assertContains(detail, 'closes 1, due 10')
        self.assertContains(detail, 'Automatic settlement on due date')
        for name, pk in [('credit_card_update', self.card.pk), ('credit_card_delete', self.card.pk),
                         ('debit_card_update', debit_card.pk), ('debit_card_delete', debit_card.pk)]:
            self.assertContains(detail, reverse('banking:' + name, args=[pk]))
        self.assertContains(detail, 'Invoices for Daily card')
        self.assertContains(detail, 'New transaction on Daily card')
        self.assertContains(detail, 'Add debit card')
        self.assertContains(detail, 'Add credit card')
        self.assertRegex(detail.content.decode(), r'Opening balance: BRL 1[.,\s]000[.,]00')
        self.assertEqual(list(CreditCard.objects.values()), before)
        self.assertFalse(BankMovement.objects.exists())

    def test_compact_row_actions_keep_owned_post_state_and_available_value_separate(self):
        origin = reverse('banking:detail', args=[self.bank.pk])
        response = self.client.get(origin)
        html = response.content.decode()
        row = html.split(f'<article id="account-row-{self.account.pk}"', 1)[1].split('</article>', 1)[0]
        amounts = row.split('<dl class="account-balance-grid">', 1)[1].split('</dl>', 1)[0]
        self.assertNotIn('<form', amounts)
        self.assertIn(f'id="planning-toggle-{self.account.pk}"', row)
        self.assertIn('name="enabled" value="0"', row)
        self.assertIn(f'name="next" value="{origin}"', row)
        self.assertIn(reverse('banking:account_planning', args=[self.account.pk]), row)
        self.assertIn('aria-label="Update Current"', row)
        self.assertIn('<span aria-hidden="true">⋯</span>', row)
        self.assertIn('class="sr-only">Update account</span>', row)
        self.assertEqual(response.context['availability']['available_total'], Decimal('1000'))
        self.assertEqual(self.account.current_balance(), Decimal('1000'))
        self.assertFalse(BankMovement.objects.exists())

    def test_card_details_never_leak_foreign_legacy_links_in_page_or_post_fragment(self):
        CreditCard.objects.create(user=self.other, account=self.account, name='Private credit', closing_day=1, due_day=10)
        DebitCard.objects.create(user=self.other, account=self.account, name='Private debit')
        responses = [self.client.get(reverse('banking:detail', args=[self.bank.pk])),
                     self.client.post(reverse('banking:account_planning', args=[self.account.pk]),
                                      {'enabled': '1'}, HTTP_HX_TARGET=f'bank-positions-{self.bank.pk}'),
                     self.client.post(reverse('banking:account_planning', args=[self.account.pk]),
                                      {'enabled': '1'}, HTTP_HX_TARGET=f'account-row-{self.account.pk}')]
        for response in responses:
            self.assertContains(response, 'Daily card')
            self.assertNotContains(response, 'Private credit')
            self.assertNotContains(response, 'Private debit')

    def test_compact_filter_criteria_are_native_complete_and_reveal_invalid_values(self):
        with patch('banking.views.sync_user_ledger'):
            unfiltered = self.client.get(reverse('banking:invoices'))
            filtered = self.client.get(reverse('banking:card_invoices', args=[self.card.pk]), {'q': 'Daily', 'bank': self.bank.pk, 'month': '2026-10', 'status': 'PAID'})
            invalid = self.client.get(reverse('banking:invoices'), {'month': 'not-a-month'})
            empty_month = self.client.get(reverse('banking:invoices'), {'month': '  '})
        self.assertContains(unfiltered, '<div id="invoice-extra-filters" class="bank-consultation-criteria">')
        self.assertEqual(unfiltered.context['active_filter_count'], 0)
        self.assertEqual(filtered.context['active_filter_count'], 3)
        self.assertContains(filtered, '3 active')
        self.assertContains(filtered, 'id="invoice-clear-control"')
        self.assertContains(filtered, 'data-live-reset')
        for name in ('q', 'month', 'bank', 'status'):
            self.assertContains(unfiltered, f'name="{name}"')
        self.assertContains(unfiltered, 'data-month-filter')
        self.assertContains(unfiltered, 'id="invoice-filter-month"', count=1)
        self.assertContains(invalid, '<div id="invoice-extra-filters" class="bank-consultation-criteria">')
        self.assertContains(invalid, 'value="not-a-month"')
        self.assertContains(invalid, 'id="invoice-filter-month-error-1"')
        self.assertContains(invalid, 'data-field-error')
        self.assertEqual(invalid.context['active_filter_count'], 0)
        self.assertTrue(invalid.context['has_filters'])
        self.assertContains(invalid, 'Clear filters')
        self.assertFalse(empty_month.context['filter_form'].errors)
        self.assertIsNone(empty_month.context['filter_form'].cleaned_data['month'])
        self.assertEqual(empty_month.context['active_filter_count'], 0)
        self.assertEqual(empty_month.context['filter_form']['month'].value(), '  ')
        self.assertTrue(empty_month.context['has_filters'])
        self.assertContains(empty_month, 'Clear filters')
        rate_url = reverse('banking:exchange_rates')
        rates = self.client.get(rate_url)
        selected = self.client.get(rate_url, {'q': 'evidence', 'from_currency': 'USD', 'to_currency': 'BRL'})
        bad_dates = self.client.get(rate_url, {'from_currency': 'USD', 'date_from': '2026-10-03', 'date_to': '2026-10-01'})
        self.assertContains(rates, '<div id="rate-extra-filters" class="bank-consultation-criteria">')
        self.assertEqual(selected.context['active_filter_count'], 2)
        self.assertContains(selected, '2 active')
        for name in ('q', 'from_currency', 'to_currency', 'date_from', 'date_to'):
            self.assertContains(rates, f'name="{name}"')
        self.assertContains(bad_dates, '<div id="rate-extra-filters" class="bank-consultation-criteria">')
        self.assertContains(bad_dates, 'id="rate-filter-date_to-error-1"')
        self.assertEqual(bad_dates.context['active_filter_count'], 0)
        self.assertEqual(bad_dates.context['filter_form']['from_currency'].value(), 'USD')
        self.assertEqual(bad_dates.context['filter_form']['date_to'].value(), '2026-10-01')
        self.assertTrue(bad_dates.context['has_filters'])
        self.assertContains(bad_dates, 'Clear filters')
        self.assertFalse(BankMovement.objects.exists())

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
            response = self.client.get(reverse('banking:card_invoices', args=[self.card.pk]), {'q': 'Daily', 'bank': self.bank.pk, 'month': '2026-10', 'status': 'PARTIAL'})
        self.assertEqual(list(response.context['invoices']), [invoice])
        self.assertEqual(response.context['selected_card'], self.card)
        self.assertContains(response, 'data-live-results="invoice-results"')
        self.assertContains(response, 'October 2026')
        self.assertEqual(list(CardInvoice.objects.values()), original)
        with patch('banking.views.sync_user_ledger'):
            for key, value in [('card', '9' * 5000), ('bank', '0' + str(self.bank.pk)), ('card', '١')]:
                self.assertEqual(self.client.get(reverse('banking:invoices'), {key: value}).status_code, 404)
            invalid = self.client.get(reverse('banking:card_invoices', args=[self.card.pk]), {'month': 'not-a-month'})
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
