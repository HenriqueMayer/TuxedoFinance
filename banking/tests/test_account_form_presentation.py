# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Account setup explains its baseline without changing cash or reservations."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from banking.forms import BankAccountForm
from banking.models import Bank, BankAccount, BankMovement


class AccountFormPresentationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('account-presentation')
        self.bank = Bank.objects.create(user=self.user, name='Local bank')
        self.account = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Everyday', currency='BRL',
            opening_balance=Decimal('1000'), opening_date=date(2026, 1, 1),
        )
        self.client.force_login(self.user)

    def payload(self, **changes):
        return {
            'bank': self.bank.pk, 'name': self.account.name, 'currency': 'BRL',
            'opening_balance': '1000', 'opening_date': '2026-01-01',
            'pix_enabled': 'on', 'planning_enabled': 'on', 'reserved_amount': '0',
        } | changes

    def test_new_account_keeps_defaults_with_optional_planning_collapsed(self):
        form = BankAccountForm(user=self.user)
        self.assertFalse(form.planning_adjustments_open)
        self.assertTrue(form['planning_enabled'].value())
        self.assertEqual(form['reserved_amount'].value(), Decimal('0'))
        with override('en'):
            response = self.client.get(reverse('banking:account_create'))
        self.assertContains(response, 'Balance when tracking starts')
        self.assertContains(response, 'Start tracking on')
        self.assertContains(response, 'at the start of the chosen date and before its movements')
        self.assertContains(response, '<details id="account-planning-adjustments" class="explanation-disclosure finance-entry-section">')
        self.assertContains(response, 'name="planning_enabled"')
        self.assertContains(response, 'name="reserved_amount"')

    def test_existing_reserve_and_excluded_account_reveal_the_settings(self):
        for reserved, enabled in ((Decimal('25'), True), (Decimal('0'), False)):
            with self.subTest(reserved=reserved, enabled=enabled):
                self.account.reserved_amount = reserved
                self.account.planning_enabled = enabled
                self.account.save(update_fields=['reserved_amount', 'planning_enabled'])
                response = self.client.get(reverse('banking:account_update', args=[self.account.pk]))
                self.assertTrue(response.context['form'].planning_adjustments_open)
                self.assertContains(response, '<details id="account-planning-adjustments" class="explanation-disclosure finance-entry-section" open>')

    def test_invalid_bound_reserve_stays_visible_without_posting_money(self):
        response = self.client.post(
            reverse('banking:account_update', args=[self.account.pk]),
            self.payload(reserved_amount='-1'),
        )
        form = response.context['form']
        self.assertTrue(form.planning_adjustments_open)
        self.assertEqual(form['reserved_amount'].value(), '-1')
        self.assertIn('reserved_amount', form.errors)
        self.account.refresh_from_db()
        self.assertEqual(self.account.reserved_amount, Decimal('0'))
        self.assertFalse(BankMovement.objects.exists())

    def test_disclosure_submission_preserves_explicit_reserve_and_baseline(self):
        self.account.reserved_amount = Decimal('125.50')
        self.account.save(update_fields=['reserved_amount'])
        response = self.client.post(
            reverse('banking:account_update', args=[self.account.pk]),
            self.payload(name='Renamed', reserved_amount='125.50'),
        )
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual(self.account.reserved_amount, Decimal('125.50'))
        self.assertEqual(self.account.opening_balance, Decimal('1000'))
        self.assertEqual(self.account.opening_date, date(2026, 1, 1))
        self.assertTrue(self.account.planning_enabled)
        self.assertFalse(BankMovement.objects.exists())

    def test_clearer_date_label_keeps_nonzero_baseline_guard(self):
        form = BankAccountForm(
            self.payload(name='New', opening_date=''), user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('opening_date', form.errors)
        zero = BankAccountForm(
            self.payload(name='Zero', opening_date='', opening_balance='0'),
            user=self.user,
        )
        self.assertTrue(zero.is_valid(), zero.errors)

    def test_unknown_existing_baseline_stays_unknown_after_edit(self):
        self.account.opening_date = None
        self.account.save(update_fields=['opening_date'])
        response = self.client.post(
            reverse('banking:account_update', args=[self.account.pk]),
            self.payload(name='Legacy', opening_date=''),
        )
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertIsNone(self.account.opening_date)
        self.assertEqual(self.account.opening_balance, Decimal('1000'))
