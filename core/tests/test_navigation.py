# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from urllib.parse import parse_qs, urlsplit

from django.test import RequestFactory, SimpleTestCase

from core.navigation import return_url, safe_local_url, with_return_url


class ReturnContextTests(SimpleTestCase):
    def test_rejects_browser_redirects_and_encoded_control_characters(self):
        for value in ('https://example.test/', '//example.test/', '/\\example.test/',
                      '/%2fexample.test/', '/%252fexample.test/', '/%5cexample.test/',
                      '/ok\r\nLocation: https://example.test/', '/ok?x=%0a',
                      'relative/path', ' /safe/', '/%25252525252fexample.test/'):
            with self.subTest(value=value):
                self.assertEqual(safe_local_url(value, '/default/'), '/default/')
        self.assertEqual(safe_local_url('/transactions/?q=caf%C3%A9&month=2026-01#row-7'),
                         '/transactions/?q=caf%C3%A9&month=2026-01#row-7')

    def test_submitted_destination_wins_and_invalid_post_uses_default(self):
        factory = RequestFactory()
        request = factory.post('/transactions/create/?next=/from-get/', {'next': '/from-post/?month=2026-01'})
        self.assertEqual(return_url(request, '/default/'), '/from-post/?month=2026-01')
        request = factory.post('/transactions/create/?next=/from-get/', {'next': '//example.test/'})
        self.assertEqual(return_url(request, '/default/'), '/default/')

    def test_encoded_origin_preserves_filters_and_stable_position_anchor(self):
        result = with_return_url('/investments/create/?kind=YIELD&next=/old/',
                                 '/investments/?section=cash&q=CDB+local', fragment='position-12-34')
        query = parse_qs(urlsplit(result).query)
        self.assertEqual(query, {'kind': ['YIELD'], 'next': ['/investments/?section=cash&q=CDB+local#position-12-34']})
        self.assertEqual(with_return_url('/local/', '//external.test/'), '/local/')
