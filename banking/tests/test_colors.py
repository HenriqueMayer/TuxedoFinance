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

    def test_bank_create_edit_and_marker_use_the_shared_native_color_picker(self):
        for url in (reverse('banking:create'),
                    reverse('banking:update', args=[self.bank.pk]),
                    reverse('banking:color', args=[self.bank.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'data-color-picker', count=1)
                self.assertContains(response, 'list="id_color-palette"')
                self.assertContains(response, 'value="#64788C" label="Blue gray"')
                self.assertContains(response, 'data-color-presets')
        response = self.client.post(reverse('banking:create'),
                                    {'name': 'Custom bank', 'color': '#abcdef'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Bank.objects.get(user=self.user, name='Custom bank').color,
                         '#ABCDEF')

    def test_invalid_bank_hex_renders_raw_text_instead_of_sanitizing_to_black(self):
        response = self.client.post(reverse('banking:color', args=[self.bank.pk]),
                                    {'color': '#12ZZ89'})
        self.assertContains(response, 'type="text" name="color" value="#12ZZ89"')
        self.assertContains(response, 'aria-invalid="true"')
