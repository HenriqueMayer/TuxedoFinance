# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
FROM ghcr.io/astral-sh/uv:0.12.9 AS uv
FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
RUN SECRET_KEY=build-only-not-a-runtime-secret TUXEDO_ENV_FILE=/dev/null \
    DEBUG=False .venv/bin/python manage.py collectstatic --noinput

FROM python:3.12-slim-bookworm AS runtime
ARG VERSION=development
ARG REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/HenriqueMayer/TuxedoFinance" \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$REVISION"
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TUXEDO_DATA_DIR=/data TUXEDO_ENV_FILE=/dev/null DEBUG=False HTTPS=False
WORKDIR /app
COPY --from=build /app /app
RUN groupadd --gid 10001 tuxedo && useradd --uid 10001 --gid tuxedo --no-create-home tuxedo \
    && mkdir /data && chown tuxedo:tuxedo /data && chmod 700 /data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "scripts/docker_healthcheck.py"]
ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]
CMD ["serve"]
