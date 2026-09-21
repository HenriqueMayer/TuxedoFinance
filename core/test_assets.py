# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, override_settings
from whitenoise.middleware import WhiteNoiseMiddleware

from core.assets import asset_url, frontend_revision
from core.middleware import FrontendAssetsMiddleware


class FrontendAssetTests(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='tuxedo-assets-test-')
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.source = root / 'source'
        self.collected = root / 'collected'
        for directory in (self.source, self.collected):
            (directory / 'css').mkdir(parents=True)
            (directory / 'js').mkdir()
        self.css = self.source / 'css/app.css'
        self.css.write_text('old')
        (self.source / 'js/navigation.js').write_text('initial JavaScript')
        self.override = override_settings(
            DEBUG=True, STATIC_URL='/static/', STATIC_ROOT=self.collected,
            STATICFILES_DIRS=[self.source],
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
            },
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        finders.get_finder.cache_clear()
        self.addCleanup(finders.get_finder.cache_clear)
        self.factory = RequestFactory()

    def test_urls_follow_bytes_even_for_same_length_edit_with_preserved_mtime(self):
        before = asset_url('css/app.css')
        stamp = self.css.stat()
        self.css.write_text('new')
        os.utime(self.css, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertNotEqual(asset_url('css/app.css'), before)
        self.assertEqual(asset_url('css/app.css'), '/static/css/app.css?v=' + sha256(b'new').hexdigest()[:20])
        current = asset_url('css/app.css')
        self.css.touch()
        self.assertEqual(asset_url('css/app.css'), current)

    def test_revision_tracks_domain_javascript_and_new_scripts(self):
        before = frontend_revision()
        css_url = asset_url('css/app.css')
        (self.source / 'js/sandbox.js').write_text('new domain JavaScript')
        self.assertNotEqual(frontend_revision(), before)
        self.assertEqual(asset_url('css/app.css'), css_url)

    def test_development_ignores_stale_collected_files(self):
        (self.collected / 'css/app.css').write_text('stale production copy')
        self.assertEqual(asset_url('css/app.css'), '/static/css/app.css?v=' + sha256(b'old').hexdigest()[:20])

    @override_settings(DEBUG=False, WHITENOISE_USE_FINDERS=False, WHITENOISE_AUTOREFRESH=False)
    def test_production_version_matches_bytes_served_by_whitenoise(self):
        served = b'collected CSS from the image build'
        (self.collected / 'css/app.css').write_bytes(served)
        url = asset_url('css/app.css')
        self.assertEqual(url, '/static/css/app.css?v=' + sha256(served).hexdigest()[:20])
        middleware = WhiteNoiseMiddleware(lambda request: HttpResponse(status=404))
        response = middleware(self.factory.get(url))
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), served)
        finally:
            response.close()

    def test_template_tags_share_the_request_revision(self):
        request = self.factory.get('/')
        request.tuxedo_asset_revision = 'captured-for-this-response'
        rendered = Template('{% load assets %}{% asset_revision %}|{% asset "css/app.css" %}').render(Context({'request': request}))
        self.assertEqual(rendered, 'captured-for-this-response|' + asset_url('css/app.css'))

    def test_legacy_and_old_get_requests_keep_full_html_and_refresh_destination(self):
        middleware = FrontendAssetsMiddleware(lambda request: HttpResponse('<html>complete response</html>'))
        for headers in ({}, {'HTTP_X_TUXEDO_ASSETS': 'old-document'}, {'HTTP_HX_REQUEST': 'true'}):
            with self.subTest(headers=headers):
                response = middleware(self.factory.get('/transactions/?date=2026-04-03', **headers))
                self.assertEqual(response.content, b'<html>complete response</html>')
                self.assertEqual(response['HX-Redirect'], '/transactions/?date=2026-04-03')
                self.assertIn('no-cache', response['Cache-Control'])

    def test_current_document_keeps_htmx_and_post_is_never_redirected_or_repeated(self):
        calls = []

        def view(request):
            calls.append(request.method)
            return HttpResponse('bound invalid form')

        middleware = FrontendAssetsMiddleware(view)
        current = middleware(self.factory.get('/', HTTP_X_TUXEDO_ASSETS=frontend_revision()))
        self.assertNotIn('HX-Redirect', current)
        self.assertIn('X-Tuxedo-Assets', current['Vary'])
        for headers in ({}, {'HTTP_X_TUXEDO_ASSETS': 'old-document'}):
            response = middleware(self.factory.post('/sandbox/', {'amount': 'invalid'}, **headers))
            self.assertEqual(response.content, b'bound invalid form')
            self.assertNotIn('HX-Redirect', response)
        self.assertEqual(calls, ['GET', 'POST', 'POST'])

    def test_non_html_and_existing_navigation_contracts_are_preserved(self):
        csv = FrontendAssetsMiddleware(lambda request: HttpResponse('date,amount', content_type='text/csv'))
        self.assertNotIn('HX-Redirect', csv(self.factory.get('/export/')))

        def declared_redirect(request):
            response = HttpResponse('existing flow')
            response['HX-Redirect'] = '/saved-draft/'
            return response

        response = FrontendAssetsMiddleware(declared_redirect)(self.factory.get('/draft/'))
        self.assertEqual(response['HX-Redirect'], '/saved-draft/')
