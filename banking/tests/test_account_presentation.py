"""Account hierarchy and shared navigation retain existing financial state.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from assistant.context import ScopeError, normalize_location
from banking.models import Bank, BankAccount, BankMovement, CreditCard, LoyaltyProgram


class AccountPresentationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('account-presentation')
        self.bank = Bank.objects.create(user=self.user, name='Everyday bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank,
            name='Everyday account', currency='BRL', opening_balance='1000.25',
            opening_date=date(2020, 1, 1), reserved_amount='100')
        self.card = CreditCard.objects.create(user=self.user, account=self.account,
            name='Everyday card', closing_day=24, due_day=1, color='#263843')
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Travel rewards')
        self.client.force_login(self.user)

    def test_four_explicit_sections_and_divided_accounts_preserve_money_and_artwork(self):
        response = self.client.get(reverse('banking:list'))
        self.assertContains(response, 'Your banks')
        self.assertContains(response, 'banking-sections')
        self.assertEqual([item['label'] for item in response.context['APP_SECTIONS']],
            ['Accounts', 'Invoices', 'Loyalty', 'Exchange rates'])
        self.assertContains(response, reverse('banking:programs'))
        self.assertContains(response, 'class="payment-choice-art institution-miniature" data-choice-kind="account" aria-hidden="true"', count=1)

        response = self.client.get(reverse('banking:detail', args=[self.bank.pk]))
        self.assertContains(response, 'class="bank-account-list"')
        self.assertContains(response, 'class="account-secondary"')
        self.assertContains(response, 'institution-miniature', count=1)
        self.assertNotContains(response, 'class="bank-marker"')
        self.assertContains(response, '--card-start:#263843')
        self.assertContains(response, 'closes 24, due 1')
        self.assertEqual(response.context['availability']['bank_total'], Decimal('1000.25'))
        self.assertEqual(response.context['availability']['available_total'], Decimal('900.25'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.opening_balance, Decimal('1000.25'))
        self.assertEqual(self.account.reserved_amount, Decimal('100'))
        self.assertFalse(BankMovement.objects.exists())

    def test_nested_card_and_loyalty_forms_keep_their_section(self):
        cases = [('credit_card_update', self.card.pk, 'Accounts'),
                 ('program_update', self.program.pk, 'Loyalty')]
        for route, pk, label in cases:
            with self.subTest(route=route):
                response = self.client.get(reverse('banking:' + route, args=[pk]))
                self.assertEqual([item['label'] for item in response.context['APP_SECTIONS']
                                  if item['active']], [label])

    def test_assistant_accepts_owned_loyalty_pages_and_validates_history_owner(self):
        overview = reverse('banking:programs') + '?q=Travel'
        history = reverse('banking:program_entries', args=[self.program.pk]) + '?q=Award&page=2'
        self.assertEqual(normalize_location(self.user, overview)['location'], overview)
        self.assertEqual(normalize_location(self.user, history)['location'],
            reverse('banking:program_entries', args=[self.program.pk]) + '?page=2&q=Award')
        other = get_user_model().objects.create_user('other-account-presentation')
        with self.assertRaises(ScopeError):
            normalize_location(other, history)
