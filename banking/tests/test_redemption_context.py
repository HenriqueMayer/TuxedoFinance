# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit chart origins survive the inline redemption editor."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from banking.models import Bank, BankAccount, LoyaltyEntry, LoyaltyProgram
from banking.services import create_reward_redemption
from core.navigation import with_return_url


class RewardRedemptionContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('redemption-context-owner')
        self.other = get_user_model().objects.create_user('redemption-context-other')
        self.bank = Bank.objects.create(user=self.user, name='Receiving context bank')
        self.target = BankAccount.objects.create(user=self.user, bank=self.bank,
            name='Reward destination', currency='BRL')
        self.new_bank = Bank.objects.create(user=self.user, name='New receiving context bank')
        self.new_target = BankAccount.objects.create(user=self.user, bank=self.new_bank,
            name='Changed destination', currency='BRL')
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Context rewards')
        LoyaltyEntry.objects.create(user=self.user, program=self.program, direction='CREDIT',
            kind='ADJUSTMENT', amount=1000, date=date(2026, 9, 1))
        self.redemption = create_reward_redemption(user=self.user, program=self.program,
            points=Decimal('100'), target_account=self.target, target_amount=Decimal('25'),
            date=date(2026, 9, 21))
        self.path = reverse('banking:redemption_update', args=[self.redemption.pk])
        self.bank_path = reverse('banking:detail', args=[self.bank.pk])
        self.anchor = f'#reward-redemption-{self.redemption.pk}'
        self.editor = f'{self.bank_path}?edit_redemption={self.redemption.pk}{self.anchor}'
        self.origin = '/reports/?instrument_month=2026-09&charts_offset=-1#instrument-activity'
        self.client.force_login(self.user)

    def values(self, **changes):
        fields = {'program': self.program.pk, 'points': '100', 'target_account': self.target.pk,
            'target_amount': '25', 'iof_amount': '0', 'iof_account': '', 'iof_credit_card': '',
            'date': '2026-09-21', 'notes': 'Preserved contextual edit'} | changes
        return {f'redemption-{name}': str(value) for name, value in fields.items()}

    def assert_inline_origin(self, response, origin, cancel):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['redemption_origin'], origin)
        self.assertEqual(response.context['redemption_cancel_url'], cancel)
        self.assertContains(response, f'name="next" value="{escape(origin)}"')
        self.assertContains(response, f'href="{escape(cancel)}" class="quiet-action">Cancel</a>')

    def test_get_redirect_and_inline_cancel_preserve_explicit_filtered_origin(self):
        response = self.client.get(self.path, {'next': self.origin})
        self.assertRedirects(response, with_return_url(self.editor, self.origin), fetch_redirect_response=False)
        self.assert_inline_origin(self.client.get(response.url), self.origin, self.origin)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.target_amount, Decimal('25'))

    def test_invalid_fields_and_domain_errors_keep_submitted_origin_and_values(self):
        for changes, field in [({'target_amount': '-1'}, 'target_amount'), ({'points': '1001'}, 'points')]:
            with self.subTest(changes=changes):
                response = self.client.post(self.path, self.values(**changes) | {'next': self.origin})
                self.assert_inline_origin(response, self.origin, self.origin)
                form = response.context['redemption_form']
                self.assertTrue(form.errors)
                self.assertEqual(form[field].value(), changes[field])
                self.assertEqual(form['target_account'].value(), str(self.target.pk))
                self.redemption.refresh_from_db()
                self.assertEqual(self.redemption.target_amount, Decimal('25'))
                self.assertEqual(self.program.balance, Decimal('900'))

    def test_success_returns_to_explicit_origin_after_updating_owned_redemption(self):
        response = self.client.post(self.path, self.values(target_amount='30.25') | {'next': self.origin})
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.target_amount, Decimal('30.25'))
        self.assertEqual(self.redemption.notes, 'Preserved contextual edit')

    def test_without_origin_cancel_keeps_bank_and_success_uses_updated_receiving_bank(self):
        response = self.client.get(self.path)
        self.assertRedirects(response, self.editor, fetch_redirect_response=False)
        self.assert_inline_origin(self.client.get(response.url), '', self.bank_path + self.anchor)
        invalid = self.client.post(self.path, self.values(target_amount='-1') | {'next': ''})
        self.assert_inline_origin(invalid, '', self.bank_path + self.anchor)
        response = self.client.post(self.path, self.values(target_account=self.new_target.pk) | {'next': ''})
        self.assertRedirects(response, reverse('banking:detail', args=[self.new_bank.pk]) + self.anchor,
            fetch_redirect_response=False)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.target_account, self.new_target)

    def test_external_origins_are_not_forwarded_rendered_or_used_after_save(self):
        for origin in ['//outside.example/reports', 'https://outside.example/reports', '/\\outside.example/reports']:
            with self.subTest(origin=origin):
                response = self.client.get(self.path, {'next': origin})
                self.assertRedirects(response, self.editor, fetch_redirect_response=False)
                self.assert_inline_origin(self.client.get(response.url), '', self.bank_path + self.anchor)
                invalid = self.client.post(self.path, self.values(target_amount='-1') | {'next': origin})
                self.assert_inline_origin(invalid, '', self.bank_path + self.anchor)
                response = self.client.post(self.path, self.values() | {'next': origin})
                self.assertRedirects(response, self.bank_path + self.anchor, fetch_redirect_response=False)

    def test_origin_does_not_bypass_redemption_or_inline_bank_ownership(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.path, {'next': self.origin}).status_code, 404)
        self.assertEqual(self.client.post(self.path, self.values(target_amount='99') | {'next': self.origin}).status_code, 404)
        self.assertEqual(self.client.get(self.bank_path, {'edit_redemption': self.redemption.pk,
            'next': self.origin}).status_code, 404)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.target_amount, Decimal('25'))
