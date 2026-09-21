# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Content versions for the assets actually delivered by this installation."""
from hashlib import sha256
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static


def asset_file(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('An asset must use a relative static path.')
    # WhiteNoise serves the collected tree in production. runserver uses the
    # source finders in development; a stale collected directory must not win.
    collected = Path(staticfiles_storage.path(name))
    if not settings.DEBUG and collected.is_file():
        return collected
    source = finders.find(name)
    if source:
        return Path(source)
    raise ImproperlyConfigured(f'Missing frontend asset: {name}')


def _digest(path):
    # Filesystem timestamps can be preserved or have coarse resolution during
    # a rebuild. Reading this small local bundle also handles same-length edits.
    return sha256(path.read_bytes()).hexdigest()[:20]


def asset_digest(name):
    return _digest(asset_file(name))


def asset_url(name):
    url = static(name)
    separator = '&' if '?' in url else '?'
    return f'{url}{separator}v={asset_digest(name)}'


def frontend_revision():
    stylesheet = asset_file('css/app.css')
    root = stylesheet.parent.parent
    paths = [stylesheet, *sorted((root / 'js').rglob('*.js'))]
    digest = sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b'\0')
        digest.update(_digest(path).encode())
        digest.update(b'\0')
    return digest.hexdigest()[:20]
