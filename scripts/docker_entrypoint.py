#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Start one SQLite installation; explicit commands never migrate implicitly."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    os.umask(0o077)
    command = sys.argv[1:] or ['serve']
    if command == ['serve']:
        key = os.environ.get('SECRET_KEY', '').strip()
        if len(key) < 50 or key.lower().startswith(('replace', 'change', 'build-only')):
            raise SystemExit('SECRET_KEY must be a generated persistent key of at least 50 characters.')
        directory = Path(os.environ.get('TUXEDO_DATA_DIR', '/data'))
        try:
            with tempfile.TemporaryFile(dir=directory):
                pass
        except OSError:
            raise SystemExit(f'Data directory {directory} must exist and be writable by UID {os.getuid()}.') from None
        subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], check=True)
        command = [
            'gunicorn', 'core.wsgi:application', '--bind', '0.0.0.0:8000',
            '--workers', '1', '--threads', '4', '--access-logfile', '-',
            '--error-logfile', '-', '--worker-tmp-dir', '/tmp',
            '--no-control-socket',
        ]
    os.execvp(command[0], command)


if __name__ == '__main__':
    main()
