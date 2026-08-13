from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


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
        self.assertContains(response, 'Gastos por cartão ou conta')
        self.assertNotContains(response, '<html')

    def test_currency_separators_do_not_change_with_ui_language(self):
        from django.utils import translation
        from django.utils.formats import number_format

        with translation.override('en'):
            english = number_format(1234.5, decimal_pos=2, use_l10n=True, force_grouping=True)
        with translation.override('pt-br'):
            portuguese = number_format(1234.5, decimal_pos=2, use_l10n=True, force_grouping=True)

        self.assertEqual(portuguese, english)
