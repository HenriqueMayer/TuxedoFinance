#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Exercise a Docker image using only disposable Compose installations."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import sys
import subprocess
import tempfile
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent


def isolated_environment():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('COMPOSE_', 'TUXEDO_', 'E2E_')) or key in {
            'SECRET_KEY', 'DEBUG', 'HTTPS', 'ALLOWED_HOSTS', 'ALLOW_SIGNUPS', 'LOG_LEVEL',
            'DJANGO_SETTINGS_MODULE',
        }:
            del env[key]
    return env


class Installation:
    """Own the configuration, volume and port; never accept an existing target."""

    def __init__(self, image):
        self.image = image
        self.project = 'tuxedo-test-' + uuid.uuid4().hex[:12]
        self.directory = None

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='tuxedo-docker-test-')
        directory = Path(self.directory.name)
        shutil.copyfile(ROOT / 'compose.yaml', directory / 'compose.yaml')
        env_file = directory / '.env'
        env_file.write_text(
            f'TUXEDO_IMAGE={self.image}\nSECRET_KEY={secrets.token_urlsafe(64)}\n'
            'TUXEDO_PORT=0\nALLOW_SIGNUPS=True\n'
        )
        env_file.chmod(0o600)
        self.command = [
            'docker', 'compose', '--project-name', self.project,
            '--project-directory', str(directory), '--env-file', str(env_file),
            '-f', str(directory / 'compose.yaml'),
        ]
        return self

    def compose(self, *args, check=True, input=None):
        return subprocess.run(
            [*self.command, *args], env=isolated_environment(),
            input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check,
        )

    def start(self, recreate=False):
        args = ['up', '-d', '--wait', '--wait-timeout', '120', '--pull', 'never']
        if recreate:
            args.append('--force-recreate')
        self.compose(*args)
        binding = self.compose('port', 'web', '8000').stdout.decode().strip()
        assert binding.startswith('127.0.0.1:'), binding
        self.url = 'http://' + binding

    def python(self, code):
        return self.compose('exec', '-T', 'web', 'python', '-c', code).stdout

    def django(self, code):
        return self.compose('exec', '-T', 'web', 'python', 'manage.py', 'shell', '-c', code).stdout

    def __exit__(self, exc_type, exc, traceback):
        try:
            log = self.compose('logs', '--no-color', check=False)
            output = ROOT / 'test-results'
            output.mkdir(exist_ok=True)
            (output / f'{self.project}.log').write_bytes(log.stdout + log.stderr)
            self.compose('down', '--volumes', '--remove-orphans')
        finally:
            self.directory.cleanup()


def verify(image, previous_image=None):
    with Installation(previous_image or image) as app:
        print('Checking configuration failures and command overrides.', flush=True)
        for key in ('', 'replace-with-a-generated-secret-key'):
            result = app.compose('run', '--rm', '-T', '-e', f'SECRET_KEY={key}', 'web', check=False)
            assert result.returncode != 0 and b'SECRET_KEY must be' in result.stderr
        result = app.compose('run', '--rm', '-T', '-e', 'TUXEDO_DATA_DIR=/app', 'web', check=False)
        assert result.returncode != 0 and b'must exist and be writable' in result.stderr
        app.compose('run', '--rm', '-T', 'web', 'python', '-c',
                    "from pathlib import Path; assert not Path('/data/db.sqlite3').exists()")
        app.start()
        print('Checking non-root runtime, assets, headers and translations.', flush=True)
        app.python("""
import importlib.util, os
from pathlib import Path
assert os.getuid() == 10001
assert not Path('/app/.env').exists()
assert not Path('/app/db.sqlite3').exists()
assert not Path('/app/.git').exists()
assert not Path('/app/node_modules').exists()
assert importlib.util.find_spec('coverage') is None
assert Path('/data/db.sqlite3').stat().st_mode & 0o077 == 0
""")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path, content_type in (
            ('/', 'text/html'), ('/static/css/app.css', 'text/css'),
            ('/static/js/vendor/htmx.min.js', 'text/javascript'),
            ('/static/admin/css/base.css', 'text/css'),
        ):
            with opener.open(app.url + path, timeout=10) as response:
                assert response.status == 200
                assert content_type in response.headers['Content-Type']
                assert "default-src 'self'" in response.headers['Content-Security-Policy']
                assert response.read()
        request = urllib.request.Request(app.url, headers={'Accept-Language': 'pt-br'})
        with opener.open(request, timeout=10) as response:
            assert response.headers['Content-Language'] == 'pt-br'
            assert 'Criar conta' in response.read().decode()
        app.django("""
from django.contrib.auth import get_user_model
from banking.models import Bank, BankAccount
user = get_user_model().objects.create_user(username='docker-persistence')
bank = Bank.objects.create(user=user, name='Disposable bank')
BankAccount.objects.create(user=user, bank=bank, name='Rehearsal', currency='BRL', opening_balance='123.45')
""")
        check_record = """
from decimal import Decimal
from banking.models import BankAccount
assert BankAccount.objects.get(user__username='docker-persistence').opening_balance == Decimal('123.45')
"""
        print('Checking recreation, backup, restore and idempotent migrations.', flush=True)
        # Upgrade the same disposable volume to the candidate image when supplied.
        if previous_image:
            env_file = Path(app.directory.name) / '.env'
            env_file.write_text(env_file.read_text().replace(
                f'TUXEDO_IMAGE={previous_image}\n', f'TUXEDO_IMAGE={image}\n',
            ))
        # A valid Django wildcard must not make the HTTP health probe fail.
        env_file = Path(app.directory.name) / '.env'
        with env_file.open('a') as config:
            config.write('ALLOWED_HOSTS=.example.test\n')
        app.start(recreate=True)
        request = urllib.request.Request(app.url, headers={'Host': 'finance.example.test'})
        with opener.open(request, timeout=10) as response:
            assert response.status == 200
        app.django(check_record)
        app.compose('stop', 'web')
        app.compose('run', '--rm', '-T', 'web', 'python', 'scripts/sqlite_backup.py',
                    '/data/db.sqlite3', '/data/rehearsal.sqlite3')
        duplicate = app.compose('run', '--rm', '-T', 'web', 'python', 'scripts/sqlite_backup.py',
                                '/data/db.sqlite3', '/data/rehearsal.sqlite3', check=False)
        assert duplicate.returncode != 0
        exported = Path(app.directory.name) / 'rehearsal.sqlite3'
        app.compose('cp', 'web:/data/rehearsal.sqlite3', str(exported))
        snapshot = exported.read_bytes()
        with Installation(image) as restored:
            restored.compose('run', '--rm', '-T', 'web', 'python',
                             'scripts/sqlite_backup.py', '-', '/data/db.sqlite3', input=snapshot)
            restored.start()
            restored.django(check_record)
            restored.compose('exec', '-T', 'web', 'python', 'manage.py', 'migrate', '--check')
        container = app.compose('ps', '-aq', 'web').stdout.decode().strip()
        state = json.loads(subprocess.check_output(['docker', 'inspect', container]))[0]['State']
        assert state['ExitCode'] == 0, state
        # A check in a fresh one-off container must fail when no HTTP process exists.
        failed = app.compose('run', '--rm', '-T', 'web', 'python', 'scripts/docker_healthcheck.py', check=False)
        assert failed.returncode != 0
    print('Docker lifecycle smoke checks passed.', flush=True)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--previous-image', help='Rehearse an upgrade from this compatible image')
    args = parser.parse_args()
    try:
        verify(args.image, args.previous_image)
    except subprocess.CalledProcessError as error:
        print((error.stdout or b'').decode(), (error.stderr or b'').decode())
        raise SystemExit(error.returncode) from None
