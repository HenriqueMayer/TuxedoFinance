# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owned native credit forms preserve invoice context and explicit returns."""

from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assistant.context import normalize_location, ScopeError
from banking.credits import save_invoice_credit
from banking.forms import InvoiceCreditForm
from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CardInvoiceCredit, CreditCard
from categories.models import Category
from transactions.models import Transaction
from transactions.services import sync_user_ledger


class InvoiceCreditViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('invoice-credit-owner')
        self.other = get_user_model().objects.create_user('invoice-credit-other')
        self.bank = Bank.objects.create(user=self.user, name='Local')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank,
            name='Cash', currency='BRL', opening_balance=1000)
        self.card = CreditCard.objects.create(user=self.user, account=self.account,
            name='Prime', closing_day=31, due_day=30,
            manual_settlement_from=timezone.localdate().replace(day=1))
        self.category = Category.objects.create(user=self.user, name='Transport', transaction_type='EXPENSE')
        self.income = Category.objects.create(user=self.user, name='Salary', transaction_type='INCOME')
        self.foreign_category = Category.objects.create(user=self.other, name='Private', transaction_type='EXPENSE')
        Transaction.objects.create(user=self.user, title='Purchase', amount=100, transaction_type='EXPENSE',
            category=self.category, payment_channel='CREDIT_CARD', credit_card=self.card,
            date=timezone.localdate().replace(day=1))
        sync_user_ledger(self.user)
        self.invoice = CardInvoice.objects.get(card=self.card)
        self.url = reverse('banking:invoice_credit_create', args=[self.invoice.pk])
        self.origin = reverse('banking:invoice_detail', args=[self.invoice.pk]) + '?next=%2Fbanking%2Finvoices%2F%3Fq%3DPrime#invoice-credits'
        self.client.force_login(self.user)

    def payload(self, **overrides):
        return {'title': 'Uber refund', 'amount': '8.95', 'date': timezone.localdate().isoformat(),
            'category': str(self.category.pk), 'notes': 'Granted by the issuer',
            'idempotency_key': str(uuid4()), 'next': self.origin, **overrides}

    def make_credit(self):
        return save_invoice_credit(CardInvoiceCredit(user=self.user, card=self.card,
            category=self.category, reference_month=self.invoice.reference_month,
            title='Uber refund', amount=Decimal('8.95'), date=timezone.localdate()), user=self.user)

    def test_native_create_renders_shared_fields_and_rejects_invalid_amount(self):
        response = self.client.get(self.url, {'next': self.origin})
        self.assertContains(response, 'novalidate')
        self.assertContains(response, 'autocomplete="off"')
        self.assertContains(response, 'data-search-select')
        self.assertContains(response, 'data-date-picker="true"')
        self.assertContains(response, 'It reduces this invoice without creating income or a bank payment.')
        self.assertEqual(response.context['return_url'], self.origin)
        payload = self.payload(amount='-8.95')
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn('amount', response.context['form'].errors)
        self.assertEqual(response.context['form']['title'].value(), 'Uber refund')
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertFalse(CardInvoiceCredit.objects.exists())

    def test_create_uses_invoice_context_and_repeat_post_is_idempotent(self):
        payload = self.payload(card='9999', reference_month='2020-01-01', user=self.other.pk)
        response = self.client.post(self.url, payload)
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        credit = CardInvoiceCredit.objects.get()
        self.assertEqual((credit.card_id, credit.user_id, credit.reference_month),
            (self.card.pk, self.user.pk, self.invoice.reference_month))
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        self.assertEqual(CardInvoiceCredit.objects.count(), 1)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount, Decimal('91.05'))
        self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(Transaction.objects.count(), 1)

    def test_owned_expense_category_choices_and_forged_selection(self):
        form = InvoiceCreditForm(user=self.user, card=self.card, reference_month=self.invoice.reference_month)
        choices = form.fields['category'].queryset
        self.assertIn(self.category, choices)
        self.assertFalse(choices.exclude(user=self.user).exists())
        self.assertFalse(choices.filter(transaction_type='INCOME').exists())
        for category in (self.income, self.foreign_category):
            response = self.client.post(self.url, self.payload(category=str(category.pk)))
            self.assertEqual(response.status_code, 200)
            self.assertIn('category', response.context['form'].errors)
        self.assertFalse(CardInvoiceCredit.objects.exists())

    def test_detail_lists_credit_separately_and_keeps_nested_return(self):
        credit = self.make_credit()
        response = self.client.get(reverse('banking:invoice_detail', args=[self.invoice.pk]),
            {'next': '/banking/invoices/?q=Prime'})
        self.assertContains(response, f'id="invoice-credit-{credit.pk}"')
        self.assertContains(response, 'Purchases and charges')
        self.assertContains(response, 'Refunds and adjustments reduce this invoice.')
        self.assertEqual(list(response.context['credits']), [credit])
        self.assertEqual(response.context['sources'][0][1], Decimal('100'))
        self.assertEqual(response.context['invoice'].gross_amount, Decimal('100'))
        self.assertEqual(response.context['invoice'].credits_amount, Decimal('8.95'))

    def test_native_edit_delete_and_cancel_preserve_origin(self):
        credit = self.make_credit()
        edit = reverse('banking:invoice_credit_edit', args=[credit.pk])
        delete = reverse('banking:invoice_credit_delete', args=[credit.pk])
        response = self.client.get(edit, {'next': self.origin})
        self.assertEqual(response.context['form']['amount'].value(), Decimal('8.95'))
        self.assertEqual(response.context['return_url'], self.origin)
        response = self.client.post(edit, self.payload(amount='9.25', idempotency_key=str(credit.idempotency_key)))
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        credit.refresh_from_db()
        self.assertEqual(credit.amount, Decimal('9.25'))
        response = self.client.get(delete, {'next': self.origin})
        self.assertContains(response, 'Removing this credit recalculates the invoice.')
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertTrue(CardInvoiceCredit.objects.filter(pk=credit.pk).exists())
        response = self.client.post(delete, {'next': self.origin})
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        self.assertFalse(CardInvoiceCredit.objects.exists())
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount, Decimal('100'))

    def test_foreign_and_anonymous_credit_routes_do_not_reveal_data(self):
        credit = self.make_credit()
        routes = [self.url, reverse('banking:invoice_credit_edit', args=[credit.pk]),
            reverse('banking:invoice_credit_delete', args=[credit.pk])]
        self.client.force_login(self.other)
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.client.logout()
        for url in routes:
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_external_return_is_rejected_and_excess_credit_is_explained(self):
        response = self.client.post(self.url, self.payload(amount='120', next='https://example.test/'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('banking:invoice_detail', args=[self.invoice.pk]) + '#invoice-credits')
        response = self.client.get(reverse('banking:invoice_detail', args=[self.invoice.pk]))
        self.assertContains(response, 'Unused invoice credit')
        self.assertContains(response, 'It is not transferred to another month.')
        self.assertEqual(response.context['invoice'].credit_balance, Decimal('20'))

    def test_removing_last_credit_only_source_returns_to_the_card(self):
        credit = self.make_credit()
        self.user.transactions.all().delete()
        sync_user_ledger(self.user)
        self.invoice.refresh_from_db()
        url = reverse('banking:invoice_credit_delete', args=[credit.pk])
        response = self.client.post(url, {'next': self.origin})
        self.assertRedirects(response, reverse('banking:card_invoices', args=[self.card.pk]),
            fetch_redirect_response=False)
        self.assertFalse(CardInvoice.objects.filter(pk=self.invoice.pk).exists())

    def test_assistant_page_context_accepts_only_owned_credit_routes(self):
        credit = self.make_credit()
        for url in (self.url, reverse('banking:invoice_credit_edit', args=[credit.pk]),
                reverse('banking:invoice_credit_delete', args=[credit.pk])):
            with self.subTest(url=url):
                self.assertEqual(normalize_location(self.user, url)['location'], url)
                with self.assertRaises(ScopeError):
                    normalize_location(self.other, url)
