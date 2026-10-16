# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CreditCard


class InvoiceCardNavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('invoice-card-owner')
        self.other = get_user_model().objects.create_user('invoice-card-other')
        self.bank = Bank.objects.create(user=self.user, name='Daily bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Current', currency='BRL')
        self.card = CreditCard.objects.create(pk=1700, user=self.user, account=self.account, name='Daily card', closing_day=1, due_day=10)
        self.empty = CreditCard.objects.create(user=self.user, account=self.account, name='Empty card', closing_day=1, due_day=10)
        self.invoice = CardInvoice.objects.create(user=self.user, card=self.card, reference_month=date(2026, 10, 1), due_date=date(2026, 11, 10), amount=120, status='PARTIAL', manual_settlement=True)
        self.client.force_login(self.user)
        synchronizer = patch('banking.views.sync_user_ledger')
        synchronizer.start()
        self.addCleanup(synchronizer.stop)

    def test_overview_lists_owned_cards_even_without_invoices_and_counts_only_owned_evidence(self):
        private = CreditCard.objects.create(user=self.other, account=self.account, name='Private card', closing_day=1, due_day=10)
        CardInvoice.objects.create(user=self.other, card=self.card, reference_month=date(2026, 9, 1), due_date=date(2026, 10, 10), amount=999)
        before = list(CardInvoice.objects.values())
        response = self.client.get(reverse('banking:invoices'))
        self.assertEqual({card.pk: card.invoice_count for card in response.context['cards']}, {self.card.pk: 1, self.empty.pk: 0})
        self.assertContains(response, 'id="invoice-card-1700"')
        self.assertContains(response, 'href="' + reverse('banking:card_invoices', args=[1700]) + '"')
        self.assertNotContains(response, f'id="invoice-card-{private.pk}"')
        self.assertNotContains(response, 'invoice-filter-card')
        self.assertEqual(list(CardInvoice.objects.values()), before)
        self.assertFalse(BankMovement.objects.exists())

    def test_live_compatible_get_filters_constrain_card_blocks_and_retain_errors(self):
        response = self.client.get(reverse('banking:invoices'), {'bank': self.bank.pk, 'q': 'Daily', 'month': '2026-10', 'status': 'PARTIAL'})
        self.assertEqual(list(response.context['cards']), [self.card])
        self.assertEqual(response.context['cards'][0].invoice_count, 1)
        self.assertEqual(response.context['active_filter_count'], 3)
        self.assertContains(response, 'month=2026-10')
        self.assertContains(response, 'status=PARTIAL')
        empty = self.client.get(reverse('banking:invoices'), {'q': 'Empty'})
        self.assertEqual(list(empty.context['cards']), [self.empty])
        invalid = self.client.get(reverse('banking:invoices'), {'month': 'bad'})
        self.assertEqual(list(invalid.context['cards']), [])
        self.assertContains(invalid, 'invoice-filter-month-error-1')

    def test_card_page_and_clear_remain_scoped_without_losing_return_context(self):
        url = reverse('banking:card_invoices', args=[self.card.pk])
        other_invoice = CardInvoice.objects.create(user=self.user, card=self.empty, reference_month=date(2026, 10, 1), due_date=date(2026, 11, 10), amount=300)
        origin = reverse('banking:detail', args=[self.bank.pk])
        response = self.client.get(url, {'month': '2026-10', 'next': origin})
        self.assertEqual(list(response.context['invoices']), [self.invoice])
        self.assertEqual(response.context['selected_card'], self.card)
        self.assertTrue(next(section for section in response.context['APP_SECTIONS']
                             if section['url'] == reverse('banking:invoices'))['active'])
        self.assertNotContains(response, f'id="invoice-{other_invoice.pk}"')
        clear = urlsplit(response.context['invoice_clear_url'])
        self.assertEqual(clear.path, url)
        self.assertEqual(parse_qs(clear.query), {'next': [origin]})
        private = CreditCard.objects.create(user=self.other, account=self.account, name='Private', closing_day=1, due_day=10)
        self.assertEqual(self.client.get(reverse('banking:card_invoices', args=[private.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('banking:card_invoices', args=[0])).status_code, 404)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_legacy_card_filter_redirect_keeps_criteria_and_rejects_invalid_identifiers(self):
        response = self.client.get(reverse('banking:invoices'), {'card': '1700', 'month': '2026-10', 'status': 'PARTIAL', 'page': '2'})
        self.assertEqual(response.status_code, 302)
        target = urlsplit(response.url)
        self.assertEqual(target.path, reverse('banking:card_invoices', args=[1700]))
        self.assertEqual(parse_qs(target.query), {'month': ['2026-10'], 'status': ['PARTIAL'], 'page': ['2']})
        for identifier in ['01700', '١٧٠٠', '9' * 5000]:
            self.assertEqual(self.client.get(reverse('banking:invoices'), {'card': identifier}).status_code, 404)

    def test_cards_and_card_history_have_independent_complete_pagination(self):
        for number in range(31):
            CreditCard.objects.create(user=self.user, account=self.account, name=f'Extra {number:02}', closing_day=1, due_day=10)
            year, month = 2000 + number // 12, 1 + number % 12
            CardInvoice.objects.create(user=self.user, card=self.card, reference_month=date(year, month, 1), due_date=date(year, month, 10), amount=number)
        overview = self.client.get(reverse('banking:invoices'), {'page': '2'})
        self.assertEqual(overview.context['paginator'].count, 33)
        self.assertEqual(len(overview.context['cards']), 3)
        history = self.client.get(reverse('banking:card_invoices', args=[self.card.pk]), {'page': '2'})
        self.assertEqual(history.context['paginator'].count, 32)
        self.assertEqual(len(history.context['invoices']), 2)
