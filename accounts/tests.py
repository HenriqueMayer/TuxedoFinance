from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from categories.models import Category
from payments.models import PaymentMethod


class SignupViewTests(TestCase):
    """PRD 3.1, FR02, FR14 — sign up creates the user, seeds defaults, auto-logs-in."""

    def test_signup_creates_user_seeds_defaults_and_logs_in(self):
        response = self.client.post(reverse('accounts:signup'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('dashboard:index'))

        user = User.objects.get(username='newuser')
        self.assertEqual(Category.objects.filter(user=user).count(), 9)
        self.assertEqual(PaymentMethod.objects.filter(user=user).count(), 4)

        # Auto-logged-in: the dashboard is reachable without a fresh login call.
        dashboard_response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(dashboard_response.status_code, 200)

    def test_signup_invalid_data_does_not_create_user(self):
        response = self.client.post(reverse('accounts:signup'), {
            'username': 'baduser',
            'email': 'bad@example.com',
            'password1': 'StrongPass123!',
            'password2': 'Mismatch123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='baduser').exists())


class LoginViewTests(TestCase):
    """PRD 3.2, 3.3 — valid login redirects to the dashboard; invalid login is friendly."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='StrongPass123!')

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'alice',
            'password': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('dashboard:index'))

    def test_invalid_login_shows_friendly_error_not_500(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'alice',
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Please enter a correct username and password.',
        )


class LogoutViewTests(TestCase):
    """PRD 3.2.2 — logout is POST-only and redirects to the public landing page."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='StrongPass123!')

    def test_logout_get_is_not_allowed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 405)

    def test_logout_post_redirects_to_landing_and_clears_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('pages:landing'))

        # Session cleared: the dashboard requires a fresh login again.
        dashboard_response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(dashboard_response.status_code, 302)
