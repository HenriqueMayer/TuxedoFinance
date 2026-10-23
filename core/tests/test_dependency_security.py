"""Request-parser security regressions for the supported Django baseline.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils.translation import trans_real


class DependencyParserSecurityTests(SimpleTestCase):
    def test_distinct_long_language_cookies_share_bounded_cache_keys(self):
        # CVE-2026-77050: truncation must happen before the cached lookup.
        lookup = getattr(
            trans_real, '_get_supported_language_variant',
            trans_real.get_supported_language_variant,
        )
        self.addCleanup(lookup.cache_clear)
        for prefix in ('en-' + 'x' * 600, 'en-' * 300):
            with self.subTest(prefix_length=len(prefix)):
                lookup.cache_clear()
                for index in range(8):
                    self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = prefix + str(index)
                    response = self.client.get(reverse('pages:landing'))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers['Content-Language'], 'en')
                self.assertEqual(lookup.cache_info().currsize, 1)

    def test_quoted_content_type_separators_preserve_public_response(self):
        response = self.client.get(
            reverse('pages:landing'),
            CONTENT_TYPE='text/plain; note="' + ';' * 9000 + '"; charset=utf-8',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Language'], 'en')

    def test_quoted_accept_separators_preserve_native_language_redirect(self):
        response = self.client.get(
            reverse('set_language'),
            HTTP_ACCEPT='text/html; note="' + ';' * 9000 + '", text/html',
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')

    def test_native_language_form_retains_charset_and_quoted_parameters(self):
        response = self.client.post(
            reverse('set_language'),
            data='language=pt-br&next=%2F',
            content_type='application/x-www-form-urlencoded; charset=UTF-8; note="a;b"',
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'pt-br')
