# Deployment (Docker)

CashFlow ships as a single, lean container: the Django app served by `gunicorn`, plus one named volume that persists the `db.sqlite3` file. There is no separate database service (SQLite is a single file) and no nginx/reverse proxy — static files are served in-process by WhiteNoise. Day-to-day operator instructions (first run, `.env` setup, the release checklist) live in the root [`README.md`](../README.md#docker) — this page documents *how the image is built* and *why* it's built that way, for anyone changing the `Dockerfile`/`docker-compose.yml` themselves.

## `Dockerfile` — two stages

### Stage 1: `builder` (`ghcr.io/astral-sh/uv:python3.12-trixie-slim`)

1. **Install Python dependencies** with `uv sync --locked --no-install-project`, using cache/bind mounts on `uv.lock`/`pyproject.toml` only — this layer is cached across code changes since it runs before `COPY . /app`.
2. **Copy the project** and run `uv sync --locked` again to install the project itself into the venv.
3. **Translations** — the runtime needs the compiled `locale/pt_BR/LC_MESSAGES/django.mo` catalog. The current image copies that committed artifact with the source tree. GNU gettext supplies `msgfmt`, which Django's `compilemessages` command invokes, so any build that regenerates the catalog must install gettext in the builder, run `uv run python manage.py compilemessages`, and keep that tooling out of the runtime stage.
4. **Tailwind build stage** — download the standalone Tailwind CLI binary (pinned via `ARG TAILWIND_VERSION`, no Node.js/npm anywhere in the image) and compile:
   ```
   tailwindcss -i ./tailwind/input.css -o ./static/css/output.css --minify
   ```
5. **`collectstatic`** — run with placeholder settings (`SECRET_KEY=build-time-placeholder`, `DEBUG=False`, `ALLOWED_HOSTS=localhost`). `collectstatic` never opens the database and doesn't need real secrets; the *runtime* container always gets its actual `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` from the environment (`.env` via `docker-compose.yml`) — nothing secret is baked into the image.

### Stage 2: `runtime` (`python:3.12-slim-trixie`)

1. Creates a non-root system user/group `cashflow` (uid/gid 999).
2. `COPY --from=builder --chown=cashflow:cashflow /app /app` — pulls in the fully-built app (venv, compiled CSS, collected static files) from the builder stage, skipping all build tooling (`uv`, the Tailwind CLI, `pip` caches).
3. **`RUN chown cashflow:cashflow /app`** — necessary because `WORKDIR /app` creates the directory as `root` *before* the `COPY --chown` above runs, and `--chown` only rewrites ownership of files copied *into* the directory, not the top-level directory entry itself. Without this line, the non-root `cashflow` user cannot write the SQLite file into a subdirectory of `/app` at runtime. (This was caught and fixed during Sprint 10 — see the Sprint 10 notes if you're auditing history.)
4. `VOLUME ["/app/data"]` — where the SQLite file lives (matches `SQLITE_PATH` in `.env.example`); chowned to `cashflow` in step 3, so the app can write to it without running as root.
5. `USER cashflow` — the container process never runs as root.
6. `CMD`:
   ```
   sh -c "python manage.py migrate --noinput && exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3"
   ```
   Migrations run automatically on every container start (idempotent — a no-op if already applied), then `exec` hands off PID 1 to `gunicorn` (so it receives signals directly, e.g. for graceful shutdown).

## `docker-compose.yml`

```yaml
services:
  app:
    build: .
    ports: ['8000:8000']
    env_file: [.env]
    volumes:
      - db-data:/app/data
    restart: unless-stopped

volumes:
  db-data:
```

A single service. `env_file: .env` supplies `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`/`SQLITE_PATH`/`CURRENCY`/`HTTPS`; `CURRENCY` is the default base currency for new users, not a restriction on account currencies. The named volume `db-data` mounted at `/app/data` normally preserves data. For the approved breaking banking release, back up any legacy volume and deliberately recreate it before applying the fresh migration graph; no in-place upgrade is supported.

### TLS is out of scope for this compose file

The service publishes **plain HTTP** on `:8000`, which is why HTTPS hardening remains behind its own `HTTPS` flag defaulting to `False` rather than following `DEBUG`. Enabling it without a TLS terminator would prevent secure cookies from returning and redirect to an HTTPS endpoint that is not listening.

Put this container behind something that terminates TLS (a reverse proxy, a load balancer, a PaaS router), then set `HTTPS=True` in `.env`. That switch also starts trusting `X-Forwarded-Proto`, so the terminator must set it — and must strip any client-supplied copy, or the header can be forged.

The `SECRET_KEY` guard is worth knowing about when debugging a container that exits immediately on boot: with `DEBUG=False` and no real key set, `core/settings.py` raises `ImproperlyConfigured` before `gunicorn` starts. The fix is to put a generated key in `.env`, not to unset `DEBUG`.

## `.dockerignore`

Keeps the build context lean and prevents dev-only artifacts from leaking into the image: VCS metadata, `__pycache__`/venvs, the *local* `db.sqlite3` (the container gets its own, in the mounted volume — never baked into the image), the uncompiled `static/css/output.css` (regenerated fresh at build time), editor cruft, `.env`/`.env.*` (secrets — `.env.example` is explicitly re-allowed via `!.env.example` since it has no real secrets), and project-management files not needed at runtime (`docs/`, `ProductRequirementsDocument.md`, `CLAUDE.md`, `.claude/`).

## Static files in production

Covered in full in [architecture.md § Static files](architecture.md#static-files) and [frontend.md § Tailwind strategy](frontend.md#tailwind-strategy-devprod); the short version: `DEBUG=False` (always true for any real deployment) selects `whitenoise.storage.CompressedManifestStaticFilesStorage` — gzip/brotli-compressed, content-hashed filenames for long-lived caching, served directly by the `WhiteNoiseMiddleware` already installed right after `SecurityMiddleware`. No nginx, no CDN, no separate static-file service.

## Translation release check

GNU gettext is required in the environment that compiles translations (local
release host or the Docker builder), but not in the final runtime image. Before
shipping changes to marked UI strings, run:

```bash
uv run python manage.py makemessages -l pt_BR
# translate new entries in locale/pt_BR/LC_MESSAGES/django.po
uv run python manage.py compilemessages
uv run python manage.py test core
```

Ship both `django.po` and the generated `django.mo`. The tests cover cookie
persistence, public and authenticated selectors, HTMX translation and currency
format independence; they do not require a localized URL configuration.

## Operator-facing docs

First-run steps, `.env` setup, rebuilding CSS locally without Docker, and the pre-deploy release checklist all live in the project root [`README.md`](../README.md) — that file is the one operators actually follow; this page exists so the *implementation* of the Docker setup has a home in `docs/` alongside every other part of the codebase.
