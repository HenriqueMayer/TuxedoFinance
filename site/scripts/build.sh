#!/usr/bin/env bash
# Builds the public site in site/dist:
#   1. the client in demonstration mode, under public/app/;
#   2. the demonstration data of each language, exported by the backend from
#      an empty temporary database;
#   3. the pages.
# Needs the dependencies of backend/ (uv sync), web/ and site/ (npm ci).
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
app="$root/site/public/app"

rm -rf "$app"
(cd "$root/web" && npx vite build --mode demo --outDir "$app" --emptyOutDir)

mkdir -p "$app/demo"
for language in en pt-BR; do
  data="$(mktemp -d)"
  (
    cd "$root/backend"
    export SECRET_KEY=demo-export-only-not-a-real-secret
    export TUXEDO_ENV_FILE=/dev/null
    export TUXEDO_DATA_DIR="$data"
    uv run python -B manage.py migrate --noinput >/dev/null
    uv run python -B manage.py export_demo "$app/demo/$language.json" --language "$language"
  )
  rm -rf "$data"
done

(cd "$root/site" && npx astro build)
