#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Run Playwright against a server and database owned by this invocation."""
import argparse
from contextlib import contextmanager
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
import urllib.error
import urllib.request

from docker_smoke import Installation, isolated_environment

ROOT = Path(__file__).resolve().parent.parent


def stop_process(process):
    """Stop the owned process group, including uv/npm/browser children."""
    try:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


@contextmanager
def native_server():
    with tempfile.TemporaryDirectory(prefix='tuxedo-e2e-') as directory:
        env = isolated_environment()
        env.update(TUXEDO_DATA_DIR=directory, TUXEDO_ENV_FILE=os.devnull,
                   SECRET_KEY=secrets.token_urlsafe(64), DEBUG='True', HTTPS='False',
                   ALLOWED_HOSTS='localhost,127.0.0.1', ALLOW_SIGNUPS='True')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        log_path = Path(directory) / 'server.log'
        output_log = ROOT / 'test-results' / 'e2e-server.log'
        process = None
        try:
            with log_path.open('w') as log:
                subprocess.run(['uv', 'run', 'python', 'manage.py', 'migrate', '--noinput'],
                               cwd=ROOT, env=env, stdout=log, stderr=log, check=True)
                process = subprocess.Popen(
                    ['uv', 'run', 'python', 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
                    cwd=ROOT, env=env, stdout=log, stderr=log,
                    start_new_session=(os.name == 'posix'),
                )
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError(f'Server exited; see {output_log}')
                    try:
                        with opener.open(url, timeout=1) as response:
                            if response.status == 200:
                                break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.25)
                else:
                    raise RuntimeError(f'Server not ready; see {output_log}')
                yield url
        finally:
            if process is not None:
                stop_process(process)
            output_log.parent.mkdir(exist_ok=True)
            shutil.copyfile(log_path, output_log)


@contextmanager
def docker_server(image):
    with Installation(image) as app:
        app.start()
        yield app.url


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--docker-image')
    args, playwright_args = parser.parse_known_args()
    if playwright_args[:1] == ['--']:
        playwright_args = playwright_args[1:]
    server = docker_server(args.docker_image) if args.docker_image else native_server()
    with server as url:
        env = isolated_environment()
        env['E2E_BASE_URL'] = url
        process = subprocess.Popen([shutil.which('npx'), 'playwright', 'test', *playwright_args],
                                   cwd=ROOT, env=env, start_new_session=(os.name == 'posix'))
        try:
            return process.wait()
        finally:
            if process.poll() is None:
                stop_process(process)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    raise SystemExit(main())
