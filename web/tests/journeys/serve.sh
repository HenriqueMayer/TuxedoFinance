#!/usr/bin/env bash
# Starts the backend for the browser journeys with a temporary data directory.
# It serves the built client from web/dist, so build the client first.
set -euo pipefail

port="$1"
data_dir="$(mktemp -d)"
trap 'rm -rf "$data_dir"' EXIT

cd "$(dirname "$0")/../../../backend"
export SECRET_KEY=journeys-only-not-a-real-secret
export TUXEDO_ENV_FILE=/dev/null
export TUXEDO_DATA_DIR="$data_dir"
export DEBUG=False
export DJANGO_SUPERUSER_USERNAME=journey
export DJANGO_SUPERUSER_PASSWORD=journey-passphrase-42
export DJANGO_SUPERUSER_EMAIL=journey@example.test

uv run python -B manage.py migrate --noinput >/dev/null
uv run python -B manage.py createsuperuser --noinput >/dev/null
uv run python -B manage.py runserver "127.0.0.1:${port}" --noreload --nothreading
