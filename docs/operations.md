# Operations

Tuxedo Finance 2.0 has a new database schema. There is no upgrade from 1.x:
a 2.0 installation starts with an empty database.

## Settings

Settings come from the environment, or from the file named by
`TUXEDO_ENV_FILE` (default: `backend/.env`). A process variable wins over the
file.

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | none, required | Signs sessions. Generate once and keep it |
| `DEBUG` | `False` | `True` shows error pages and serves a new client build without a restart |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Host names that the server answers |
| `ALLOW_SIGNUPS` | `True` | `False` closes registration |
| `HTTPS` | `False` | `True` when a TLS proxy serves the installation: secure cookies, redirect, HSTS |
| `TUXEDO_TIME_ZONE` | `America/Sao_Paulo` | The financial time zone: it decides which day is today |
| `TUXEDO_DATA_DIR` | `backend/var` | Folder of the database |
| `TUXEDO_CLIENT_DIR` | `web/dist` | Folder of the built client |
| `TUXEDO_AUTH_THROTTLE` | `10/m` | Attempts to sign in or sign up for each address |
| `LOG_LEVEL` | `INFO` | Level of the console log |

Generate a key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## Data

All data is in one SQLite file: `db.sqlite3` in the data directory. It uses
WAL mode, so two more files (`-wal`, `-shm`) can exist beside it.

Back up with the SQLite backup command, which is safe while the server runs:

```bash
sqlite3 /path/to/db.sqlite3 ".backup '/path/to/backup.sqlite3'"
```

To restore, stop the server, replace `db.sqlite3` with the backup, remove the
`-wal` and `-shm` files, and start the server.

Keep `SECRET_KEY` with the backup. Without it, open sessions end; the data is
not affected.

## Docker

```bash
docker build -t tuxedo-finance:local .
cp .env.docker.example .env      # set TUXEDO_IMAGE and SECRET_KEY
docker compose up -d
```

The container applies migrations when it starts and serves on port 8000,
published on `127.0.0.1` only. `TUXEDO_PORT` in `.env` changes the published
port. The database is in the `data` volume.

A release publishes the image as `ghcr.io/henriquemayer/tuxedofinance` with
the tag of the release (for example `v2.0.0`). There is no `latest` tag. The
release also has `compose.yaml` and `docker.env.example` as files, so an
installation needs no checkout: set `TUXEDO_IMAGE` to the released image.

The Docker workflow builds the image, starts it, asks for its health, reads
the client from it and restarts it.

## Repair

`python manage.py reconcile_ledger` derives account movements and invoices
again from the recorded entries. Use it after a direct database edit.
`--user` with a username does it for one owner.

## Release

A release is a tag on `main` and a GitHub release of that tag.

1. Set the version in `backend/pyproject.toml` (for example `2.0.0`) and give
   the entry of the [changelog](../CHANGELOG.md) that version and its date.
2. Merge to `main`. The workflows of the backend, the client and the public
   site run. The public site is published from `main`.
3. Tag the merge commit `v` plus the version (`v2.0.0`) and publish a GitHub
   release of the tag. The Docker workflow checks that the tag names the
   version and is on `main`, builds the image for both architectures and
   starts it. For a release that is not a prerelease, it then pushes the
   tested images and attaches the installation files.

The repository setting "Pages, Source" must be "GitHub Actions" for the
public site.

