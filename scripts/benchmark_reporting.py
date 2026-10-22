#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Measure full Django reads and ledger sync using disposable synthetic data."""
import argparse
import json
import math
import os
from pathlib import Path
import secrets
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

if __package__:
    from .docker_smoke import isolated_environment
else:
    from docker_smoke import isolated_environment

ROOT = Path(__file__).resolve().parent.parent


def benchmark_environment(directory):
    """Never inherit an installation database, environment file or signing key."""
    return dict(isolated_environment(), TUXEDO_DATA_DIR=str(directory),
                TUXEDO_ENV_FILE=str(Path(directory) / '.env'),
                SECRET_KEY=secrets.token_urlsafe(48), DEBUG='True', HTTPS='False',
                ALLOW_SIGNUPS='False', ALLOWED_HOSTS='testserver', LOG_LEVEL='ERROR',
                DJANGO_SETTINGS_MODULE='core.settings', PYTHONDONTWRITEBYTECODE='1')


def measure(count, samples):
    """Own a fresh installation, even when called without the CLI launcher."""
    from django.conf import settings

    if settings.configured:
        raise RuntimeError('Run the benchmark in a fresh process, outside an existing Django installation.')
    with tempfile.TemporaryDirectory(prefix='tuxedo-report-benchmark-') as directory:
        (Path(directory) / '.env').touch()
        os.environ.update(benchmark_environment(directory))
        try:
            _measure(count, samples, Path(directory))
        finally:
            from django.db import connections
            connections.close_all()


def _measure(count, samples, directory):
    import platform
    import sqlite3
    import warnings
    from datetime import date, timedelta
    from decimal import Decimal

    import django
    django.setup()
    from django.conf import settings
    if Path(settings.DATABASES['default']['NAME']).resolve() != directory / 'db.sqlite3':
        raise RuntimeError('The benchmark database must belong to its disposable directory.')
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection
    from django.test import Client
    from django.utils import timezone

    from banking.models import Bank, BankAccount, BankMovement, CreditCard
    from categories.models import Category
    from transactions.models import Transaction
    from transactions.services import sync_user_ledger

    call_command('migrate', verbosity=0, interactive=False)
    today = timezone.localdate()
    start = date(today.year - 5, today.month, 1)
    span = (today - start).days + 1
    user = get_user_model().objects.create_user('synthetic-benchmark')
    bank = Bank.objects.create(user=user, name='Synthetic bank')
    account = BankAccount.objects.create(user=user, bank=bank, name='Synthetic cash', currency='BRL',
                                         opening_balance=Decimal('1000000'), opening_date=start)
    card = CreditCard.objects.create(user=user, account=account, name='Synthetic card',
                                     closing_day=20, due_day=28)
    category = Category.objects.filter(user=user).first()
    records = []
    for index in range(count):
        fixed = index < min(12, count)
        credit = not fixed and index % 10 == 0
        records.append(Transaction(user=user, title=f'Synthetic expense {index}',
                                   amount=Decimal('10.01'), transaction_type='EXPENSE', category=category,
                                   date=start if fixed else start + timedelta(days=index % span),
                                   is_fixed=fixed, installments=6 if credit else 1,
                                   payment_channel='CREDIT_CARD' if credit else 'ACCOUNT',
                                   bank_account=None if credit else account, credit_card=card if credit else None))
    Transaction.objects.bulk_create(records, batch_size=500)
    del records
    seed_start = time.perf_counter()
    sync_user_ledger(user)
    initial_sync_ms = (time.perf_counter() - seed_start) * 1000
    client = Client()
    client.force_login(user)

    def read(path):
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='No directory at: .*staticfiles/')
            response = client.get(path)
        if response.status_code != 200:
            raise RuntimeError(f'{path} returned {response.status_code}')
        return response

    def profile(operation):
        operation()  # Warm templates, Python imports and filesystem caches.
        elapsed = []
        for _ in range(samples):
            started = time.perf_counter()
            operation()
            elapsed.append((time.perf_counter() - started) * 1000)
        captured = []
        def record(execute, sql, params, many, context):
            # Client requests reset Django's DEBUG query log; an execution
            # wrapper also avoids its bounded deque dropping older entries.
            captured.append(sql.lstrip().split(None, 1)[0].upper())
            return execute(sql, params, many, context)
        with connection.execute_wrapper(record):
            operation()
        writes = sum(verb in {'INSERT', 'UPDATE', 'DELETE'} for verb in captured)
        tracemalloc.start()
        try:
            operation()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return {'samples': samples, 'median_ms': round(statistics.median(elapsed), 3),
                'p95_ms': round(sorted(elapsed)[math.ceil(samples * .95) - 1], 3),
                'queries': len(captured), 'writes': writes,
                'peak_python_mib': round(peak / 1024 ** 2, 3)}

    report = {
        'transactions': count,
        'movements': BankMovement.objects.filter(user=user).count(),
        'initial_sync_ms': round(initial_sync_ms, 3),
        'sync': profile(lambda: sync_user_ledger(user)),
        'dashboard': profile(lambda: read('/dashboard/')),
        'reports': profile(lambda: read('/analytics/')),
        'environment': {'python': platform.python_version(), 'django': django.get_version(),
                        'sqlite': sqlite3.sqlite_version, 'platform': platform.platform(),
                        'as_of': today.isoformat(), 'debug': True},
    }
    connection.close()
    print(json.dumps(report))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counts', nargs='+', type=int, default=[0, 1000, 10000])
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--output', type=Path, help='Optional JSON result; creates the parent directory if needed.')
    args = parser.parse_args(argv)
    if args.samples < 3 or any(count < 0 for count in args.counts):
        parser.error('Use at least 3 samples and nonnegative record counts.')
    reports = []
    for count in args.counts:
        print(f'Measuring {count} synthetic transactions ({args.samples} warm samples)...', file=sys.stderr, flush=True)
        worker = 'from scripts.benchmark_reporting import measure; import sys; measure(int(sys.argv[1]), int(sys.argv[2]))'
        result = subprocess.run([sys.executable, '-B', '-c', worker, str(count), str(args.samples)],
                                cwd=ROOT, env=isolated_environment(),
                                check=True, capture_output=True, text=True)
        reports.append(json.loads(result.stdout))
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
    report = {'revision': revision, 'working_tree_dirty': dirty, 'cases': reports,
              'method': 'Five years of synthetic BRL expenses: up to 12 fixed recurrences, '
                        '10% of remaining sources in six credit installments, one bank account. '
                        'Full authenticated Django test-client GETs include ledger reconciliation and template rendering. '
                        'Timing excludes seeding, initial sync, SQL capture and tracemalloc; each fixture uses a new process/database. '
                        'Memory is peak Python allocation for a separate warm call, not process RSS. '
                        'This is not an HTTP, browser, concurrency, cold-cache or production benchmark.'}
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
        print(f'Report written to {args.output}', file=sys.stderr)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
