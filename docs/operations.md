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

The application version is the `[project].version` value in `pyproject.toml`.
Print and validate it together with the lockfile, README and changelog using:

```bash
uv run python scripts/check_version.py
```

See [versioning.md](versioning.md) for the Semantic Versioning and release-tag
workflow.

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

## Continuous integration

The supported local Python path is reproduced by `.github/workflows/ci.yml` on
pushes and pull requests. CI installs the exact `uv.lock` set, then runs Django
system checks, missing-migration checks, the full test suite with branch
coverage, translation compilation, Ruff lint, a `pip-audit` scan of the locked
Python runtime requirements, and an `npm audit` gate for high-severity issues in
the pinned frontend tooling. Coverage XML and HTML reports are retained as
workflow artifacts. CI enforces the documented 70% line-coverage floor; the
policy is documented in [coverage-baseline.md](coverage-baseline.md).

## SQLite backup

Before upgrades or other risky maintenance, stop `runserver` (and any other
process that writes to the database) and record the application version and
current migration state. Store backups outside the checkout, with restrictive
permissions:

```bash
mkdir -p "$HOME/tuxedo-finance-backups"
chmod 700 "$HOME/tuxedo-finance-backups"
uv run python manage.py showmigrations > /tmp/tuxedo-finance-migrations.txt
sqlite3 db.sqlite3 ".backup '$HOME/tuxedo-finance-backups/tuxedo-finance-$(date +%Y%m%d-%H%M%S).sqlite3'"
chmod 600 "$HOME/tuxedo-finance-backups"/*.sqlite3
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
cp db.sqlite3 "$HOME/tuxedo-finance-backups/before-restore-$(date +%Y%m%d-%H%M%S).sqlite3"
rm -f db.sqlite3-wal db.sqlite3-shm
cp "$HOME/tuxedo-finance-backups/tuxedo-finance-YYYYMMDD-HHMMSS.sqlite3" db.sqlite3
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

The following isolated restore rehearsal was completed before release:

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

No installation owner's working database was used as the rehearsal source. A
live database must be backed up before upgrading and validated separately rather
than treated as a clean fixture.

Future rehearsals should record the same details. A rehearsal must not overwrite
the owner’s live database.
