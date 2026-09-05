# Contributing to Tuxedo Finance

Contributions are provided under the repository's [PolyForm Noncommercial
License](LICENSE). Copies and modified distributions must retain the required
copyright and license notices.

## Development principles

- Preserve the local-first Django architecture, user isolation, Decimal-based
  calculations, accessibility, and no-JavaScript form fallbacks.
- Keep domain code and Python tests in their owning apps. Shared browser tests
  belong in `tests/e2e`, preview tests in `tests/preview`, and repository-tool
  tests in `tests/tooling`. Root manifests serve the shared toolchain.
- Introduce a module or abstraction when it has a distinct responsibility or
  removes demonstrated duplication. File length alone does not justify a split.
- Update documentation affected by a change. Maintain equivalent content in
  `README.md` and `README.pt-BR.md`; technical guides remain in English. Use
  precise, professional language. Keep icons consistent with the established
  README layout; technical guides do not need decorative emojis.
- Update English and Brazilian Portuguese interface strings together. Keep
  user-entered data outside the translation catalog.
- Record notable changes for users, operators, or contributors under
  `Unreleased` in [CHANGELOG.md](CHANGELOG.md). Follow the
  [release workflow](docs/versioning.md) for versions and tags.

## Prerequisites

Use Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Node.js 20 (the CI baseline), npm, and GNU gettext (`msgfmt` and `xgettext`).
The isolated browser executor supports Linux, macOS, and WSL. Node.js and
gettext are development tools; compiled frontend assets and translations are
included for normal application use.

From the repository root:

```bash
uv sync --locked
npm ci
npx playwright install chromium
```

On Linux, Playwright may also require system libraries; CI installs them with
`npx playwright install --with-deps chromium`.

## Python checks

The following commands use a temporary data directory and an empty environment
file, so Django checks cannot open the installation's database. Run this block
in a subshell; the trap disposes of its temporary directory.

```bash
(
  check_dir=$(mktemp -d)
  trap 'rm -f "$check_dir"/db.sqlite3 "$check_dir"/db.sqlite3-wal "$check_dir"/db.sqlite3-shm "$check_dir"/db.sqlite3-journal; rmdir "$check_dir"' EXIT
  export TUXEDO_DATA_DIR="$check_dir" TUXEDO_ENV_FILE=/dev/null
  export SECRET_KEY=local-validation-only DEBUG=True HTTPS=False ALLOW_SIGNUPS=True
  uv run python scripts/check_version.py &&
  uv run python -m unittest discover -s tests/tooling &&
  uv run python manage.py check &&
  uv run python manage.py makemigrations --check --dry-run &&
  uv run coverage run --branch manage.py test &&
  uv run coverage report --show-missing --fail-under=70
)
```

The Django suite uses its own test database. The trap also removes any SQLite
files created by the migration check in that temporary directory. Coverage
outputs are ignored local artifacts.
See [coverage-baseline.md](docs/coverage-baseline.md) for policy and measurements.

CI also performs executable-correctness lint and dependency audits:

```bash
uvx --from 'ruff>=0.9,<1' ruff check . --select F --ignore F401
npm audit --audit-level=high
```

To audit the locked Python runtime without including development dependencies:

```bash
(
  requirements_file=$(mktemp)
  trap 'rm -f "$requirements_file"' EXIT
  uv export --locked --no-dev --format requirements-txt > "$requirements_file" &&
  uvx --from 'pip-audit>=2.7,<3' pip-audit --strict -r "$requirements_file"
)
```

Ruff is invoked through `uvx`; it is not an application dependency. Keep the
current focused rule set until a separate style migration is agreed.

## Frontend and translations

After changing Tailwind classes or tokens:

```bash
npm run build:css
```

Update the stylesheet's `?v=` value in the base template when its contents change.
CI rebuilds CSS into a temporary file and compares it with the committed asset;
it also verifies the pinned checksum of vendored HTMX.

After changing translatable UI copy:

```bash
uv run python manage.py makemessages -l pt_BR
# Translate new entries in locale/pt_BR/LC_MESSAGES/django.po.
uv run python manage.py compilemessages
```

Commit the updated `.po` and `.mo` files together. CI checks that recompilation
leaves the committed `.mo` unchanged. The
[frontend guide](docs/frontend.md#translation-convention) defines which strings
to mark and how the interface retains its no-JavaScript behavior.

## Browser tests

```bash
npm run test:e2e
npm run test:preview
```

`test:e2e` creates a temporary SQLite database, overrides installation settings,
uses an empty `.env`, generates an ephemeral signing key, and enables signup.
It migrates that database, starts its own Django server on a free loopback port,
and passes the URL to Playwright. It never reuses an existing server or the
installation's `TUXEDO_DATA_DIR`, `.env`, or `E2E_BASE_URL`.

The executor forwards Playwright arguments and returns the suite's exit code:

```bash
npm run test:e2e -- --grep 'dashboard'
```

Success, failure, and interruption all stop its processes and remove temporary
data. Migration and server logs remain at `test-results/e2e-server.log`.
Playwright retains configured failure screenshots, videos, and traces; CI
uploads browser artifacts when a check fails.

For an advanced, manually managed **disposable** installation, the direct
`npx playwright test` command still honors `E2E_BASE_URL` (default:
`http://127.0.0.1:8765`). It does not manage a server or database. The suite creates
users and financial records, so never point that direct command at personal data.

`test:preview` serves only the committed static tour. Screenshot regeneration is
a separate operation, `npm run preview:capture`, documented in
[preview maintenance](.github/preview/README.md).

## Before proposing a change

Run the applicable checks above and `git diff --check`. Review the diff for
unintended generated files and private data. For documentation changes, verify
relative links, section anchors, images, and rendered layout; compare both
READMEs for equivalent commands, features, and version badges.

The single application CI job uses the same lockfiles and isolated browser
executor as local development. It checks the supported SQLite configuration;
it does not certify other databases or deployment stacks. Describe relevant
validation and remaining gaps in the pull request. Avoid broadening a successful
test run without a new change or unresolved concern.

## License notices

Preserve existing notices. Where practical, new distributable source files
should include `SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0`.
