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
        'https': os.environ['HTTPS'], 'settings': os.environ['DJANGO_SETTINGS_MODULE']}) + '\\n')
assert Path(os.environ['TUXEDO_ENV_FILE']).read_text() == ''
assert Path(os.environ['TUXEDO_DATA_DIR']) != root
assert os.environ['SECRET_KEY'] != 'personal-secret'
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
        'args': sys.argv[1:], 'data': os.environ['TUXEDO_DATA_DIR']}) + '\\n')
(root / 'test-results').mkdir(exist_ok=True)
(root / 'test-results/browser-artifact.txt').write_text('diagnostic')
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
        node = self.root / 'node'
        node.write_text(f'#!{sys.executable}\n' + BROWSER)
        node.chmod(0o755)
        (self.root / '.env').write_text('personal-secret')
        (self.root / 'db.sqlite3').write_bytes(b'personal-database')
        self.env = dict(
            os.environ, PATH=f'{self.root}{os.pathsep}{os.environ.get("PATH", "")}',
            SECRET_KEY='personal-secret', TUXEDO_DATA_DIR=str(self.root),
            TUXEDO_ENV_FILE=str(self.root / '.env'), ALLOW_SIGNUPS='False', HTTPS='True',
            DJANGO_SETTINGS_MODULE='personal.settings', E2E_BASE_URL='http://127.0.0.1:1',
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

    def verify_cleanup(self):
        self.assertEqual((self.root / '.env').read_text(), 'personal-secret')
        self.assertEqual((self.root / 'db.sqlite3').read_bytes(), b'personal-database')
        self.assertTrue((self.root / 'test-results/e2e-server.log').is_file())
        events = self.events()
        self.assertTrue(events)
        for event in events:
            self.assertFalse(Path(event['data']).exists())
            with self.assertRaises(ProcessLookupError):
                os.kill(event['pid'], 0)
        migration = events[0]
        self.assertEqual(migration['signup'], 'True')
        self.assertEqual(migration['https'], 'False')
        self.assertEqual(migration['settings'], 'core.settings')
        self.assertNotEqual(migration['url'], self.env['E2E_BASE_URL'])
        self.assertFalse(Path(migration['env_file']).exists())

    def test_success_isolates_environment_forwards_arguments_and_keeps_artifacts(self):
        process = self.start('success', '--grep', 'dashboard with spaces')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, output)
        browser = self.events()[-1]
        self.assertEqual(browser['args'][1:], ['test', '--grep', 'dashboard with spaces'])
        self.assertTrue((self.root / 'test-results/browser-artifact.txt').is_file())
        self.verify_cleanup()

    def test_suite_failure_preserves_exit_code(self):
        process = self.start('suite_failure')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 7, output)
        self.verify_cleanup()

    def test_startup_failure_never_runs_browser(self):
        process = self.start('startup_failure')
        output, _ = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 1, output)
        self.assertNotIn('browser', [event['phase'] for event in self.events()])
        self.assertIn('Startup failure fixture', (self.root / 'test-results/e2e-server.log').read_text())
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
