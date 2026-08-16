import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import UserPreference


User = get_user_model()


class SettingsSecurityTests(SimpleTestCase):
    def test_secret_key_is_required_at_startup(self):
        environment = os.environ.copy()
        environment.pop('SECRET_KEY', None)
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            cwd=Path(__file__).resolve().parent.parent,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY must be set in the environment.', result.stderr)


class LanguageSelectionTests(TestCase):
    def test_public_page_defaults_to_english_and_shows_selector(self):
        response = self.client.get(reverse('pages:landing'))

        self.assertContains(response, '<html lang="en"', html=False)
        self.assertContains(response, 'id="language-select-public"')
        self.assertContains(response, 'Log in')


    def test_set_language_persists_portuguese_in_cookie(self):
        response = self.client.post(
            reverse('set_language'),
            {'language': 'pt-br', 'next': reverse('pages:landing')},
        )

        self.assertRedirects(response, reverse('pages:landing'))
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'pt-br')

        translated = self.client.get(reverse('pages:landing'))
        self.assertContains(translated, '<html lang="pt-br"', html=False)
        self.assertContains(translated, 'Entrar')
        self.assertContains(translated, 'Cadastre-se')
        self.assertContains(
            translated,
            'Nascido da frustração diária de adaptar planilhas às finanças pessoais reais.',
        )

    @override_settings(DEBUG=False)
    def test_tailwind_cdn_is_used_without_a_production_static_build(self):
        response = self.client.get(reverse('pages:landing'))

        self.assertContains(response, 'https://cdn.tailwindcss.com')
        self.assertNotContains(response, 'css/output.css')

    def test_authenticated_nav_has_desktop_and_mobile_selectors(self):
        user = User.objects.create_user('language', password='test')
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, 'id="language-select-desktop"')
        self.assertContains(response, 'id="language-select-mobile"')
        self.assertEqual(response.content.count(b'data-theme-toggle'), 2)
        self.assertEqual(response.content.count(b'id="theme-toggle"'), 1)
        self.assertContains(response, '/static/js/theme.js?v=2')

    def test_htmx_reports_respect_selected_language(self):
        user = User.objects.create_user('reports-language', password='test')
        self.client.force_login(user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'pt-br'

        response = self.client.get(
            reverse('dashboard:reports'),
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Receitas e despesas por conta ou cartão')
        self.assertNotContains(response, '<html')

    def test_currency_separators_do_not_change_with_ui_language(self):
        from django.utils import translation
        from django.utils.formats import number_format

        with translation.override('en'):
            english = number_format(1234.5, decimal_pos=2, use_l10n=True, force_grouping=True)
        with translation.override('pt-br'):
            portuguese = number_format(1234.5, decimal_pos=2, use_l10n=True, force_grouping=True)

        self.assertEqual(portuguese, english)


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
