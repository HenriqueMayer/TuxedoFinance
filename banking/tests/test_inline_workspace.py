"""Owned bank panels and visible consultation controls preserve native routes.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CreditCard, DebitCard


class InlineBankWorkspaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('inline-bank-owner')
        self.other = get_user_model().objects.create_user('inline-bank-other')
        self.bank = Bank.objects.create(user=self.user, name='Owned bank', color='#315D50')
        self.second = Bank.objects.create(user=self.user, name='Second bank')
        self.foreign = Bank.objects.create(user=self.other, name='Private institution')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Daily',
            currency='BRL', opening_balance=1000, planning_enabled=True)
        BankAccount.objects.create(user=self.user, bank=self.second, name='Other',
            currency='BRL', opening_balance=500, planning_enabled=True)
        CreditCard.objects.create(user=self.user, account=self.account, name='Owned credit', closing_day=20, due_day=28)
        DebitCard.objects.create(user=self.user, account=self.account, name='Owned debit')
        # Legacy cross-owner references must not enter either tab counts or rows.
        CreditCard.objects.create(user=self.other, account=self.account, name='Private credit', closing_day=20, due_day=28)
        self.client.force_login(self.user)
        synchronizer = patch('banking.views.workspace.sync_user_ledger')
        synchronizer.start()
        self.addCleanup(synchronizer.stop)

    def test_overview_always_exposes_the_same_balance_breakdown(self):
        response = self.client.get(reverse('banking:list'))
        self.assertContains(response, 'Bank balances')
        self.assertContains(response, 'Cash pots to redeem')
        self.assertContains(response, 'Set aside')
        self.assertNotContains(response, 'Balance details')
        self.assertNotContains(response, 'bank-availability-breakdown')
        self.assertEqual(response.context['availability']['available_total'], Decimal('1500'))
        self.assertContains(response, 'id="banking-workspace"')
        self.assertNotContains(response, 'id="bank-workspace-panel"')
        self.assertContains(response, f'href="{reverse("banking:detail", args=[self.bank.pk])}"')

    def test_owned_detail_is_a_native_page_with_one_selected_inline_panel(self):
        response = self.client.get(reverse('banking:detail', args=[self.bank.pk]))
        self.assertEqual(response.context['selected_bank'], self.bank)
        banks = {bank.pk: bank for bank in response.context['banks']}
        self.assertEqual(set(banks), {self.bank.pk, self.second.pk})
        self.assertEqual(banks[self.bank.pk].account_count, 1)
        self.assertEqual(banks[self.bank.pk].card_count, 2)
        self.assertContains(response, 'id="bank-workspace-panel"', count=1)
        self.assertContains(response, 'id="planning-availability"', count=1)
        self.assertNotContains(response, 'id="bank-results"')
        self.assertNotContains(response, 'id="bank-workspace-choice"')
        self.assertNotContains(response, 'id="bank-switch-form"')
        self.assertNotContains(response, 'data-bank-switch-link')
        self.assertContains(response, 'hx-select="#banking-workspace"')
        self.assertContains(response, 'hx-push-url="true"')
        self.assertContains(response, 'aria-label="Minimize Owned bank"')
        self.assertContains(response, '<span>Minimize</span>')
        self.assertContains(response, f'id="account-row-{self.account.pk}"', count=1)
        self.assertNotContains(response, 'Private institution')
        self.assertNotContains(response, 'Private credit')
        self.assertFalse(BankMovement.objects.exists())

    def test_forty_banks_keep_the_open_surface_and_minimize_compact(self):
        Bank.objects.bulk_create([Bank(user=self.user, name=f'Bank {number:02d}') for number in range(1, 38)])
        selected = Bank.objects.create(pk=12001, user=self.user, name='Bank 40')
        overview = self.client.get(reverse('banking:list'))
        self.assertContains(overview, 'bank-overview-card', count=40)
        self.assertContains(overview, 'id="bank-12001"')
        response = self.client.get(reverse('banking:detail', args=[selected.pk]))
        self.assertNotContains(response, 'id="bank-results"')
        self.assertNotContains(response, 'bank-overview-card')
        self.assertContains(response, 'id="planning-availability"', count=1)
        self.assertContains(response, 'class="bank-workspace-windowbar"')
        self.assertContains(response, 'id="bank-detail-title-12001"')
        self.assertContains(response, 'data-bank-minimize="12001"')
        self.assertContains(response, '<span>Minimize</span>')
        self.assertNotContains(response, 'id="bank-workspace-choice"')
        self.assertNotContains(response, 'id="bank-switch-form"')
        self.assertNotContains(response, 'Bank 01')
        self.assertNotContains(response, 'Private institution')
        self.assertNotContains(response, 'iframe')

    def test_bank_routes_and_legacy_open_context_remain_owned(self):
        detail = reverse('banking:detail', args=[self.bank.pk])
        response = self.client.get(reverse('banking:list'), {'open': self.bank.pk, 'reserves': self.bank.pk})
        self.assertRedirects(response, detail + f'?reserves={self.bank.pk}', fetch_redirect_response=False)
        for identifier in [str(self.foreign.pk), '01', '١', '9' * 100]:
            with self.subTest(identifier=identifier):
                self.assertEqual(self.client.get(reverse('banking:list'), {'open': identifier}).status_code, 404)
        self.assertEqual(self.client.get(reverse('banking:detail', args=[self.foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('banking:list') + f'?open={self.bank.pk}').status_code, 405)

    def test_bank_index_keeps_the_same_name_order_when_a_panel_opens(self):
        # Aggregated card counts must not let GROUP BY reorder the tab index.
        self.bank.name = 'Zulu bank'
        self.bank.save(update_fields=['name'])
        self.second.name = 'Alpha bank'
        self.second.save(update_fields=['name'])
        expected = [self.second.pk, self.bank.pk]
        overview = self.client.get(reverse('banking:list'))
        opened = self.client.get(reverse('banking:detail', args=[self.bank.pk]))
        self.assertEqual([bank.pk for bank in overview.context['banks']], expected)
        self.assertEqual([bank.pk for bank in opened.context['banks']], expected)

    def test_panel_planning_post_refreshes_the_visible_consolidated_summary(self):
        response = self.client.post(reverse('banking:account_planning', args=[self.account.pk]),
            {'enabled': '0', 'return_to': 'detail', 'next': reverse('banking:detail', args=[self.bank.pk])},
            HTTP_HX_TARGET=f'bank-positions-{self.bank.pk}')
        self.assertContains(response, 'id="planning-availability"')
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.assertEqual(response.context['availability']['available_total'], Decimal('500'))
        self.assertEqual(self.account.current_balance(), Decimal('1000'))
        self.assertFalse(BankMovement.objects.exists())

    def test_invoice_and_fx_criteria_remain_complete_without_a_disclosure(self):
        for name, controls in [
            ('invoices', ('q', 'month', 'bank', 'status')),
            ('exchange_rates', ('q', 'from_currency', 'to_currency', 'date_from', 'date_to')),
        ]:
            with self.subTest(name=name):
                response = self.client.get(reverse('banking:' + name))
                self.assertContains(response, 'bank-consultation-criteria')
                self.assertNotContains(response, 'filter-disclosure')
                for control in controls:
                    self.assertContains(response, f'name="{control}"')
                self.assertContains(response, 'data-live-submit')

    def test_exchange_rate_direction_has_visible_copy_and_preserves_precision(self):
        response = self.client.get(reverse('banking:exchange_rate_create'))
        form = response.context['form']
        self.assertEqual(str(form['from_currency'].label), 'From currency (1 unit)')
        self.assertEqual(str(form['to_currency'].label), 'To currency')
        self.assertEqual(str(form['rate'].label), 'Value in the target currency')
        self.assertContains(response, 'Example: 1 USD = 5.12 BRL.')
        self.assertContains(response, 'step="0.00000001"')
        self.assertNotContains(response, 'data-money-input')
