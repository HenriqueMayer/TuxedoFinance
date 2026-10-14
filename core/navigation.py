# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit local return destinations for contextual financial form journeys."""
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


def safe_local_url(value, fallback=''):
    """Accept a local absolute path, never a host, scheme or browser redirect."""
    if not isinstance(value, str) or not value.startswith('/'):
        return fallback
    decoded = value
    for _ in range(4):
        if (decoded.startswith('//') or '\\' in decoded
                or any(ord(char) < 32 or ord(char) == 127 for char in decoded)):
            return fallback
        try:
            parts = urlsplit(decoded)
        except ValueError:
            return fallback
        if parts.scheme or parts.netloc or not parts.path.startswith('/'):
            return fallback
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            return value
        decoded = next_decoded
    # Reject unusually nested encodings instead of guessing how a browser parses them.
    return fallback


def return_url(request, fallback):
    """Preserve the submitted origin on errors; never infer one from Referer."""
    values = request.POST if request.method == 'POST' and 'next' in request.POST else request.GET
    return safe_local_url(values.get('next', ''), fallback)


def with_return_url(target, origin, *, fragment=None):
    """Encode an explicit origin, optionally its stable on-page anchor."""
    target = safe_local_url(str(target), '/')
    origin = safe_local_url(str(origin))
    if not origin:
        return target
    if fragment is not None:
        parts = urlsplit(origin)
        origin = urlunsplit(parts._replace(fragment=str(fragment).lstrip('#')))
        origin = safe_local_url(origin)
        if not origin:
            return target
    parts = urlsplit(target)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'next']
    query.append(('next', origin))
    return urlunsplit(parts._replace(query=urlencode(query)))


class ReturnContextMixin:
    """CBV return context; dynamic defaults override get_return_fallback."""

    def get_return_fallback(self):
        return str(self.success_url)

    def get_return_url(self):
        return return_url(self.request, self.get_return_fallback())

    def get_success_url(self):
        return self.get_return_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['return_url'] = self.get_return_url()
        return context
