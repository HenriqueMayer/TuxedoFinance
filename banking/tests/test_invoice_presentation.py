# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Statement presentation retains owned evidence and complete native forms."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CreditCard, InvoicePayment
from core.navigation import with_return_url


class InvoicePresentationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('invoice-presentation-owner')
        self.bank = Bank.objects.create(user=self.user, name='Statement institution')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank,
            name='Everyday account', currency='BRL')
        self.card = CreditCard.objects.create(user=self.user, account=self.account,
            name='Personal purple card', color='#72419C', closing_day=31, due_day=28)
        self.invoice = CardInvoice.objects.create(user=self.user, card=self.card,
            reference_month=date(2026, 10, 1), due_date=date(2026, 11, 28),
            amount=Decimal('84.90'), manual_settlement=True)
        self.client.force_login(self.user)
        sync = patch('banking.views.invoices.sync_user_ledger')
        sync.start()
        self.addCleanup(sync.stop)

    def test_card_history_keeps_identity_native_filters_and_individual_invoice_values(self):
        path = reverse('banking:card_invoices', args=[self.card.pk])
        response = self.client.get(path, {'month': '2026-10'})
        self.assertContains(response, 'class="invoice-identity"')
        self.assertContains(response, '--card-start:#72419C')
        self.assertContains(response, 'Statement institution')
        self.assertContains(response, 'Everyday account')
        self.assertContains(response, 'class="invoice-history-row"')
        self.assertContains(response, 'class="invoice-history-amount"')
        self.assertRegex(response.content.decode(), r'BRL 84[,.]90')
        self.assertRegex(response.content.decode(), r'Remaining: BRL 84[,.]90')
        self.assertContains(response, f'action="{path}" method="get"')
        self.assertEqual(list(response.context['invoices']), [self.invoice])
        self.assertFalse(BankMovement.objects.exists())

    def test_detail_identity_and_summary_keep_native_payment_and_source_anchors(self):
        path = reverse('banking:invoice_detail', args=[self.invoice.pk])
        response = self.client.get(path)
        self.assertContains(response, 'class="invoice-identity"')
        self.assertContains(response, 'class="invoice-summary-grid"')
        self.assertContains(response, 'class="invoice-summary-total"')
        for anchor in ['invoice-summary', 'invoice-payment', 'invoice-payments', 'invoice-credits']:
            self.assertContains(response, f'id="{anchor}"')
        self.assertContains(response, 'autocomplete="off" method="post" hx-boost="false" novalidate')
        self.assertContains(response, 'Invoice sources')
        self.assertFalse(InvoicePayment.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_bound_payment_errors_remain_visible_without_replacing_financial_evidence(self):
        path = reverse('banking:invoice_detail', args=[self.invoice.pk])
        origin = reverse('banking:card_invoices', args=[self.card.pk]) + '?month=2026-10'
        before = list(CardInvoice.objects.values())
        response = self.client.post(path, {'amount': '-1', 'next': origin})
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="-1"')
        self.assertContains(response, 'class="invoice-summary-total"')
        self.assertEqual(response.context['invoice_context_url'], with_return_url(path, origin))
        self.assertEqual(list(CardInvoice.objects.values()), before)
        self.assertFalse(InvoicePayment.objects.exists())
        self.assertFalse(BankMovement.objects.exists())
