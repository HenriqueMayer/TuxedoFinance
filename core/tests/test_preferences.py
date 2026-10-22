"""Preferences coverage for core."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounts.models import UserPreference


User = get_user_model()


class UserPreferenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('preferences', password='test')
        self.client.force_login(self.user)

    def test_settings_save_date_format_and_expose_template_format(self):
        response = self.client.post(
            reverse('accounts:settings'),
            {'base_currency': 'USD', 'date_format': 'MDY'},
        )
        self.assertRedirects(response, reverse('accounts:settings'))
        preference = UserPreference.for_user(self.user)
        self.assertEqual(preference.date_format, 'MDY')
        dashboard = self.client.get(reverse('dashboard:index'))
        self.assertEqual(dashboard.context['USER_DATE_FORMAT'], 'm/d/Y')

    def test_date_format_defaults_to_day_month_year(self):
        preference = UserPreference.for_user(self.user)
        self.assertEqual(preference.date_format, 'DMY')
        response = self.client.get(reverse('accounts:settings'))
        self.assertContains(response, 'DD/MM/YYYY')
        self.assertContains(response, 'MM/DD/YYYY')
