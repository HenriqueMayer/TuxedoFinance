# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Recover old HTMX documents before they combine new markup with old assets."""
from django.utils.cache import patch_cache_control, patch_vary_headers

from core.assets import frontend_revision


class FrontendAssetsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tuxedo_asset_revision = frontend_revision()
        response = self.get_response(request)
        if not response.get('Content-Type', '').startswith('text/html'):
            return response
        revision = request.tuxedo_asset_revision
        response['X-Tuxedo-Assets'] = revision
        patch_vary_headers(response, ['X-Tuxedo-Assets'])
        patch_cache_control(response, no_cache=True)
        if (request.method == 'GET' and response.status_code == 200
                and request.headers.get('X-Tuxedo-Assets') != revision
                and 'HX-Redirect' not in response):
            # Legacy boosted requests deliberately suppress HX-Request. The
            # header is harmless on normal HTML navigation; HTMX follows it
            # with one full GET to the intended URL, updating head and body.
            # Never redirect/replay a POST or discard its validation response.
            response['HX-Redirect'] = request.get_full_path()
        return response
