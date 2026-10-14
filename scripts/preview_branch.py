#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Run this branch against a disposable SQLite copy, leaving the source intact."""
import argparse
import ipaddress
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
from scripts.sqlite_backup import copy_database


def private_preview_host(value):
    """LAN exposure is explicit and limited to one private IPv4 interface."""
    if value == 'localhost':
        return value
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise argparse.ArgumentTypeError('Use localhost, a loopback IPv4 address, or your private LAN IPv4 address.') from error
    private_networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
    if not address.is_loopback and not any(address in ipaddress.IPv4Network(network) for network in private_networks):
        raise argparse.ArgumentTypeError('The preview must bind to loopback or one private LAN address, never all interfaces or a public address.')
    return str(address)


def preview_environment(directory, inherited=None, *, bind_host='127.0.0.1'):
    bind_host = private_preview_host(bind_host)
    allowed_hosts = 'localhost,127.0.0.1'
    if bind_host not in {'localhost', '127.0.0.1'}:
        allowed_hosts += f',{bind_host}'
    return {**(os.environ if inherited is None else inherited),
            'TUXEDO_DATA_DIR': str(Path(directory).resolve()), 'TUXEDO_ENV_FILE': os.devnull,
            'DJANGO_SETTINGS_MODULE': 'core.settings',
            'SECRET_KEY': secrets.token_urlsafe(48), 'DEBUG': 'True', 'HTTPS': 'False',
            'ALLOWED_HOSTS': allowed_hosts, 'ALLOW_SIGNUPS': 'False'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-database', type=Path, help='Defaults to the installation configured by TUXEDO_DATA_DIR/.env.')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--bind', type=private_preview_host, default='127.0.0.1', help='Default: loopback only. To test a phone on a trusted LAN, explicitly supply this computer\'s private IPv4 address.')
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error('Choose an unprivileged loopback port between 1024 and 65535.')
    configured = dotenv_values(os.environ.get('TUXEDO_ENV_FILE', ROOT / '.env'))
    source = args.source_database or Path(os.environ.get('TUXEDO_DATA_DIR', configured.get('TUXEDO_DATA_DIR') or ROOT)) / 'db.sqlite3'
    source = source.resolve()
    if not source.is_file():
        parser.error('Source database does not exist. Pass --source-database explicitly.')
    with tempfile.TemporaryDirectory(prefix='tuxedo-manual-preview-') as directory:
        copy_database(source, Path(directory) / 'db.sqlite3')
        env = preview_environment(directory, bind_host=args.bind)
        print('Verified disposable copy created. Only this copy will be migrated.', flush=True)
        migrate = subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env)
        if migrate.returncode:
            return migrate.returncode
        print(f'Preview: http://{args.bind}:{args.port}/ — sign in with your existing user.', flush=True)
        if not args.bind.startswith('127.') and args.bind != 'localhost':
            print('LAN preview uses HTTP. Use only your trusted private network; signups remain disabled. Stop it after testing.', flush=True)
        print('Changes made here are discarded on exit. The installation database is untouched.', flush=True)
        try:
            return subprocess.run([sys.executable, 'manage.py', 'runserver', f'{args.bind}:{args.port}', '--noreload'], cwd=ROOT, env=env).returncode
        except KeyboardInterrupt:
            return 0


if __name__ == '__main__':
    raise SystemExit(main())
