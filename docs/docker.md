# Docker installation and operations

Tuxedo Finance runs as one non-root Linux container with Gunicorn, WhiteNoise
and an owner-managed SQLite volume. Docker Engine/Docker Desktop and Compose v2
or later are required. No host Python, uv or Node.js installation is needed.
The default address is <http://127.0.0.1:8000/>.

## Availability

Docker packaging is new under `Unreleased`. The existing v0.2.0 release does
not include a published container. Use a local build until a newer release
provides `compose.yaml`, `docker.env.example` and a verified GHCR image.
The release workflow tests Linux amd64 and arm64 separately before publishing.

## Build from a checkout

From the checkout containing these Docker files:

```bash
docker build -t tuxedo-finance:local .
image=tuxedo-finance:local
```

Then perform the one-time configuration below. To build through Compose after
configuration, use:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.build.yaml up -d --build --wait
```

## Install a released image without cloning

Open the [releases page](https://github.com/HenriqueMayer/TuxedoFinance/releases)
and select a release that includes Docker support. Download its `compose.yaml`
and `docker.env.example` into a new installation directory. Read the exact
`TUXEDO_IMAGE` value from that release's example and assign it below, replacing
`vX.Y.Z` with that release tag. Run commands from this directory.

```bash
image=ghcr.io/henriquemayer/tuxedofinance:vX.Y.Z
docker pull "$image"
```

Images use explicit version tags; there is no supported `latest` alias. Keep
the directory name stable because Compose uses it to identify the data volume.
Moving or renaming the directory requires preserving the original project name
with `--project-name`; otherwise Compose creates a different empty installation.

## One-time configuration and startup

The following POSIX-shell command creates `.env.docker` using the image's
Python. `noclobber` refuses to replace an existing file. If image startup fails,
inspect any incomplete file before retrying; never regenerate an existing
installation's signing key. Windows users can run these commands in WSL.

```bash
(
  umask 077
  set -o noclobber
  docker run --rm --entrypoint python -e TUXEDO_IMAGE="$image" "$image" -c \
    'import os,secrets; print("TUXEDO_IMAGE="+os.environ["TUXEDO_IMAGE"]); print("SECRET_KEY="+secrets.token_urlsafe(64))' > .env.docker
)
docker compose --env-file .env.docker up -d --wait
```

Open <http://127.0.0.1:8000/>, create an account and add a bank and account before
recording transactions. Startup applies migrations before serving requests.
No example user, password or financial data is created. Subsequent starts reuse
the same signing key and named `data` volume; no source-code bind mount is used.

Protect `.env.docker` and keep a separate secure copy. Optionally append values
from `.env.docker.example` (the release asset is named `docker.env.example`):

| Variable | Container behavior |
|---|---|
| `TUXEDO_IMAGE` | Required image reference; version tag or digest |
| `SECRET_KEY` | Required generated key, at least 50 characters; retain on upgrades |
| `TUXEDO_PORT` | Host port, default `8000`; always bound to `127.0.0.1` |
| `ALLOWED_HOSTS` | Default `localhost,127.0.0.1` |
| `ALLOW_SIGNUPS` | Default `True`; set `False` after creating the intended accounts |
| `HTTPS` | Default `False`; set `True` only with a correctly configured TLS proxy |
| `LOG_LEVEL` | Default `INFO` |

The Compose service fixes `DEBUG=False`, `TUXEDO_DATA_DIR=/data` and
`TUXEDO_ENV_FILE=/dev/null`. The native checkout's `.env` and database are not
mounted. The image uses UID/GID `10001:10001`. Named volumes are initialized with
the right ownership; existing bind mounts need deliberate ownership setup and
are not the quick-start path. SQLite's database, WAL and shared-memory files
must remain together on local storage. Use one web service, without replicas or
network filesystems. An incompatible database/migration or unwritable volume
stops startup instead of resetting data.

## Routine commands

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail=100 web
docker compose --env-file .env.docker exec web python manage.py showmigrations
docker compose --env-file .env.docker exec web python manage.py createsuperuser
docker compose --env-file .env.docker stop
docker compose --env-file .env.docker up -d --wait
```

`stop` and `down` preserve the named data volume. **`down --volumes` deletes it**
and is never part of an ordinary update. A management-command override does not
implicitly migrate or launch the server. Health checks probe HTTP locally;
`--wait` reports failed startup and logs show migration/server errors.

## Backup

Stop all database writers, including any management commands. Record the image
reference and migration state. Choose a new backup filename each time:

```bash
docker compose --env-file .env.docker exec -T web python manage.py showmigrations > migrations.txt
docker compose --env-file .env.docker stop web
docker compose --env-file .env.docker run --rm -T web python scripts/sqlite_backup.py /data/db.sqlite3 /data/backup-YYYYMMDD.sqlite3
docker compose --env-file .env.docker cp web:/data/backup-YYYYMMDD.sqlite3 ./backup-YYYYMMDD.sqlite3
chmod 600 backup-YYYYMMDD.sqlite3
docker compose --env-file .env.docker up -d --wait
```

The helper uses SQLite's backup API, checks integrity and refuses to overwrite
an existing destination. Move the host copy to protected storage outside this
installation and keep a copy on another device. Do not commit backups or copy
only a live database file while ignoring WAL. A copy inside `/data` alone does
not protect against volume loss. Retain `.env.docker` securely alongside the
backup metadata, without publishing its key.

## Restore rehearsal and recovery

Use code/image compatible with the backup schema. Restore to a new Compose
project/volume; retain the original installation as a rollback source. The name
`tuxedo-restore` below must be unused. The destination must not already contain
a database; the helper refuses to overwrite it.

```bash
docker compose --project-name tuxedo-restore --env-file .env.docker run --rm -T web python scripts/sqlite_backup.py - /data/db.sqlite3 < backup-YYYYMMDD.sqlite3
TUXEDO_PORT=8001 docker compose --project-name tuxedo-restore --env-file .env.docker up -d --wait
docker compose --project-name tuxedo-restore --env-file .env.docker exec web python manage.py check
docker compose --project-name tuxedo-restore --env-file .env.docker exec web python manage.py showmigrations
```

Open <http://127.0.0.1:8001/> and verify login, balances, transactions and
investments. Record the image, backup date, migration state and checks. Keep
using the explicit restored project name and port if promoting it to the active
installation. Never rehearse restoration over the active database.

## Update

Back up and read the release's migration notes first. Stop the web service,
change only `TUXEDO_IMAGE` in `.env.docker` to the selected release, then run:

```bash
docker compose --env-file .env.docker pull
docker compose --env-file .env.docker up -d --wait
docker compose --env-file .env.docker logs --tail=100 web
```

Keep the same volume, Compose project name and signing key. Test the candidate
image against a restored copy before upgrading valuable data. Returning to an
older image does not undo migrations; recovery may require its matching backup.
Pre-release legacy schemas still have no automatic conversion path.

## LAN and TLS

The default port is reachable only from the Docker host. Remote access requires
an explicit Compose port override, matching allowed hosts and access controls.
For TLS, use a trusted reverse proxy, forward the original Host and overwrite
`X-Forwarded-Proto` correctly before enabling `HTTPS=True`. Keep direct access
to Gunicorn restricted to that proxy. Public hosting, proxy provisioning and
multi-instance deployment are not provided by this configuration.

## Contributor validation

```bash
docker build -t tuxedo-finance:test .
uv run python scripts/docker_smoke.py --image tuxedo-finance:test
npm run test:e2e -- --docker-image tuxedo-finance:test
```

Both runners own fresh Compose projects, keys, volumes and loopback ports and
remove only their own resources. They never consume the developer's `.env`,
`TUXEDO_DATA_DIR` or `E2E_BASE_URL`. Failure logs remain under `test-results/`.
The lifecycle runner checks non-root operation, configuration failures, assets,
translations, financial-record persistence, repeated startup, backup/restore,
shutdown and health checks. The browser runner exercises the real container.

See [versioning.md](versioning.md#container-releases) for release publication
and first-publication access verification.
