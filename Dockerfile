# syntax=docker/dockerfile:1
#
# CashFlow — production image.
#
#   1. builder — installs dependencies with `uv`, compiles the Tailwind CSS
#      bundle with the standalone CLI, and runs `collectstatic`.
#   2. runtime — slim Python image with no build tooling, running gunicorn
#      as a non-root user.

FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS builder

# Pinned for reproducible builds; bump when upgrading Tailwind.
ARG TAILWIND_VERSION=v4.3.3

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first, so this layer is cached across code changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# The standalone Tailwind CLI is a plain Linux binary — no Node.js or npm.
# It compiles tailwind/input.css into the bundle base.html serves when
# DEBUG=False.
ADD https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64 /usr/local/bin/tailwindcss
RUN chmod +x /usr/local/bin/tailwindcss \
    && tailwindcss -i ./tailwind/input.css -o ./static/css/output.css --minify

# Placeholder settings for `collectstatic` only — it never opens the database
# and needs no real secrets. The runtime container gets its actual
# SECRET_KEY/DEBUG/ALLOWED_HOSTS from the environment; nothing is baked in.
#
# The placeholder still has to clear `MIN_SECRET_KEY_LENGTH` in core/settings,
# because this step runs with DEBUG=False and that guard does not know the
# difference between a build and a deployment. Padding it is enough — the
# value never reaches the runtime image, let alone signs anything.
RUN mkdir -p /app/data \
    && SECRET_KEY=build-time-placeholder-not-used-at-runtime-0000000000 \
       DEBUG=False ALLOWED_HOSTS=localhost \
       uv run python manage.py collectstatic --noinput


FROM python:3.12-slim-trixie AS runtime

RUN groupadd --system --gid 999 cashflow \
    && useradd --system --gid 999 --uid 999 --create-home cashflow

WORKDIR /app
COPY --from=builder --chown=cashflow:cashflow /app /app
# `WORKDIR` creates /app as root and `--chown` only applies to files copied
# into it, so the directory itself is fixed up separately.
RUN chown cashflow:cashflow /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER cashflow

# Mount point for the SQLite volume (see docker-compose.yml and SQLITE_PATH).
VOLUME ["/app/data"]

EXPOSE 8000

# Apply migrations, then hand off to gunicorn.
#
# `gthread` rather than the default `sync` worker. A sync worker serves one
# connection at a time and blocks in recv() until a whole request arrives, so
# a browser's speculative pre-connect — Chrome opens sockets before it has
# anything to send — ties up an entire worker until the timeout expires and
# the arbiter SIGKILLs it, logging `WORKER TIMEOUT ... (no URI read)`. A
# handful of those idle sockets is enough to stall every worker while real
# requests wait in the backlog. Threads absorb idle connections without
# burning a process each.
#
# Two processes instead of three also cuts SQLite write contention (see the
# DATABASES OPTIONS in core/settings.py); concurrency comes from the threads.
# `--access-logfile -` puts request lines on stdout alongside the tracebacks
# the LOGGING config now emits.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 2 --threads 4 --timeout 60 --graceful-timeout 30 --access-logfile - --error-logfile -"]
