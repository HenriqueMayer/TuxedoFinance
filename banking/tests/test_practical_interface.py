"""Nested invoice actions preserve an explicit, authorized consultation origin.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from banking.models import Bank, BankAccount, CardInvoice, CreditCard, DebitCard, ExchangeRate, InvoicePayment
from banking.services import account_balance
from banking.settlements import save_invoice_payment
from categories.models import Category
from core.navigation import with_return_url
from transactions.models import Transaction


class InvoiceActionContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('practical-bank-owner')
        self.other = get_user_model().objects.create_user('practical-bank-other')
        self.bank = Bank.objects.create(user=self.user, name='Owned institution')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank,
            name='Checking', currency='BRL', opening_balance=1000)
        self.card = CreditCard.objects.create(user=self.user, account=self.account,
            name='Daily card', closing_day=31, due_day=30, manual_settlement_from=date.today())
        self.invoice = CardInvoice.objects.create(user=self.user, card=self.card,
            reference_month=date.today().replace(day=1), due_date=date.today() + timedelta(days=30),
            amount=100, manual_settlement=True)
        self.payment = save_invoice_payment(InvoicePayment(user=self.user, invoice=self.invoice,
            account=self.account, amount=Decimal('20'), date=date.today()))
        category = Category.objects.create(user=self.user, name='Practical invoice source', transaction_type='EXPENSE')
        self.purchase = Transaction.objects.create(user=self.user, title='Source purchase', amount=100,
            transaction_type='EXPENSE', category=category, payment_channel='CREDIT_CARD',
            credit_card=self.card, date=date.today().replace(day=1))
        self.invoice_url = reverse('banking:invoice_detail', args=[self.invoice.pk])
        self.origin = reverse('banking:card_invoices', args=[self.card.pk]) + '?q=Daily&status=PARTIAL&month=' + date.today().strftime('%Y-%m')
        self.context_url = with_return_url(self.invoice_url, self.origin)
        self.payment_origin = self.context_url + '#invoice-payments'
        self.edit_url = reverse('banking:invoice_payment_edit', args=[self.payment.pk])
        self.delete_url = reverse('banking:invoice_payment_delete', args=[self.payment.pk])
        self.client.force_login(self.user)
        synchronizer = patch('banking.views.invoices.sync_user_ledger')
        synchronizer.start()
        self.addCleanup(synchronizer.stop)

    def assert_action_origins(self, response):
        for target in [self.edit_url, self.delete_url]:
            expected = with_return_url(target, self.context_url, fragment='invoice-payments')
            self.assertContains(response, f'href="{escape(expected)}"')
        source = with_return_url(reverse('transactions:update', args=[self.purchase.pk]),
            self.context_url, fragment='invoice-summary')
        self.assertContains(response, f'href="{escape(source)}"')

    def test_invoice_actions_keep_the_filtered_outer_origin_after_get_and_invalid_payment(self):
        self.assert_action_origins(self.client.get(self.context_url))
        response = self.client.post(self.invoice_url, {'next': self.origin, 'amount': '-1'})
        self.assertContains(response, 'aria-invalid="true"')
        # A bound POST need not repeat next in its query; submitted context is
        # the source of truth for every nested action after validation errors.
        self.assert_action_origins(response)
        self.assertEqual(InvoicePayment.objects.count(), 1)

    def test_payment_edit_preserves_context_on_errors_cancel_and_success(self):
        response = self.client.get(self.edit_url, {'next': self.payment_origin})
        self.assertEqual(response.context['cancel_url'], self.payment_origin)
        values = {'next': self.payment_origin, 'account': self.account.pk, 'amount': '-1',
            'date': date.today().isoformat(), 'notes': 'Owned edit',
            'confirmation_key': str(self.payment.confirmation_key)}
        invalid = self.client.post(self.edit_url, values)
        self.assertContains(invalid, 'aria-invalid="true"')
        self.assertEqual(invalid.context['return_url'], self.payment_origin)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, 20)
        values['amount'] = '25.10'
        response = self.client.post(self.edit_url, values)
        self.assertRedirects(response, self.payment_origin, fetch_redirect_response=False)
        self.assertEqual(account_balance(self.account), Decimal('974.90'))

    def test_payment_delete_cancel_and_submit_keep_context_and_reverse_only_its_movement(self):
        response = self.client.get(self.delete_url, {'next': self.payment_origin})
        self.assertContains(response, f'href="{escape(self.payment_origin)}"')
        self.assertContains(response, f'name="next" value="{escape(self.payment_origin)}"')
        self.assertTrue(InvoicePayment.objects.filter(pk=self.payment.pk).exists())
        response = self.client.post(self.delete_url, {'next': self.payment_origin})
        self.assertRedirects(response, self.payment_origin, fetch_redirect_response=False)
        self.assertFalse(InvoicePayment.objects.exists())
        self.assertEqual(account_balance(self.account), 1000)

    def test_nested_actions_reject_external_returns_and_other_users_records(self):
        for path in [self.edit_url, self.delete_url]:
            with self.subTest(path=path):
                response = self.client.get(path, {'next': '//outside.example/invoice'})
                destination = response.context.get('cancel_url', response.context.get('return_url'))
                self.assertEqual(destination, self.invoice_url)
        response = self.client.get(self.invoice_url, {'next': 'https://outside.example/'})
        self.assertEqual(response.context['invoice_context_url'], self.invoice_url)
        self.assertEqual(parse_qs(urlsplit(response.context['invoice_context_url']).query), {})
        self.client.force_login(self.other)
        for path in [self.invoice_url, self.edit_url, self.delete_url]:
            self.assertEqual(self.client.get(path).status_code, 404)
            self.assertEqual(self.client.post(path, {'next': self.payment_origin}).status_code, 404)
        self.assertEqual(InvoicePayment.objects.count(), 1)


class RecordDeletionContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('bank-delete-context')
        self.other = get_user_model().objects.create_user('bank-delete-stranger')
        self.bank = Bank.objects.create(user=self.user, name='Owned institution')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank,
            name='Checking', currency='BRL')
        self.card = DebitCard.objects.create(user=self.user, account=self.account, name='Owned debit')
        self.origin = reverse('banking:detail', args=[self.bank.pk]) + '#account-row-' + str(self.account.pk)
        self.client.force_login(self.user)

    def test_cancel_and_protected_deletion_keep_the_owned_bank_origin(self):
        for route, record in [('delete', self.bank), ('account_delete', self.account)]:
            with self.subTest(route=route):
                path = reverse('banking:' + route, args=[record.pk])
                response = self.client.get(path, {'next': self.origin})
                self.assertEqual(response.context['cancel_url'], self.origin)
                self.assertEqual(response.context['return_url'], self.origin)
                self.assertContains(response, f'name="next" value="{escape(self.origin)}"')
                response = self.client.post(path, {'next': self.origin})
                self.assertRedirects(response, self.origin, fetch_redirect_response=False)
                self.assertTrue(type(record).objects.filter(pk=record.pk).exists())

    def test_successful_card_removal_returns_to_the_surviving_bank(self):
        path = reverse('banking:debit_card_delete', args=[self.card.pk])
        response = self.client.post(path, {'next': self.origin})
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        self.assertFalse(DebitCard.objects.filter(pk=self.card.pk).exists())

    def test_removed_bank_does_not_return_to_its_deleted_workspace(self):
        empty = Bank.objects.create(user=self.user, name='Empty institution')
        path = reverse('banking:delete', args=[empty.pk])
        origin = reverse('banking:detail', args=[empty.pk])
        self.assertEqual(self.client.get(path, {'next': origin}).context['cancel_url'], origin)
        response = self.client.post(path, {'next': origin})
        self.assertRedirects(response, reverse('banking:list'), fetch_redirect_response=False)
        self.assertFalse(Bank.objects.filter(pk=empty.pk).exists())

    def test_delete_fallbacks_and_ownership_remain_server_validated(self):
        path = reverse('banking:debit_card_delete', args=[self.card.pk])
        response = self.client.get(path, {'next': '//outside.example/'})
        self.assertEqual(response.context['cancel_url'], reverse('banking:list'))
        rate = ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
            rate='5.12345678', effective_date=date.today())
        rate_path = reverse('banking:exchange_rate_delete', args=[rate.pk])
        response = self.client.get(rate_path, {'next': 'https://outside.example/'})
        self.assertEqual(response.context['cancel_url'], reverse('banking:exchange_rates'))
        self.client.force_login(self.other)
        for owned in [path, rate_path]:
            self.assertEqual(self.client.get(owned).status_code, 404)
            self.assertEqual(self.client.post(owned, {'next': self.origin}).status_code, 404)
