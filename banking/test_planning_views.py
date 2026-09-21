"""Planning controls preserve ledger truth and request cost."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement


class PlanningAccountViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('planning-owner')
        self.other = get_user_model().objects.create_user('planning-other')
        self.bank = Bank.objects.create(user=self.user, name='Planning bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Reserve',
                                                  currency='BRL', opening_balance=5000, reserved_amount=2000)
        self.client.force_login(self.user)

    def test_toggle_changes_availability_without_posting_or_changing_balance(self):
        url = reverse('banking:account_planning', args=[self.account.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {'enabled': '0'}, HTTP_HX_TARGET=f'account-row-{self.account.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.account.refresh_from_db()
        self.assertFalse(self.account.planning_enabled)
        self.assertEqual(self.account.reserved_amount, Decimal('2000'))
        self.assertEqual(self.account.current_balance(), Decimal('5000'))
        self.assertFalse(BankMovement.objects.exists())
        self.assertEqual(self.client.post(url, {'enabled': '1'}).status_code, 302)
        self.account.refresh_from_db()
        self.assertTrue(self.account.planning_enabled)

    def test_other_user_cannot_toggle_and_invalid_choice_is_rejected(self):
        url = reverse('banking:account_planning', args=[self.account.pk])
        self.assertEqual(self.client.post(url, {'enabled': 'invalid'}).status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, {'enabled': '0'}).status_code, 404)

    def test_bank_list_query_count_does_not_grow_per_account(self):
        url = reverse('banking:list')
        self.client.get(url)  # initialize presentation preferences
        with CaptureQueriesContext(connection) as single:
            self.assertEqual(self.client.get(url).status_code, 200)
        for index in range(24):
            BankAccount.objects.create(user=self.user, bank=self.bank, name=f'Extra {index}', currency='BRL')
        with CaptureQueriesContext(connection) as many:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(many), len(single) + 1)
        self.assertContains(response, 'Extra 23')
