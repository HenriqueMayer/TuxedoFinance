# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from banking.models import Bank, BankAccount, CardInvoice, CreditCard
from categories.models import Category
from ingestion.models import ImportBatch
from transactions.models import Transaction
from transactions.services import sync_user_ledger


class ContextualBankNavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('navigation-owner')
        self.other = get_user_model().objects.create_user('navigation-other')
        self.bank = Bank.objects.create(user=self.user, name='Local bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash', currency='BRL', opening_balance=1000, opening_date=date(2025, 1, 1))
        self.client.force_login(self.user)

    def test_account_editor_preserves_origin_and_bound_errors(self):
        url = reverse('banking:account_update', args=[self.account.pk])
        origin = reverse('banking:list') + '?q=Local#account-row-' + str(self.account.pk)
        response = self.client.get(url, {'next': origin})
        self.assertEqual(response.context['cancel_url'], origin)
        payload = {'next': origin, 'bank': self.bank.pk, 'name': 'Cash', 'currency': 'BRL', 'opening_balance': '1000', 'opening_date': '2025-01-01', 'reserved_amount': '-1'}
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cancel_url'], origin)
        self.assertContains(response, 'name="next"')
        self.account.refresh_from_db()
        self.assertEqual(self.account.reserved_amount, 0)
        payload['reserved_amount'] = '100'
        response = self.client.post(url, payload)
        self.assertRedirects(response, origin, fetch_redirect_response=False)
        self.account.refresh_from_db()
        self.assertEqual(self.account.reserved_amount, 100)

    def test_transfer_returns_to_owned_source_context_without_extra_cash(self):
        destination = BankAccount.objects.create(user=self.user, bank=self.bank, name='Savings', currency='BRL')
        origin = reverse('banking:list') + '?q=Local'
        response = self.client.post(reverse('banking:transfer_create'), {'next': origin, 'source_account': self.account.pk, 'destination_account': destination.pk, 'source_amount': '25', 'destination_amount': '25', 'date': date.today().isoformat()})
        self.assertRedirects(response, origin, fetch_redirect_response=False)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

    def test_external_return_is_rejected(self):
        response = self.client.post(reverse('banking:create'), {'name': 'Another bank', 'next': '//example.test/steal'})
        self.assertRedirects(response, reverse('banking:list'), fetch_redirect_response=False)

    def test_large_account_identifiers_keep_native_htmx_update_target(self):
        account = BankAccount.objects.create(pk=1700, user=self.user, bank=self.bank, name='Long lived account', currency='BRL', opening_balance=200, opening_date=date(2025, 1, 1))
        response = self.client.get(reverse('banking:detail', args=[account.bank_id]))
        self.assertContains(response, 'id="account-row-1700"')
        self.assertContains(response, '?account=1700')
        response = self.client.post(reverse('banking:account_planning', args=[account.pk]), {'enabled': '0', 'return_to': 'list'}, HTTP_HX_TARGET='account-row-1700')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="account-row-1700"')
        account.refresh_from_db()
        self.assertFalse(account.planning_enabled)

    def test_fragment_actions_keep_the_explicit_page_origin_after_planning_post(self):
        origin = reverse('banking:detail', args=[self.bank.pk]) + '?reserves=1#account-row-' + str(self.account.pk)
        for target in (f'bank-positions-{self.bank.pk}', f'account-row-{self.account.pk}'):
            response = self.client.post(reverse('banking:account_planning', args=[self.account.pk]),
                                        {'enabled': '1', 'next': origin}, HTTP_HX_TARGET=target)
            self.assertEqual(response.status_code, 200)
            from html.parser import HTMLParser

            class Links(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.urls = []

                def handle_starttag(self, tag, attrs):
                    if tag == 'a':
                        self.urls.append(dict(attrs).get('href', ''))

            links = Links()
            links.feed(response.content.decode())
            shortcuts = [url for url in links.urls if urlsplit(url).path == reverse('transactions:create')]
            self.assertTrue(shortcuts)
            for shortcut in shortcuts:
                self.assertEqual(parse_qs(urlsplit(shortcut).query)['next'], [origin])

    def make_invoice(self, name='Card'):
        card = CreditCard.objects.create(user=self.user, account=self.account, name=name, closing_day=31, due_day=30, manual_settlement_from=date(2025, 1, 1))
        category = Category.objects.create(user=self.user, name=name + ' expense', transaction_type='EXPENSE')
        Transaction.objects.create(user=self.user, title='Purchase', amount=100, transaction_type='EXPENSE', category=category, payment_channel='CREDIT_CARD', credit_card=card, date=date.today().replace(day=1))
        sync_user_ledger(self.user)
        return CardInvoice.objects.get(card=card)

    def test_card_invoice_filter_is_owned_and_scoped(self):
        invoice = self.make_invoice()
        other_invoice = self.make_invoice('Other card')
        response = self.client.get(reverse('banking:invoices'), {'card': invoice.card_id})
        self.assertEqual(list(response.context['invoices']), [invoice])
        self.assertEqual(response.context['selected_card'], invoice.card)
        # Other owned cards remain selectable, but their invoice rows must not
        # escape the explicit card filter.
        self.assertNotContains(response, f'id="invoice-{other_invoice.pk}"')
        foreign_bank = Bank.objects.create(user=self.other, name='Foreign')
        foreign_account = BankAccount.objects.create(user=self.other, bank=foreign_bank, name='Foreign', currency='BRL')
        foreign_card = CreditCard.objects.create(user=self.other, account=foreign_account, name='Foreign', closing_day=31, due_day=30)
        for identifier in [foreign_card.pk, 'invalid', '9' * 5000, '٩']:
            response = self.client.get(reverse('banking:invoices'), {'card': identifier})
            self.assertEqual(response.status_code, 404)

    def test_invoice_payment_keeps_error_origin_and_shows_result_on_invoice(self):
        invoice = self.make_invoice()
        url = reverse('banking:invoice_detail', args=[invoice.pk])
        origin = reverse('dashboard:index') + '?month=2026-09'
        response = self.client.post(url, {'next': origin, 'confirmation_key': str(uuid4()), 'account': self.account.pk, 'amount': '101', 'date': date.today().isoformat()})
        self.assertContains(response, 'Payments cannot exceed')
        self.assertEqual(response.context['return_url'], origin)
        self.assertContains(response, 'Record a payment already made at your bank.')
        self.assertLess(response.content.find(b'id="invoice-payment"'), response.content.find(b'Invoice sources'))
        self.assertEqual(invoice.payments.count(), 0)
        response = self.client.post(url, {'next': origin, 'confirmation_key': str(uuid4()), 'account': self.account.pk, 'amount': '25', 'date': date.today().isoformat()})
        self.assertEqual(response.status_code, 302)
        destination = urlsplit(response['Location'])
        self.assertEqual(destination.path, url)
        self.assertEqual(destination.fragment, 'invoice-summary')
        self.assertEqual(parse_qs(destination.query)['next'], [origin])
        invoice.refresh_from_db()
        self.assertEqual(invoice.remaining_amount, Decimal('75'))

    @override_settings(REVIEWED_FEATURES={'imports'})
    def test_dashboard_pending_imports_are_owned_and_never_count_as_cash(self):
        batch = ImportBatch.objects.create(user=self.user, account=self.account, file_name='owner.csv', file_hash='a' * 64, file_format='CSV', raw_text='date,amount', status='STAGED')
        ImportBatch.objects.create(user=self.other, account=self.account, file_name='foreign.csv', file_hash='b' * 64, file_format='CSV', raw_text='date,amount', status='READY')
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['pending_import_count'], 1)
        self.assertEqual(response.context['pending_imports'], [batch])
        self.assertContains(response, 'owner.csv')
        self.assertNotContains(response, 'foreign.csv')
        self.assertEqual(response.context['current_balance'], 1000)
        self.assertContains(response, reverse('ingestion:mapping', args=[batch.pk]))

    @override_settings(REVIEWED_FEATURES=set())
    def test_paused_imports_do_not_offer_pending_actions_or_change_current_cash(self):
        ImportBatch.objects.create(user=self.user, account=self.account, file_name='owner.csv', file_hash='a' * 64,
                                  file_format='CSV', raw_text='date,amount', status='STAGED')
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['pending_import_count'], 0)
        self.assertEqual(response.context['pending_imports'], [])
        self.assertEqual(response.context['current_balance'], 1000)
