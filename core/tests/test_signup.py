"""Signup coverage for core."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


class SignupControlTests(TestCase):
    @override_settings(ALLOW_SIGNUPS=False)
    def test_signup_route_blocks_get_and_post_without_creating_user(self):
        response = self.client.get(reverse('accounts:signup'))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Registration is currently closed', status_code=403)

        response = self.client.post(
            reverse('accounts:signup'),
            {'username': 'blocked', 'email': 'blocked@example.com', 'password1': 'A-strong-password-123', 'password2': 'A-strong-password-123'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username='blocked').exists())

    @override_settings(ALLOW_SIGNUPS=False)
    def test_public_ctas_are_hidden_when_signup_is_disabled(self):
        landing = self.client.get(reverse('pages:landing'))
        login = self.client.get(reverse('accounts:login'))
        self.assertNotContains(landing, reverse('accounts:signup'))
        self.assertNotContains(login, reverse('accounts:signup'))
