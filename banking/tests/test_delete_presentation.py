"""Localized confirmation identity without changing points or deletion rules.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, LoyaltyEntry, LoyaltyProgram


class DeletePresentationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('delete-presentation')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Editorial bank')
        self.program = LoyaltyProgram.objects.create(
            user=self.user, bank=self.bank, name='Programa da família', unit_name='Milhas',
        )
        self.entry = LoyaltyEntry.objects.create(
            user=self.user, program=self.program,
            direction=LoyaltyEntry.Direction.CREDIT, kind=LoyaltyEntry.Kind.ADJUSTMENT,
            amount=Decimal('12400.75'), date=date(2026, 10, 17),
        )

    def test_points_confirmation_uses_translated_direction_and_exact_localized_units(self):
        for language, expected in [
            ('pt-br', 'Crédito 12.400,75 Milhas'),
            # Numerical display follows the application's shared financial
            # format independently of the translated interface language.
            ('en', 'Credit 12.400,75 Milhas'),
        ]:
            with self.subTest(language=language):
                response = self.client.get(
                    reverse('banking:entry_delete', args=[self.entry.pk]),
                    HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Programa da família')
                self.assertContains(response, expected)
                self.assertNotContains(response, 'CREDIT')
                self.assertNotContains(response, '12400.75')
                self.assertContains(response, 'method="post"')
                self.entry.refresh_from_db()
                self.assertEqual(self.entry.amount, Decimal('12400.75'))

    def test_other_delete_confirmations_keep_the_generic_owned_item_name(self):
        response = self.client.get(
            reverse('banking:delete', args=[self.bank.pk]), HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delete Editorial bank?')
        self.assertNotContains(response, 'Milhas')
