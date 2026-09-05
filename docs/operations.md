# Local operations

Tuxedo Finance is a local Django application with an owner-managed SQLite
database. Configuration and financial data are private runtime files, excluded
from Git. The installation owner chooses backup storage, access permissions,
encryption, and retention.

## Configuration

Settings read the project-root `.env`, unless `TUXEDO_ENV_FILE` selects another
file. Process environment variables always take priority.

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Private Django signing key | Required |
| `DEBUG` | Development debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `HTTPS` | Secure cookies, redirect, HSTS, and trusted proxy HTTPS header | `False` |
| `ALLOW_SIGNUPS` | Permit new public accounts; existing login remains available | `True` |
| `TUXEDO_DATA_DIR` | Directory containing `db.sqlite3`; create the directory before use | Project root |
| `TUXEDO_ENV_FILE` | Environment file path, selected through the process environment | Project-root `.env` |
| `LOG_LEVEL` | Application log level | `INFO` |

`DEBUG` and `HTTPS` are enabled only by the exact value `True`.
`ALLOW_SIGNUPS` accepts `1`, `true`, `yes`, or `on`, ignoring case and surrounding
whitespace. Use an absolute path for an external data directory or environment
file. Changing the data directory does not move an existing database.

Generate a signing key during initial setup as shown in the README; retain it
for subsequent starts. Enable `HTTPS` only behind a correctly configured TLS
endpoint. The supported local startup command is `uv run python manage.py
runserver`; production deployment packaging is outside the current scope.

## Updating dependencies

The application version is `[project].version` in `pyproject.toml`, with the
resolved Python dependencies in `uv.lock`. The npm lockfile controls development
tools. Review upstream release notes before changing compatible dependency
ranges; then regenerate the affected lockfile and install its exact contents.

```bash
uv lock
uv sync --locked
```

Follow the complete [development checks](../CONTRIBUTING.md) and
[release workflow](versioning.md) before adopting an update. Keep the previous
code and lockfiles available until the new version passes an isolated restore
rehearsal. Review database compatibility before running migrations on an
installation with existing records.

## Locate the active database

Run operational commands from the repository root with the same process
variables used to start the application. This resolves `TUXEDO_DATA_DIR` and
`TUXEDO_ENV_FILE`, including values loaded from the selected environment file,
without opening the database:

```bash
database_path=$(uv run python -c 'from pathlib import Path; from core.settings import DATABASES; print(Path(DATABASES["default"]["NAME"]).resolve())')
backup_dir="$HOME/tuxedo-finance-backups"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
```

Use these variables in the same shell for the procedures below. Keep the backup
directory outside the checkout. Before a backup or restore, stop `runserver`
and every other process writing to this database.

## SQLite backup

Record the application version and migration state alongside the backup:

```bash
uv run python scripts/check_version.py
uv run python manage.py showmigrations
```

The Python standard library provides SQLite's backup API, including consistent
handling of WAL state. This command opens the source read-only, refuses to
overwrite an existing backup, and prints the created backup path:

```bash
uv run python - "$database_path" "$backup_dir" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
import sys

source = Path(sys.argv[1]).resolve()
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
backup = Path(sys.argv[2]) / f'tuxedo-finance-{stamp}.sqlite3'
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as database:
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(backup) as destination:
        database.backup(destination)
        if destination.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise SystemExit('Backup integrity check failed; do not use this file.')
print(backup)
PY
```

For sensitive records, encrypt the verified backup with an owner-controlled
tool such as `age` or `gpg`. Keep at least one copy on a separate device and
choose a retention policy appropriate to the data. An integrity check verifies
SQLite structure; rehearse restoration to verify expected application records.

## Restore and validation

With all writers stopped, first run the backup procedure above to preserve the
current database as a rollback copy. Select an existing, verified backup, and
restore it to the resolved active database through the SQLite backup API:

```bash
backup_file="$backup_dir/tuxedo-finance-YYYYMMDD-HHMMSS-MICROSECONDS.sqlite3"
uv run python - "$backup_file" "$database_path" <<'PY'
from pathlib import Path
import os
import sqlite3
import sys

source = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
if source == target:
    raise SystemExit('The backup and active database must be different files.')
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as backup:
    if backup.execute('PRAGMA integrity_check').fetchone() != ('ok',):
        raise SystemExit('Backup integrity check failed; restoration cancelled.')
    os.umask(0o077)
    with sqlite3.connect(target) as database:
        backup.backup(database)
        if database.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise SystemExit('Restored database integrity check failed.')
    target.chmod(0o600)
print('Restored database integrity: ok')
PY
```

Use code and lockfiles compatible with the backup's schema. Apply migrations
only when the release documents an upgrade path; the legacy reset described in
[data-model.md](data-model.md#breaking-release) is not an automatic conversion.
Then run `manage.py check`, inspect `showmigrations`, and start the application.
Verify representative balances, transactions, invoices, and investments before
resuming normal writes.

## Restore rehearsals

Rehearse on a separate temporary installation with its own `TUXEDO_DATA_DIR`.
Record the date, exact code revision and lockfile, source migration state,
backup and restore results, integrity check, and representative record checks.
Never use the active installation as the rehearsal destination.

A historical rehearsal recorded on **2026-08-13** used a clean temporary SQLite
database with 29 migration steps and a marker row. Backup, restore, and integrity
checks passed without overwriting an owner's database. The record identified
the code only as the then-current working tree; it does not establish
compatibility with later revisions or with an owner's existing data.
