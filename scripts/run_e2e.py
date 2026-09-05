#!/usr/bin/env python3
"""Run browser tests against a disposable local Django installation.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parent.parent


class Interrupted(Exception):
    def __init__(self, signum):
        self.signum = signum


def interrupt(signum, frame):
    raise Interrupted(signum)


def stop(process):
    """Stop the command and its descendants, including browser processes."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def wait_for_server(server, url, timeout=30):
    # Ignore proxy settings: this request must reach our loopback server.
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError('The isolated Django server exited during startup.')
        try:
            with opener.open(url, timeout=1) as response:
                ready = response.status == 200
        except (URLError, TimeoutError, ConnectionError):
            ready = False
        # Also detect a bind failure if another process acquired this port.
        time.sleep(0.1)
        if server.poll() is not None:
            raise RuntimeError('The isolated Django server exited during startup.')
        if ready:
            return
    raise RuntimeError('The isolated Django server did not become ready within 30 seconds.')


def run(args):
    if os.name != 'posix':
        raise RuntimeError('The isolated runner requires Linux, macOS, or WSL.')
    node = shutil.which('node')
    cli = ROOT / 'node_modules/@playwright/test/cli.js'
    if not node or not cli.is_file():
        raise RuntimeError('Install Node.js and run `npm ci` before browser tests.')

    with tempfile.TemporaryDirectory(prefix='tuxedo-e2e-') as directory:
        data_dir = Path(directory)
        env_file = data_dir / '.env'
        env_file.touch()
        with socket.socket() as address:
            address.bind(('127.0.0.1', 0))
            port = address.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        env = dict(
            os.environ,
            DJANGO_SETTINGS_MODULE='core.settings',
            TUXEDO_ENV_FILE=str(env_file),
            TUXEDO_DATA_DIR=directory,
            SECRET_KEY=secrets.token_urlsafe(48),
            DEBUG='True',
            HTTPS='False',
            ALLOWED_HOSTS='127.0.0.1',
            ALLOW_SIGNUPS='True',
            LOG_LEVEL='WARNING',
            E2E_BASE_URL=url,
            PYTHONUNBUFFERED='1',
        )
        processes = []
        log_path = data_dir / 'server.log'
        print(f'Running browser tests on an isolated server at {url}', flush=True)
        with log_path.open('w') as log:
            def start(command, **kwargs):
                process = subprocess.Popen(
                    command, cwd=ROOT, env=env, start_new_session=True, **kwargs,
                )
                processes.append(process)
                return process

            try:
                migration = start(
                    [sys.executable, 'manage.py', 'migrate', '--noinput'],
                    stdout=log, stderr=subprocess.STDOUT,
                )
                result = migration.wait()
                if result:
                    raise RuntimeError(f'Isolated database migration failed (exit {result}).')
                server = start(
                    [sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
                    stdout=log, stderr=subprocess.STDOUT,
                )
                wait_for_server(server, url)
                return start([node, str(cli), 'test', *args]).wait()
            finally:
                # Repeated Ctrl-C must not interrupt disposal of private test data.
                previous = {
                    sig: signal.signal(sig, signal.SIG_IGN)
                    for sig in (signal.SIGINT, signal.SIGTERM)
                }
                try:
                    for process in reversed(processes):
                        stop(process)
                    log.flush()
                    destination = ROOT / 'test-results/e2e-server.log'
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(log_path, destination)
                    print(f'Isolated server log: {destination}', flush=True)
                finally:
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)


def main():
    previous = {
        sig: signal.signal(sig, interrupt)
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        result = run(sys.argv[1:])
        return result if result >= 0 else 128 - result
    except Interrupted as exc:
        return 128 + exc.signum
    except (OSError, RuntimeError) as exc:
        print(f'Browser tests failed: {exc}', file=sys.stderr)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
