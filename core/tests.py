import os
import subprocess
import sys
import tempfile
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
        environment['TUXEDO_ENV_FILE'] = '/path/that/does/not/exist/.env'
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

    def test_secret_key_can_be_loaded_from_env_file(self):
        environment = os.environ.copy()
        environment.pop('SECRET_KEY', None)
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / '.env'
            env_file.write_text('SECRET_KEY=local-file-secret\n', encoding='utf-8')
            environment['TUXEDO_ENV_FILE'] = str(env_file)
            result = subprocess.run(
                [sys.executable, 'manage.py', 'check'],
                cwd=Path(__file__).resolve().parent.parent,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_process_secret_key_overrides_env_file(self):
        environment = os.environ.copy()
        environment['SECRET_KEY'] = 'process-secret'
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / '.env'
            env_file.write_text('SECRET_KEY=file-secret\n', encoding='utf-8')
            environment['TUXEDO_ENV_FILE'] = str(env_file)
            result = subprocess.run(
                [
                    sys.executable,
                    '-c',
                    'from django.conf import settings; print(settings.SECRET_KEY)',
                ],
                cwd=Path(__file__).resolve().parent.parent,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'process-secret')

    def test_tuxedo_data_dir_sets_database_location(self):
        environment = os.environ.copy()
        environment['SECRET_KEY'] = 'process-secret'
        environment['TUXEDO_ENV_FILE'] = '/path/that/does/not/exist/.env'
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment['TUXEDO_DATA_DIR'] = temporary_directory
            result = subprocess.run(
                [
                    sys.executable,
                    '-c',
                    (
                        'from django.conf import settings; '
                        'print(settings.DATABASES["default"]["NAME"])'
                    ),
                ],
                cwd=Path(__file__).resolve().parent.parent,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            Path(result.stdout.strip()),
            Path(temporary_directory) / 'db.sqlite3',
        )


class LanguageSelectionTests(TestCase):
    def test_public_page_defaults_to_english_and_shows_selector(self):
        response = self.client.get(reverse('pages:landing'))

        self.assertContains(response, '<html lang="en"', html=False)
        self.assertContains(response, 'id="language-select-public"')
        self.assertEqual(response.content.count(b'class="bg-white text-forest dark:bg-night-surface dark:text-cream"'), 2)
        self.assertContains(response, 'Log in')
        self.assertContains(
            response,
            'https://github.com/HenriqueMayer/TuxedoFinance/issues/new',
        )
        self.assertContains(response, 'Problems / Suggestions')
        self.assertContains(response, 'Roadmap')
        self.assertContains(response, '/static/js/project-menu.js?v=4')
        self.assertContains(
            response,
            'A personal Tuxedo assistant to ask questions, review your finances, and plan.',
        )
        self.assertContains(response, 'Improvements to investment tracking and analysis.')
        self.assertContains(
            response,
            'Automatic monthly and annual investment yield calculations.',
        )


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
            'Aplicação local para registrar receitas e despesas, acompanhar contas e faturas e organizar investimentos.',
        )
        self.assertContains(translated, 'Problemas / Sugestões')
        self.assertContains(translated, 'Próximas implementações')
        self.assertContains(
            translated,
            'Um assistente pessoal Tuxedo para tirar dúvidas, revisar suas finanças e planejar.',
        )
        self.assertContains(
            translated,
            'Melhorias no acompanhamento e na análise de investimentos.',
        )
        self.assertContains(
            translated,
            'Cálculos automáticos de rendimento mensal e anual dos investimentos.',
        )

    @override_settings(DEBUG=False)
    def test_precompiled_tailwind_is_used_without_the_play_cdn(self):
        response = self.client.get(reverse('pages:landing'))

        self.assertContains(response, '/static/css/app.css?v=11')
        self.assertNotContains(response, 'https://cdn.tailwindcss.com')
        self.assertNotContains(response, 'unpkg.com')
        self.assertNotContains(response, 'css/output.css')
        self.assertContains(response, '/static/js/vendor/htmx.min.js?v=2.0.10')
        self.assertContains(response, 'hx-boost="true"')
        self.assertContains(response, 'hx-request=\'{"noHeaders":true}\'')
        self.assertContains(response, 'hx-boost="false"')
        self.assertContains(response, '/static/js/navigation.js?v=3')

    def test_authenticated_nav_has_desktop_and_mobile_selectors(self):
        user = User.objects.create_user('language', password='test')
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, 'id="language-select-desktop"')
        self.assertContains(response, 'id="language-select-mobile"')
        self.assertEqual(response.content.count(b'data-theme-toggle'), 2)
        self.assertEqual(response.content.count(b'id="theme-toggle"'), 1)
        self.assertContains(response, '/static/js/theme.js?v=3')
        self.assertContains(response, '/static/js/project-menu.js?v=4')
        self.assertContains(response, '/static/js/mobile-menu.js?v=3')
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, 'aria-modal="true"')
        self.assertContains(
            response,
            f'href="{reverse("pages:landing")}" class="flex shrink-0 items-center gap-3 group',
        )
        self.assertContains(response, 'aria-label="Settings"')
        self.assertContains(response, reverse('accounts:settings'))

    def test_shell_enforces_content_security_policy(self):
        response = self.client.get(reverse('pages:landing'))

        policy = response.headers['Content-Security-Policy']
        self.assertIn("default-src 'self'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("script-src 'self' 'unsafe-inline'", policy)
        self.assertNotContains(response, 'onchange=')

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
