# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from html import unescape
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, LoyaltyEntry, LoyaltyProgram, RewardRedemption


class RedemptionReturnContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('redemption-form-origin')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Receiving bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Rewards', currency='BRL')
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Rewards', unit_name='Points')
        LoyaltyEntry.objects.create(user=self.user, program=self.program, direction='CREDIT', kind='ADJUSTMENT', amount=1000, date=date(2025, 1, 1))
        self.url = reverse('banking:redemption_create')
        self.payload = {'program': self.program.pk, 'points': '100', 'target_account': self.account.pk,
                        'target_amount': '25', 'iof_amount': '0', 'date': '2025-01-03'}

    def hidden_origin(self, response):
        match = re.search(r'<input type="hidden" name="next" value="([^"]*)">', response.content.decode())
        self.assertIsNotNone(match, 'The actual entry form must submit its origin.')
        return unescape(match.group(1))

    def test_default_form_posts_empty_origin_and_returns_to_receiving_history(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['cancel_url'], reverse('banking:list'))
        origin = self.hidden_origin(response)
        self.assertEqual(origin, '')
        # Carry the rendered value through a recoverable validation response.
        response = self.client.post(self.url, self.payload | {'next': origin, 'points': '1001'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('points', response.context['form'].errors)
        self.assertEqual(RewardRedemption.objects.count(), 0)
        origin = self.hidden_origin(response)
        self.assertEqual(origin, '')
        self.assertEqual(response.context['cancel_url'], reverse('banking:list'))
        response = self.client.post(self.url, self.payload | {'next': origin})
        self.assertRedirects(response, reverse('banking:detail', args=[self.bank.pk]) + '#reward-redemptions', fetch_redirect_response=False)

    def test_explicit_origin_survives_real_form_errors_and_success(self):
        for origin in [reverse('banking:list'), reverse('banking:list') + '?q=Receiving&page=2#account-row-' + str(self.account.pk)]:
            with self.subTest(origin=origin):
                response = self.client.get(self.url, {'next': origin})
                self.assertEqual(response.context['cancel_url'], origin)
                submitted_origin = self.hidden_origin(response)
                self.assertEqual(submitted_origin, origin)
                response = self.client.post(self.url, self.payload | {'next': submitted_origin, 'points': '1001'})
                self.assertEqual(response.status_code, 200)
                self.assertIn('points', response.context['form'].errors)
                self.assertEqual(self.hidden_origin(response), origin)
                response = self.client.post(self.url, self.payload | {'next': self.hidden_origin(response)})
                self.assertRedirects(response, origin, fetch_redirect_response=False)

    def test_external_origin_uses_default_history_after_recovery(self):
        response = self.client.get(self.url, {'next': '//example.test/steal'})
        self.assertEqual(self.hidden_origin(response), '')
        self.assertEqual(response.context['cancel_url'], reverse('banking:list'))
        response = self.client.post(self.url, self.payload | {'next': self.hidden_origin(response)})
        self.assertRedirects(response, reverse('banking:detail', args=[self.bank.pk]) + '#reward-redemptions', fetch_redirect_response=False)

    def test_related_account_form_keeps_dynamic_default_shortcut_and_origin(self):
        url = reverse('banking:account_create')
        origin = reverse('banking:list') + '?q=Receiving'
        cases = [({}, '', reverse('banking:list')),
                 ({'bank': self.bank.pk}, '', reverse('banking:detail', args=[self.bank.pk])),
                 ({'bank': self.bank.pk, 'next': origin}, origin, origin)]
        for index, (query, explicit, cancel) in enumerate(cases):
            with self.subTest(query=query):
                response = self.client.get(url, query)
                self.assertEqual(response.context['cancel_url'], cancel)
                self.assertEqual(self.hidden_origin(response), explicit)
                payload = {'bank': self.bank.pk, 'name': f'New account {index}', 'currency': 'BRL',
                           'opening_balance': '100', 'opening_date': '2025-01-01',
                           'reserved_amount': '0', 'next': self.hidden_origin(response)}
                response = self.client.post(url, payload)
                destination = explicit or reverse('banking:detail', args=[self.bank.pk])
                self.assertRedirects(response, destination, fetch_redirect_response=False)
