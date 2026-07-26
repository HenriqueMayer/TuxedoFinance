# Deployment (Docker)

CashFlow ships as a single, lean container: the Django app served by `gunicorn`, plus one named volume that persists the `db.sqlite3` file. There is no separate database service (SQLite is a single file) and no nginx/reverse proxy — static files are served in-process by WhiteNoise. Day-to-day operator instructions (first run, `.env` setup, the release checklist) live in the root [`README.md`](../README.md#docker) — this page documents *how the image is built* and *why* it's built that way, for anyone changing the `Dockerfile`/`docker-compose.yml` themselves.

## `Dockerfile` — two stages

### Stage 1: `builder` (`ghcr.io/astral-sh/uv:python3.12-trixie-slim`)

1. **Install Python dependencies** with `uv sync --locked --no-install-project`, using cache/bind mounts on `uv.lock`/`pyproject.toml` only — this layer is cached across code changes since it runs before `COPY . /app`.
2. **Copy the project** and run `uv sync --locked` again to install the project itself into the venv.
3. **Tailwind build stage** — download the standalone Tailwind CLI binary (pinned via `ARG TAILWIND_VERSION`, no Node.js/npm anywhere in the image) and compile:
   ```
   tailwindcss -i ./tailwind/input.css -o ./static/css/output.css --minify
   ```
4. **`collectstatic`** — run with placeholder settings (`SECRET_KEY=build-time-placeholder`, `DEBUG=False`, `ALLOWED_HOSTS=localhost`). `collectstatic` never opens the database and doesn't need real secrets; the *runtime* container always gets its actual `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` from the environment (`.env` via `docker-compose.yml`) — nothing secret is baked into the image.

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

A single service. `env_file: .env` is where `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`/`SQLITE_PATH`/`CURRENCY`/`HTTPS` come from at runtime (see `.env.example` and [architecture.md § Environment-driven configuration](architecture.md#environment-driven-configuration-production-readiness)). The named volume `db-data` mounted at `/app/data` is what makes `docker compose down && docker compose up` preserve data — only `docker compose down -v` destroys it.

### TLS is out of scope for this compose file

The service publishes **plain HTTP** on `:8000`, which is why the HTTPS hardening settings sit behind their own `HTTPS` flag defaulting to `False` rather than following `DEBUG` — see [architecture.md § HTTPS hardening](architecture.md#https-hardening). Enabling them here would break the documented first run: secure-only cookies are never returned by a browser over HTTP, so login would silently fail, and `SECURE_SSL_REDIRECT` would loop to an HTTPS port nothing is bound to.

Put this container behind something that terminates TLS (a reverse proxy, a load balancer, a PaaS router), then set `HTTPS=True` in `.env`. That switch also starts trusting `X-Forwarded-Proto`, so the terminator must set it — and must strip any client-supplied copy, or the header can be forged.

The `SECRET_KEY` guard is worth knowing about when debugging a container that exits immediately on boot: with `DEBUG=False` and no real key set, `core/settings.py` raises `ImproperlyConfigured` before `gunicorn` ever starts. That is intentional (see [architecture.md § The secret key guard](architecture.md#the-secret-key-guard)) — the fix is to put a generated key in `.env`, not to unset `DEBUG`.

## `.dockerignore`

Keeps the build context lean and prevents dev-only artifacts from leaking into the image: VCS metadata, `__pycache__`/venvs, the *local* `db.sqlite3` (the container gets its own, in the mounted volume — never baked into the image), the uncompiled `static/css/output.css` (regenerated fresh at build time), editor cruft, `.env`/`.env.*` (secrets — `.env.example` is explicitly re-allowed via `!.env.example` since it has no real secrets), and project-management files not needed at runtime (`docs/`, `ProductRequirementsDocument.md`, `CLAUDE.md`, `.claude/`).

## Static files in production

Covered in full in [architecture.md § Static files](architecture.md#static-files) and [frontend.md § Tailwind strategy](frontend.md#tailwind-strategy-devprod); the short version: `DEBUG=False` (always true for any real deployment) selects `whitenoise.storage.CompressedManifestStaticFilesStorage` — gzip/brotli-compressed, content-hashed filenames for long-lived caching, served directly by the `WhiteNoiseMiddleware` already installed right after `SecurityMiddleware`. No nginx, no CDN, no separate static-file service.

## Operator-facing docs

First-run steps, `.env` setup, rebuilding CSS locally without Docker, and the pre-deploy release checklist all live in the project root [`README.md`](../README.md) — that file is the one operators actually follow; this page exists so the *implementation* of the Docker setup has a home in `docs/` alongside every other part of the codebase.
