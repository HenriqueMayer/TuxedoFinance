# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Preview tools must own their server and dispose only their temporary data."""

from contextlib import redirect_stderr
from functools import partial
from http.server import ThreadingHTTPServer
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener

from scripts.preview import serve

ROOT = Path(__file__).resolve().parents[2]


class PreviewServerTests(TestCase):
    def test_playwright_workers_inherit_the_coordinators_endpoint(self):
        script = '''const {spawnSync} = require('node:child_process');
function configuration() {
    const fs = require('node:fs');
    const path = require('node:path');
    const vm = require('node:vm');
    const file = path.resolve('tests/preview/playwright.config.js');
    const sandbox = {process, __dirname: path.dirname(file), module: {exports: {}},
        require: name => name === '@playwright/test'
            ? {defineConfig: value => value, devices: {'Desktop Chrome': {}}} : require(name)};
    vm.runInNewContext(fs.readFileSync(file, 'utf8'), sandbox);
    return sandbox.module.exports;
}
const config = configuration();
const child = spawnSync(process.execPath, ['-e', configuration.toString() +
    '; const c = configuration(); console.log(JSON.stringify([c.use.baseURL, c.webServer.url]));'],
    {cwd: process.cwd(), env: process.env, encoding: 'utf8'});
if (child.status) throw new Error(child.stderr);
console.log(JSON.stringify({parent: [config.use.baseURL, config.webServer.url], child: JSON.parse(child.stdout)}));'''
        env = {key: value for key, value in os.environ.items()
               if not key.startswith('TUXEDO_PREVIEW_TEST_')}
        result = subprocess.run(['node', '-e', script], cwd=ROOT, env=env,
                                capture_output=True, text=True, check=True, timeout=15)
        endpoints = json.loads(result.stdout)
        self.assertEqual(endpoints['parent'], endpoints['child'])

    def test_capture_keeps_its_automatically_allocated_socket_bound(self):
        app = lambda environ, start: []
        modules = {
            'django.contrib.staticfiles.handlers': SimpleNamespace(StaticFilesHandler=lambda application: application),
            'django.core.wsgi': SimpleNamespace(get_wsgi_application=lambda: app),
        }
        with tempfile.TemporaryDirectory(prefix='tuxedo-preview-data.') as directory:
            env = {'PREVIEW_CAPTURE': '1', 'TUXEDO_DATA_DIR': directory, 'TUXEDO_ENV_FILE': os.devnull}
            with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, modules):
                with serve.capture_server() as server:
                    self.assertEqual(server.server_address[0], '127.0.0.1')
                    self.assertGreater(server.server_port, 0)
                    with socket.socket() as competitor:
                        with self.assertRaises(OSError):
                            competitor.bind(server.server_address)

    def test_capture_rejects_workspace_or_unmarked_storage_before_loading_django(self):
        for directory, flag, environment in [
            (ROOT, '1', os.devnull),
            (ROOT / 'tuxedo-preview-data.fixture', '1', os.devnull),
            ('/tmp/tuxedo-preview-data.fixture', '', os.devnull),
            ('/tmp/tuxedo-preview-data.fixture', '1', '/owner/private-config'),
        ]:
            with self.subTest(directory=directory, flag=flag, environment=environment):
                with patch.dict(os.environ, {'TUXEDO_DATA_DIR': str(directory), 'PREVIEW_CAPTURE': flag,
                                             'TUXEDO_ENV_FILE': environment}, clear=True):
                    with self.assertRaises(RuntimeError):
                        serve.capture_server()

    def test_static_readiness_identifies_this_run_and_still_serves_the_tour(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'index.html').write_text('Synthetic static tour')
            handler = partial(serve.StaticPreviewHandler, directory=directory, ready_token='this-run-only')
            with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                opener = build_opener(ProxyHandler({}))
                url = f'http://127.0.0.1:{server.server_port}'
                try:
                    with redirect_stderr(StringIO()):
                        with opener.open(url + '/__preview_ready__/this-run-only') as response:
                            self.assertEqual(response.read(), b'Owned static preview server')
                        with self.assertRaises(HTTPError):
                            opener.open(url + '/__preview_ready__/another-run')
                        with opener.open(url + '/') as response:
                            self.assertEqual(response.read(), b'Synthetic static tour')
                finally:
                    server.shutdown()
                    thread.join(timeout=2)

    def test_bind_failure_cannot_publish_another_servers_ready_file(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            ready = Path(directory, 'ready')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/preview/serve.py'), '--static',
                                     '--port', str(occupied.getsockname()[1]), '--ready-file', str(ready)],
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(ready.exists())


UV = '''import http.server, json, os, pathlib, sys
root = pathlib.Path.cwd()
args = sys.argv[1:]
if args[:3] == ['run', 'python', '-c']:
    os.execv(sys.executable, [sys.executable, '-c', args[3]])
assert os.environ['ASSISTANT_OPENAI_AUTH_ENABLED'] == 'False'
assert os.environ['ASSISTANT_OPENAI_INFERENCE_ENABLED'] == 'False'
assert pathlib.Path(os.environ['ASSISTANT_PRIVATE_DIR']).parent == pathlib.Path(os.environ['TUXEDO_DATA_DIR'])
assert 'ASSISTANT_OPENAI_CLIENT_ID' not in os.environ
if 'scripts/preview/serve.py' in args:
    if os.environ['FIXTURE_MODE'] == 'startup-failure': sys.exit(6)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Owned fixture')
        def log_message(self, *args): pass
    with http.server.HTTPServer(('127.0.0.1', 0), Handler) as server:
        pathlib.Path(os.environ['FIXTURE_EVENTS']).write_text(json.dumps({
            'pid': os.getpid(), 'data': os.environ['TUXEDO_DATA_DIR'],
            'stage': os.environ['PREVIEW_OUTPUT_DIR']}))
        pathlib.Path(args[args.index('--ready-file') + 1]).write_text(
            'http://127.0.0.1:' + str(server.server_port))
        server.serve_forever()
'''

NODE = '''import os, pathlib, sys
pathlib.Path('node-invoked').touch()
if os.environ['FIXTURE_MODE'] == 'capture-failure': sys.exit(9)
for language in ['en', 'pt-br']:
    target = pathlib.Path(os.environ['PREVIEW_OUTPUT_DIR'], language)
    target.mkdir()
    for area in ['dashboard', 'reports', 'analytics-investments', 'transactions', 'new-entry', 'banking', 'investments', 'planning']:
        for theme in ['light', 'dark']:
            if os.environ['FIXTURE_MODE'] == 'missing-entry' and language == 'pt-br' and area == 'new-entry' and theme == 'dark':
                continue
            (target / (area + '-' + theme + '.png')).write_bytes(b'staged fixture image')
'''


class PreviewCaptureCleanupTests(TestCase):
    def run_capture(self, mode):
        with tempfile.TemporaryDirectory(prefix='tuxedo-preview-tooling-') as directory:
            root = Path(directory)
            script = root / 'scripts/preview/capture_preview.sh'
            script.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/preview/capture_preview.sh', script)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            for name, source in [('uv', UV), ('node', NODE),
                                 ('file', "print('PNG image data, 1440 x 1000')")]:
                tool = bin_dir / name
                tool.write_text(f'#!{sys.executable}\n{source}\n')
                tool.chmod(0o700)
            runtime = root / 'temporary'
            runtime.mkdir()
            image = root / 'preview/images/en/dashboard-light.png'
            image.parent.mkdir(parents=True)
            image.write_bytes(b'original fixture image')
            database = root / 'db.sqlite3'
            database.write_bytes(b'unchanged fixture database')
            config = root / '.env'
            config.write_text('fixture-only-preserved')
            events = root / 'events.json'
            env = {'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}', 'TMPDIR': str(runtime),
                   'FIXTURE_MODE': mode, 'FIXTURE_EVENTS': str(events),
                   'ASSISTANT_OPENAI_AUTH_ENABLED': 'True', 'ASSISTANT_OPENAI_INFERENCE_ENABLED': 'True',
                   'ASSISTANT_PRIVATE_DIR': '/owner/private-vault', 'ASSISTANT_OPENAI_CLIENT_ID': 'fixture-only'}
            result = subprocess.run(['bash', str(script)], cwd=root, env=env,
                                    capture_output=True, timeout=20)
            self.assertEqual(database.read_bytes(), b'unchanged fixture database')
            self.assertEqual(config.read_text(), 'fixture-only-preserved')
            self.assertEqual(list(runtime.iterdir()), [])
            if events.exists():
                event = json.loads(events.read_text())
                self.assertFalse(Path(event['data']).exists())
                self.assertFalse(Path(event['stage']).exists())
                with self.assertRaises(ProcessLookupError):
                    os.kill(event['pid'], 0)
            if mode == 'success':
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(len(list((root / 'preview/images').rglob('*.png'))), 32)
                self.assertEqual(image.read_bytes(), b'staged fixture image')
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(image.read_bytes(), b'original fixture image')
                self.assertEqual((root / 'node-invoked').exists(), mode in {'capture-failure', 'missing-entry'})

    def test_success_disposes_its_server_and_temporaries_after_staging(self):
        self.run_capture('success')

    def test_capture_failure_keeps_published_images_and_disposes_its_server(self):
        for mode in ['capture-failure', 'missing-entry']:
            with self.subTest(mode=mode):
                self.run_capture(mode)

    def test_startup_failure_cannot_invoke_capture_or_replace_images(self):
        self.run_capture('startup-failure')
