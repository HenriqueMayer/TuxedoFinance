#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
data_dir=$(mktemp -d "${TMPDIR:-/tmp}/tuxedo-preview-data.XXXXXX")
image_stage=$(mktemp -d "${TMPDIR:-/tmp}/tuxedo-preview-images.XXXXXX")
server_log="$data_dir/server.log"
ready_file="$data_dir/server-url"
server_pid=''

cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    rm -rf -- "$data_dir" "$image_stage"
}
trap cleanup EXIT INT TERM

cd "$project_root"

if [[ -e "$project_root/db.sqlite3" ]]; then
    local_db_fingerprint=$(uv run python -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("db.sqlite3").read_bytes()).hexdigest())')
else
    local_db_fingerprint='missing'
fi

export TUXEDO_DATA_DIR="$data_dir"
export TUXEDO_ENV_FILE=/dev/null
export DJANGO_SETTINGS_MODULE=core.settings
export DEBUG=True HTTPS=False ALLOW_SIGNUPS=False
export ALLOWED_HOSTS=127.0.0.1,localhost
export PREVIEW_CAPTURE=1
export SECRET_KEY
SECRET_KEY=$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')
export PREVIEW_PASSWORD
PREVIEW_PASSWORD=$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')
export PREVIEW_OUTPUT_DIR="$image_stage"

uv run python manage.py migrate --noinput
uv run python scripts/preview/seed_preview_data.py
uv run python scripts/preview/serve.py --ready-file "$ready_file" >"$server_log" 2>&1 &
server_pid=$!

for _ in {1..40}; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
        cat "$server_log" >&2
        exit 1
    fi
    if [[ -s "$ready_file" ]]; then
        break
    fi
    sleep 0.25
done
[[ -s "$ready_file" ]] || { echo 'Owned preview server did not become ready.' >&2; exit 1; }
export PREVIEW_BASE_URL
PREVIEW_BASE_URL=$(cat "$ready_file")
kill -0 "$server_pid" 2>/dev/null || { cat "$server_log" >&2; exit 1; }
curl --noproxy '*' --fail --silent "$PREVIEW_BASE_URL/" >/dev/null
kill -0 "$server_pid" 2>/dev/null || { cat "$server_log" >&2; exit 1; }

node scripts/preview/capture_preview.js

for language in en pt-br; do
    for name in dashboard-light reports-light transactions-light banking-light investments-light planning-light dashboard-dark; do
        image="$image_stage/$language/$name.png"
        [[ -s "$image" ]] || { echo "Missing capture: $image" >&2; exit 1; }
        dimensions=$(file "$image")
        [[ "$dimensions" == *'1440 x 1000'* ]] || {
            echo "Unexpected dimensions: $dimensions" >&2
            exit 1
        }
    done
done

if [[ -e "$project_root/db.sqlite3" ]]; then
    current_local_db_fingerprint=$(uv run python -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("db.sqlite3").read_bytes()).hexdigest())')
else
    current_local_db_fingerprint='missing'
fi
[[ "$local_db_fingerprint" == "$current_local_db_fingerprint" ]] || {
    echo 'The local db.sqlite3 changed during preview capture.' >&2
    exit 1
}

for language in en pt-br; do
    mkdir -p "$project_root/preview/images/$language"
    cp "$image_stage/$language/"*.png "$project_root/preview/images/$language/"
done

echo 'Preview screenshots updated successfully.'
