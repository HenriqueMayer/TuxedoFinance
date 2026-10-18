"""Languages coverage for core."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from core.assets import asset_url


User = get_user_model()


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
        self.assertContains(response, asset_url('js/project-menu.js'))
        self.assertContains(
            response,
            'A personal Tuxedo assistant to ask questions, review your finances, and plan.',
        )
        self.assertContains(response, 'Market quotes and historical prices with source and valuation date.')
        self.assertContains(
            response,
            'An integrated assistant for portfolio research and planning.',
        )


    def test_set_language_persists_portuguese_in_cookie(self):
        response = self.client.post(
            reverse('set_language'),
            {'language': 'pt-br', 'next': reverse('pages:landing')},
        )

        self.assertRedirects(response, reverse('pages:landing'))
        language_cookie = response.cookies[settings.LANGUAGE_COOKIE_NAME]
        self.assertEqual(language_cookie.value, 'pt-br')
        self.assertEqual(language_cookie['max-age'], settings.LANGUAGE_COOKIE_AGE)
        self.assertEqual(language_cookie['samesite'], settings.LANGUAGE_COOKIE_SAMESITE)

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
            'Um assistente integrado para pesquisa de carteira e planejamento.',
        )
        self.assertContains(
            translated,
            'Cotações e histórico de preços com fonte e data de avaliação.',
        )

        english_response = self.client.post(
            reverse('set_language'),
            {'language': 'en', 'next': reverse('pages:landing')},
        )
        english_cookie = english_response.cookies[settings.LANGUAGE_COOKIE_NAME]
        self.assertEqual(english_cookie.value, 'en')
        self.assertEqual(english_cookie['max-age'], settings.LANGUAGE_COOKIE_AGE)
        self.assertEqual(english_cookie['samesite'], settings.LANGUAGE_COOKIE_SAMESITE)
        english = self.client.get(reverse('pages:landing'))
        self.assertContains(english, '<html lang="en"', html=False)
        self.assertContains(english, 'Log in')

    @override_settings(DEBUG=False)
    def test_precompiled_tailwind_is_used_without_the_play_cdn(self):
        response = self.client.get(reverse('pages:landing'))

        self.assertContains(response, asset_url('css/app.css'))
        self.assertNotContains(response, 'https://cdn.tailwindcss.com')
        self.assertNotContains(response, 'unpkg.com')
        self.assertNotContains(response, 'css/output.css')
        self.assertContains(response, asset_url('js/vendor/htmx.min.js'))
        self.assertContains(response, 'hx-boost="true"')
        self.assertContains(response, 'hx-request=\'{"noHeaders":true}\'')
        self.assertContains(response, 'hx-boost="false"')
        self.assertContains(response, asset_url('js/navigation.js'))
        self.assertContains(response, asset_url('js/runtime-assets.js'))
        self.assertContains(response, 'name="tuxedo-assets"')

    def test_authenticated_nav_has_desktop_and_mobile_selectors(self):
        user = User.objects.create_user('language', password='test')
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, 'id="language-select-desktop"')
        self.assertContains(response, 'id="language-select-mobile"')
        self.assertEqual(response.content.count(b'data-theme-toggle'), 2)
        self.assertEqual(response.content.count(b'id="theme-toggle"'), 1)
        self.assertContains(response, asset_url('js/theme.js'))
        self.assertContains(response, asset_url('js/project-menu.js'))
        self.assertContains(response, asset_url('js/mobile-menu.js'))
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, 'aria-modal="true"')
        self.assertContains(
            response,
            f'<a href="{reverse("dashboard:index")}" class="app-brand">',
        )
        self.assertContains(response, '<span>Tuxedo Finance</span>', html=True)
        self.assertContains(
            response,
            '<span class="app-current-workspace hidden lg:block">Home</span>',
            html=True,
        )
        self.assertContains(response, 'data-app-navigation="desktop"')
        self.assertContains(response, 'data-app-navigation="mobile"')
        self.assertNotContains(response, 'data-nav-menu')
        for area in ('home', 'transactions', 'accounts', 'investments', 'plan'):
            self.assertContains(response, f'id="app-desktop-{area}-link"')
            self.assertContains(response, f'id="app-mobile-{area}-link"')
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
