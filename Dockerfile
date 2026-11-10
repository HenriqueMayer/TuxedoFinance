# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# One image: the built React client and the Django backend that serves it.

FROM node:22-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.9 AS uv

FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev
COPY backend/ ./
COPY --from=web /src/web/dist /app/client

FROM python:3.12-slim-bookworm AS runtime
ARG VERSION=development
ARG REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/HenriqueMayer/TuxedoFinance" \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$REVISION"
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TUXEDO_DATA_DIR=/data TUXEDO_CLIENT_DIR=/app/client TUXEDO_ENV_FILE=/dev/null \
    DEBUG=False HTTPS=False
WORKDIR /app
COPY --from=build /app /app
RUN groupadd --gid 10001 tuxedo && useradd --uid 10001 --gid tuxedo --no-create-home tuxedo \
    && mkdir /data && chown tuxedo:tuxedo /data && chmod 700 /data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "healthcheck.py"]
# Apply migrations, then serve. SQLite in WAL mode supports the two workers.
# The control socket of gunicorn is off: the user of the image has no home
# folder to hold it, and nothing in the image uses it.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --no-control-socket"]
