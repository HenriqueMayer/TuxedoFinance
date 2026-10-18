#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Serve an owned loopback preview; capture binds port zero without rebinding."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[2]


class StaticPreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, ready_token='', **kwargs):
        self.ready_path = f'/__preview_ready__/{ready_token}' if ready_token else None
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.ready_path and self.path == self.ready_path:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Owned static preview server')
            return
        super().do_GET()


def validate_capture_environment():
    directory = Path(os.environ.get('TUXEDO_DATA_DIR', '')).resolve()
    if (os.environ.get('PREVIEW_CAPTURE') != '1'
            or not directory.name.startswith('tuxedo-preview-data.')
            or directory == ROOT or ROOT in directory.parents
            or os.environ.get('TUXEDO_ENV_FILE') != os.devnull):
        raise RuntimeError('Capture requires an isolated PREVIEW_CAPTURE temporary directory and empty environment file.')


def capture_server():
    validate_capture_environment()
    sys.path.insert(0, str(ROOT))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application

    return make_server('127.0.0.1', 0, StaticFilesHandler(get_wsgi_application()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static', action='store_true', help='Serve only the committed public tour.')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-token', default='')
    parser.add_argument('--ready-file', type=Path)
    args = parser.parse_args()
    if not args.static and args.port:
        parser.error('Capture always owns an automatically allocated port.')
    if args.static:
        handler = partial(StaticPreviewHandler, directory=str(ROOT / 'preview'), ready_token=args.ready_token)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    else:
        server = capture_server()
    with server:
        # Publish readiness only after the socket is bound; never release and
        # reacquire a capture port or accept a previously running application.
        url = f'http://127.0.0.1:{server.server_port}'
        if args.ready_file:
            args.ready_file.write_text(url, encoding='utf-8')
        print(f'Preview server: {url}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
