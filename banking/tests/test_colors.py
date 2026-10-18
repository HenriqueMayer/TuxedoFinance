# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from banking.models import Bank


class BankColorTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('color', password='test')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Bank')

    def test_default_creation_and_color_only_update(self):
        self.assertEqual(self.bank.color, '#B88D57')
        self.client.post(reverse('banking:color', args=[self.bank.pk]), {'color':'#12abef'})
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.color, '#12ABEF')
        self.assertEqual(self.bank.name, 'Bank')
        self.client.post(reverse('banking:update', args=[self.bank.pk]), {'name':'Renamed'})
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.color, '#12ABEF')

    def test_invalid_css_and_other_owner_cannot_change_color(self):
        for invalid in ['red', '#ABC', '#ffffff;position:fixed', '#12ZZ89']:
            response = self.client.post(reverse('banking:color', args=[self.bank.pk]), {'color':invalid})
            self.assertTrue(response.context['form'].errors)
            self.bank.refresh_from_db()
            self.assertEqual(self.bank.color, '#B88D57')
        other = get_user_model().objects.create_user('other-color', password='test')
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse('banking:color', args=[self.bank.pk]), {'color':'#000000'}).status_code, 404)
