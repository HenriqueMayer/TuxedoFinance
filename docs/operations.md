# Local operations

Tuxedo Finance is a single-instance Django application backed by an owner-managed
SQLite database. The database is runtime data, is ignored by Git, and must not
be copied into source control or a public issue. Each installation owner chooses
the location, retention period, and encryption policy for backups.

## Updating dependencies

Dependencies are resolved from `pyproject.toml` and locked in `uv.lock`.
Install the exact lockfile set with:

```bash
uv sync --locked
```

To review an update, change the compatible range in `pyproject.toml`, regenerate
the lockfile, and run the release notes and validation checks before deploying:

```bash
uv lock
uv sync --locked
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
uv run python manage.py compilemessages
```

Keep the previous lockfile and application version available until the new
version has passed its database rehearsal. Widen a range only after reviewing
the dependency's release notes and compatibility policy.

## Optional Docker packaging

The native `uv` + `manage.py runserver` workflow remains the primary supported
path. Docker is a convenience for a local single-instance installation and
uses the same SQLite schema and automatic startup migrations:

```bash
export SECRET_KEY="$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
docker compose up --build
docker compose ps
```

The image runs as the unprivileged `cashflow` user. Its `/data` directory is
mounted to the named `cashflow_data` volume, and `CASHFLOW_DATA_DIR` points
there so the database survives container replacement. The compose healthcheck
performs a local HTTP request to `/`; it is operational visibility only and
is not a production readiness or replica-orchestration contract.

The image is intended for Linux `amd64` and `arm64` hosts supported by the
upstream Python base image. Other CPU architectures require an explicit local
build and smoke test. No database, demo credentials, personal data, or backup
is included in the image. Docker does not add TLS termination, horizontal
scaling, a separate database, or automated backups; do not expose this
single-instance SQLite service directly to the public internet.

To stop the service while retaining data, run `docker compose down` (without
`-v`). Removing the named volume is destructive and should only happen after
an independently verified backup. Back up the SQLite file while the
application is stopped, using the host path of the named volume or a temporary
helper container. Keep backup files outside the checkout, restrict their
permissions, encrypt sensitive records, and validate them with
`PRAGMA integrity_check;` before relying on them. The restore, WAL, retention
and rehearsal rules below apply unchanged to Docker volumes.

With the application stopped, copy the database out of the named volume:

```bash
docker compose down
mkdir -p "$HOME/cashflow-backups"
chmod 700 "$HOME/cashflow-backups"
docker run --rm --user "$(id -u):$(id -g)" \
  -v cashflow_data:/data:ro -v "$HOME/cashflow-backups:/backup" \
  python:3.12-slim-bookworm sh -c \
  'cp /data/db.sqlite3 /backup/cashflow-docker.sqlite3 && chmod 600 /backup/cashflow-docker.sqlite3'
sqlite3 "$HOME/cashflow-backups/cashflow-docker.sqlite3" 'PRAGMA integrity_check;'
```

Restore only from a verified backup while the application remains stopped:

```bash
docker run --rm -v cashflow_data:/data -v "$HOME/cashflow-backups:/backup:ro" \
  python:3.12-slim-bookworm sh -c \
  'cp /backup/cashflow-docker.sqlite3 /data/db.sqlite3 && rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm && chown 10001:10001 /data/db.sqlite3 && chmod 600 /data/db.sqlite3'
docker compose up
```

Review and obtain the helper image before relying on this procedure. After
startup, inspect migration output and repeat the integrity and application
smoke checks below.

## Continuous integration

The supported local Python path is reproduced by `.github/workflows/ci.yml` on
pushes and pull requests. CI installs the exact `uv.lock` set, then runs Django
system checks, missing-migration checks, the full test suite with branch
coverage, translation compilation, Ruff lint, and a `pip-audit` scan of the
locked runtime requirements. Coverage XML and HTML reports are retained as
workflow artifacts. CI enforces the documented 70% line-coverage floor;
the policy is documented in [coverage-baseline.md](coverage-baseline.md).

## SQLite backup

Before upgrades or other risky maintenance, stop `runserver` (and any other
process that writes to the database) and record the application version and
current migration state. Store backups outside the checkout, with restrictive
permissions:

```bash
mkdir -p "$HOME/cashflow-backups"
chmod 700 "$HOME/cashflow-backups"
uv run python manage.py showmigrations > /tmp/cashflow-migrations.txt
sqlite3 db.sqlite3 ".backup '$HOME/cashflow-backups/cashflow-$(date +%Y%m%d-%H%M%S).sqlite3'"
chmod 600 "$HOME/cashflow-backups"/*.sqlite3
```

SQLite's `.backup` command captures a consistent database and handles WAL
state. If the SQLite CLI is unavailable, copy the database only while all
writes are stopped, including its `-wal` and `-shm` companions when present.
Do not use a half-copied live file as a backup.

For sensitive records, encrypt the backup with an owner-controlled tool such as
`age` or `gpg`, and remove the unencrypted copy after verifying the encrypted
artifact. Keep at least one backup separate from the machine running Tuxedo Finance.
Choose a retention policy that matches the value and update frequency of the
records (for example, daily backups retained for 30 days plus a monthly copy).

## Restore and validation

Stop application writes before restoring. Preserve the current database as a
separate rollback copy, then restore the selected backup to the expected path:

```bash
cp db.sqlite3 "$HOME/cashflow-backups/before-restore-$(date +%Y%m%d-%H%M%S).sqlite3"
rm -f db.sqlite3-wal db.sqlite3-shm
cp "$HOME/cashflow-backups/cashflow-YYYYMMDD-HHMMSS.sqlite3" db.sqlite3
chmod 600 db.sqlite3
uv run python manage.py migrate
uv run python manage.py check
sqlite3 db.sqlite3 "PRAGMA integrity_check;"
```

The integrity check must return `ok`. Start the application only after checking
the expected migration state and signing in to verify representative balances,
transactions, invoices, and investments. Never mix a database with application
code from an incompatible release; restore the matching code and lockfile when
needed.

## Restore rehearsal record

The following isolated rehearsal was completed before declaring Phase 6.2
complete:

- Date: 2026-08-13
- Source: a clean temporary SQLite database migrated through all 29 migration
  steps, copied with SQLite's `.backup` command to a disposable temporary
  directory outside the checkout.
- Application/lockfile: current working tree and current `uv.lock`.
- Migration result: the restored copy opened successfully and remained
  migration-compatible; no application database was overwritten.
- Validation: `PRAGMA integrity_check;` returned `ok`; a marker row written to
  the source was retained after restore.
- Smoke check: the restored copy opened read-only through SQLite and its schema
  was queryable.

The repository's existing local database was not used as the rehearsal source:
it is an owner-managed working file with legacy rows and pending migrations,
so it must be backed up before upgrading and validated separately rather than
treated as a clean fixture.

Future rehearsals should record the same details. A rehearsal must not overwrite
the owner’s live database.
