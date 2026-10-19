"""Exercise the runner lifecycle using real disposable subprocesses.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from scripts import run_e2e


ROOT = Path(__file__).resolve().parents[2]
MANAGE = '''
import json, os, sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
root = Path.cwd()
with (root / 'events.jsonl').open('a') as stream:
    stream.write(json.dumps({'phase': sys.argv[1], 'pid': os.getpid(),
        'data': os.environ['TUXEDO_DATA_DIR'], 'url': os.environ['E2E_BASE_URL'],
        'env_file': os.environ['TUXEDO_ENV_FILE'], 'signup': os.environ['ALLOW_SIGNUPS'],
        'https': os.environ['HTTPS'], 'settings': os.environ['DJANGO_SETTINGS_MODULE'],
        'auth_enabled': os.environ['ASSISTANT_OPENAI_AUTH_ENABLED'],
        'private_dir': os.environ['ASSISTANT_PRIVATE_DIR'],
        'callback': os.environ['ASSISTANT_OPENAI_CALLBACK_URL']}) + '\\n')
assert Path(os.environ['TUXEDO_ENV_FILE']).read_text() == ''
assert Path(os.environ['TUXEDO_DATA_DIR']) != root
assert os.environ['SECRET_KEY'] != 'personal-secret'
assert os.environ['ASSISTANT_OPENAI_AUTH_ENABLED'] == 'False'
assert os.environ['ASSISTANT_OPENAI_INFERENCE_ENABLED'] == 'False'
assert Path(os.environ['ASSISTANT_PRIVATE_DIR']).parent == Path(os.environ['TUXEDO_DATA_DIR'])
assert os.environ['ASSISTANT_OPENAI_CALLBACK_URL'] == os.environ['E2E_BASE_URL'] + '/assistant/connections/callback/'
assert 'ASSISTANT_FUTURE_SECRET' not in os.environ
mode = (root / 'mode').read_text()
if sys.argv[1] == 'migrate':
    if mode == 'migration_failure':
        print('Migration failure fixture', flush=True)
        sys.exit(8)
    Path(os.environ['TUXEDO_DATA_DIR'], 'db.sqlite3').write_text('test data')
    sys.exit(0)
if mode == 'startup_failure':
    print('Startup failure fixture', flush=True)
    sys.exit(9)
host, port = sys.argv[2].split(':')
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
HTTPServer((host, int(port)), Handler).serve_forever()
'''
BROWSER = '''
import json, os, sys, time
from pathlib import Path
root = Path.cwd()
with (root / 'events.jsonl').open('a') as stream:
    stream.write(json.dumps({'phase': 'browser', 'pid': os.getpid(),
        'args': sys.argv[1:], 'data': os.environ['TUXEDO_DATA_DIR'],
        'auth_enabled': os.environ['ASSISTANT_OPENAI_AUTH_ENABLED'],
        'private_dir': os.environ['ASSISTANT_PRIVATE_DIR'],
        'callback': os.environ['ASSISTANT_OPENAI_CALLBACK_URL']}) + '\\n')
output = root / '.local/test-results/browser'
output.mkdir(parents=True, exist_ok=True)
(output / 'browser-artifact.txt').write_text('diagnostic')
mode = (root / 'mode').read_text()
if mode == 'wait':
    while True:
        time.sleep(1)
sys.exit(7 if mode == 'suite_failure' else 0)
'''


@unittest.skipUnless(os.name == 'posix', 'Runner targets Linux, macOS, and WSL')
class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='fin8-runner-test-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / 'manage.py').write_text(MANAGE)
        (self.root / 'node_modules/@playwright/test').mkdir(parents=True)
        (self.root / 'node_modules/@playwright/test/cli.js').touch()
        (self.root / 'tests').mkdir()
        (self.root / 'tests/playwright.config.js').touch()
        node = self.root / 'node'
        node.write_text(f'#!{sys.executable}\n' + BROWSER)
        node.chmod(0o755)
        (self.root / '.env').write_text('personal-secret')
        (self.root / 'db.sqlite3').write_bytes(b'personal-database')
        self.private_dir = self.root / 'personal-assistant-private'
        self.private_dir.mkdir(mode=0o700)
        (self.private_dir / 'credential.enc').write_bytes(b'preserve personal vault')
        (self.root / 'test-results').mkdir()
        (self.root / 'test-results/legacy-artifact.txt').write_text('preserve legacy output')
        self.env = dict(
            os.environ, PATH=f'{self.root}{os.pathsep}{os.environ.get("PATH", "")}',
            SECRET_KEY='personal-secret', TUXEDO_DATA_DIR=str(self.root),
            TUXEDO_ENV_FILE=str(self.root / '.env'), ALLOW_SIGNUPS='False', HTTPS='True',
            DJANGO_SETTINGS_MODULE='personal.settings', E2E_BASE_URL='http://127.0.0.1:1',
            ASSISTANT_OPENAI_AUTH_ENABLED='True', ASSISTANT_PRIVATE_DIR=str(self.private_dir),
            ASSISTANT_OPENAI_INFERENCE_ENABLED='True',
            ASSISTANT_OPENAI_CALLBACK_URL='http://127.0.0.1:9000/personal-callback/',
            ASSISTANT_FUTURE_SECRET='personal-assistant-secret',
        )

    def start(self, mode, *args):
        (self.root / 'mode').write_text(mode)
        code = (
            f'import sys; sys.path.insert(0, {str(ROOT)!r}); '
            'from scripts import run_e2e; from pathlib import Path; '
            f'run_e2e.ROOT = Path({str(self.root)!r}); '
            'sys.exit(run_e2e.main())'
        )
        process = subprocess.Popen(
            [sys.executable, '-c', code, *args], env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.addCleanup(self.dispose, process)
        return process

    def dispose(self, process):
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=10)

    def events(self):
        path = self.root / 'events.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def verify_cleanup(self, settings_module='core.settings'):
        self.assertEqual((self.root / '.env').read_text(), 'personal-secret')
        self.assertEqual((self.root / 'db.sqlite3').read_bytes(), b'personal-database')
        self.assertEqual((self.private_dir / 'credential.enc').read_bytes(), b'preserve personal vault')
        self.assertTrue((self.root / '.local/test-results/e2e-server.log').is_file())
        self.assertEqual((self.root / 'test-results/legacy-artifact.txt').read_text(), 'preserve legacy output')
        events = self.events()
        self.assertTrue(events)
        for event in events:
            self.assertEqual(Path(event['data']).parent, self.root / '.local/test-results/runtime')
            self.assertFalse(Path(event['data']).exists())
            self.assertEqual(event['auth_enabled'], 'False')
            self.assertEqual(Path(event['private_dir']), Path(event['data']) / 'assistant-private')
            self.assertNotEqual(event['private_dir'], self.env['ASSISTANT_PRIVATE_DIR'])
            self.assertTrue(event['callback'].endswith('/assistant/connections/callback/'))
            self.assertNotEqual(event['callback'], self.env['ASSISTANT_OPENAI_CALLBACK_URL'])
            with self.assertRaises(ProcessLookupError):
                os.kill(event['pid'], 0)
        migration = events[0]
        self.assertEqual(migration['signup'], 'True')
        self.assertEqual(migration['https'], 'False')
        self.assertEqual(migration['settings'], settings_module)
        self.assertNotEqual(migration['url'], self.env['E2E_BASE_URL'])
        self.assertFalse(Path(migration['env_file']).exists())

    def test_success_isolates_environment_forwards_arguments_and_keeps_artifacts(self):
        process = self.start('success', '--grep', 'dashboard with spaces')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, output)
        browser = self.events()[-1]
        self.assertEqual(browser['args'][1:], [
            'test', '--config', str(self.root / 'tests/playwright.config.js'),
            '--grep', 'dashboard with spaces',
        ])
        self.assertTrue((self.root / '.local/test-results/browser/browser-artifact.txt').is_file())
        self.verify_cleanup()

    def test_suite_failure_preserves_exit_code(self):
        process = self.start('suite_failure')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 7, output)
        self.verify_cleanup()

    def test_assistant_fixture_mode_is_explicit_and_not_forwarded_to_playwright(self):
        process = self.start('success', '--assistant-fixtures', '--grep', 'Streaming')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, output)
        self.assertNotIn('--assistant-fixtures', self.events()[-1]['args'])
        self.verify_cleanup(settings_module='tests.e2e.assistant_mock_settings')

    def test_docker_refuses_the_local_assistant_fixture_settings(self):
        with mock.patch.object(run_e2e, 'ROOT', self.root), mock.patch.object(
            run_e2e.shutil, 'which', return_value=str(self.root / 'node'),
        ), mock.patch.object(run_e2e, 'run_docker') as docker:
            with self.assertRaisesRegex(RuntimeError, 'disposable local'):
                run_e2e.run(['--docker-image', 'local:test', '--assistant-fixtures'])
        docker.assert_not_called()

    def test_startup_failure_never_runs_browser(self):
        process = self.start('startup_failure')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 1, output)
        self.assertNotIn('browser', [event['phase'] for event in self.events()])
        self.assertIn('Startup failure fixture', (self.root / '.local/test-results/e2e-server.log').read_text())
        self.verify_cleanup()

    def test_migration_failure_never_starts_server(self):
        process = self.start('migration_failure')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 1, output)
        self.assertEqual([event['phase'] for event in self.events()], ['migrate'])
        self.verify_cleanup()

    def test_interruptions_stop_server_and_browser(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig):
                (self.root / 'events.jsonl').unlink(missing_ok=True)
                process = self.start('wait')
                deadline = time.monotonic() + 10
                while not any(event['phase'] == 'browser' for event in self.events()):
                    self.assertIsNone(process.poll())
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                process.send_signal(sig)
                output, _ = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 128 + sig, output)
                self.verify_cleanup()

    def test_docker_uses_same_absolute_config_and_preserves_browser_arguments(self):
        with mock.patch.object(run_e2e, 'ROOT', self.root), mock.patch.object(
            run_e2e.shutil, 'which', return_value=str(self.root / 'node'),
        ), mock.patch.object(run_e2e, 'run_docker', return_value=7) as docker:
            result = run_e2e.run([
                '--docker-image', 'local:test', '--', '--grep', 'dashboard with spaces',
                '--output', '/tmp/explicit-browser-output',
            ])
        self.assertEqual(result, 7)
        docker.assert_called_once_with('local:test', [
            str(self.root / 'node'), str(self.root / 'node_modules/@playwright/test/cli.js'),
            'test', '--config', str(self.root / 'tests/playwright.config.js'),
            '--grep', 'dashboard with spaces', '--output', '/tmp/explicit-browser-output',
        ])

    def test_docker_browser_subprocess_discards_personal_authorization_settings(self):
        installation = mock.MagicMock()
        app = installation.__enter__.return_value
        app.url = 'http://127.0.0.1:32123'
        browser = mock.MagicMock()
        browser.wait.return_value = 0
        with mock.patch.dict(os.environ, self.env), mock.patch.object(
            run_e2e, 'Installation', return_value=installation,
        ), mock.patch.object(run_e2e.subprocess, 'Popen', return_value=browser) as start, mock.patch.object(
            run_e2e, 'stop',
        ) as stop:
            self.assertEqual(run_e2e.run_docker('local:test', ['fixture-browser']), 0)
        app.start.assert_called_once_with()
        stop.assert_called_once_with(browser)
        env = start.call_args.kwargs['env']
        self.assertEqual(env['E2E_BASE_URL'], app.url)
        self.assertEqual(env['ASSISTANT_OPENAI_AUTH_ENABLED'], 'False')
        self.assertEqual(env['ASSISTANT_OPENAI_INFERENCE_ENABLED'], 'False')
        self.assertNotIn('ASSISTANT_PRIVATE_DIR', env)
        self.assertNotIn('ASSISTANT_OPENAI_CALLBACK_URL', env)
        self.assertNotIn('ASSISTANT_FUTURE_SECRET', env)
