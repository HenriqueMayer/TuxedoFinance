# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Home shortcuts identify their live scope and keep explicit editor origins."""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, CardInvoice, CreditCard
from core.navigation import with_return_url


class HomeShortcutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('home-shortcut-owner')
        self.bank = Bank.objects.create(user=self.user, name='Shortcut bank')
        self.account = BankAccount.objects.create(pk=1700, user=self.user, bank=self.bank,
            name='Shortcut account', currency='BRL', opening_date=date(2020, 1, 1),
            opening_balance='500.00')
        self.client.force_login(self.user)

    def test_outstanding_preview_includes_overdue_and_partial_and_hub_opens_all(self):
        invoices = []
        for status in CardInvoice.Status:
            card = CreditCard.objects.create(user=self.user, account=self.account,
                name=f'{status.label} card', closing_day=31, due_day=28)
            invoices.append(CardInvoice.objects.create(user=self.user, card=card,
                reference_month=date(2025, 6, 1), due_date=date(2025, 6, 28),
                amount='25.00', status=status, manual_settlement=True))
        # Isolate the rendered link contract from ledger rebuilding: these are
        # explicit pending/paid fixtures, rather than generated purchase history.
        with patch('dashboard.views.sync_user_ledger'):
            response = self.client.get(reverse('dashboard:index'), {'month': '2026-09'})
        self.assertContains(response, 'Outstanding invoices')
        self.assertNotContains(response, 'Upcoming invoices')
        self.assertContains(response,
            'Unpaid and partially paid card invoices, independent of the selected month.')
        self.assertContains(response,
            'href="/banking/invoices/" class="quiet-action shrink-0">All invoices</a>')
        self.assertEqual({invoice.pk for invoice in response.context['open_invoices_preview']},
            {invoice.pk for invoice in invoices if invoice.status != CardInvoice.Status.PAID})

    def test_new_transaction_returns_to_selected_month_and_account_ids_are_native(self):
        origin = reverse('dashboard:index') + '?month=2026-09'
        response = self.client.get(origin)
        create_url = with_return_url(reverse('transactions:create'), origin)
        self.assertContains(response, f'href="{create_url}" class="action-primary"')
        account_target = reverse('banking:detail', args=[self.bank.pk]) + '#account-row-1700'
        self.assertContains(response, f'href="{account_target}" hx-swap="innerHTML show:none"')
        self.assertContains(response, 'href="?month=2026-08"')
        self.assertContains(response, 'href="?month=2026-10"')
        editor = self.client.get(create_url)
        self.assertEqual(editor.status_code, 200)
        self.assertEqual(editor.context['return_url'], origin)
        target = self.client.get(account_target.split('#')[0])
        self.assertEqual(target.status_code, 200)
        self.assertContains(target, 'id="account-row-1700"')
