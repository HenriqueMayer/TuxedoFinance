FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    CASHFLOW_DATA_DIR=/data

RUN useradd --create-home --uid 10001 cashflow \
    && mkdir -p /app /data \
    && chown -R cashflow:cashflow /app /data

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
COPY docker/entrypoint.sh /usr/local/bin/cashflow-entrypoint
RUN chmod 0755 /usr/local/bin/cashflow-entrypoint \
    && chown -R cashflow:cashflow /app

USER cashflow
EXPOSE 8000
ENTRYPOINT ["cashflow-entrypoint"]
