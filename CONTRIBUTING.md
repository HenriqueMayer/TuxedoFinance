# Contributing to Tuxedo Finance

Contributions are provided under the repository's [PolyForm Noncommercial
License](LICENSE). Copies and modified distributions must retain the required
copyright and license notices.

## Development principles

- Reuse the approved [design catalogue](docs/design-system.html) and shared
  components listed in the [interface map](docs/interface-map.md). Keep that map
  current when adding a route or interaction; presentation must preserve domain
  precision, native fallbacks and paused-feature gates.
- All new or changed forms must follow the mandatory
  [keyboard and choice contract](docs/frontend.md#keyboard-and-choice-contract):
  shared searchable record choices, native short choices, explicit conditional
  selections, visible focus, error recovery and a complete no-JavaScript path.
  Include real keyboard and conditional-transition tests in form reviews.
- Preserve the local-first Django architecture, user isolation, Decimal-based
  calculations, accessibility, and no-JavaScript form fallbacks.
- Use the [shared question-mark help contract](docs/frontend.md#question-mark-help)
  for every new or changed help icon. Test hover dismissal, keyboard/touch,
  outside clicks, readable viewport bounds and HTMX behavior.
- Preserve viewport and keyboard focus when updating the current page (filters,
  cards, sorting, pagination, refreshes and inline edits). Follow the
  [location-preservation contract](docs/frontend.md#preserve-the-users-location)
  and test from a nonzero scroll position; ordinary updates must not jump to the top.
- Keep domain code and Python tests in their owning apps. Shared browser tests
  belong in domain folders under `tests/e2e`, preview tests in `tests/preview`,
  and repository-tool tests in `tests/tooling`. Shared E2E helpers own catalogue
  routing and repository paths. Root manifests serve the shared toolchain;
  Tailwind configuration lives in `assets/` and Playwright configuration in
  `tests/`.
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

The following block uses a temporary data directory and an empty environment
file, so Django checks cannot open the installation's database. Python disposes
of the directory on success or failure; do not replace it with an installation
path.

```bash
uv run python - <<'PY'
import os
import subprocess
import tempfile

with tempfile.TemporaryDirectory(prefix="tuxedo-check.") as check_data:
    env = os.environ.copy()
    env.update(
        TUXEDO_DATA_DIR=check_data, TUXEDO_ENV_FILE="/dev/null",
        SECRET_KEY="local-validation-only", DEBUG="True", HTTPS="False",
        ALLOW_SIGNUPS="True", DJANGO_SETTINGS_MODULE="core.settings",
    )
    commands = [
        ["python", "scripts/check_version.py"],
        ["python", "-m", "unittest", "discover", "-s", "tests/tooling"],
        ["python", "manage.py", "check"],
        ["python", "manage.py", "makemigrations", "--check", "--dry-run"],
        ["coverage", "run", "--branch", "manage.py", "test"],
        ["coverage", "report", "--show-missing", "--fail-under=70"],
    ]
    for command in commands:
        subprocess.run(["uv", "run", *command], env=env, check=True)
PY
```

The Django suite uses its own test database. The context also removes any SQLite
files created by the migration check in that temporary directory. Coverage
outputs are ignored local artifacts under `.local/coverage/`.
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
npm run test:unit
```

Use the shared `{% asset %}` template tag for CSS and JavaScript URLs; it versions
the files by their delivered content. No manual `?v=` bump is needed. The shared
runtime also refreshes an older HTMX document on its next GET when those assets
change, without replaying POSTs or discarding validation errors.
CI rebuilds CSS into a temporary file and compares it with the committed asset;
it also verifies the pinned checksum of vendored HTMX.

After changing translatable UI copy:

```bash
uv run python - <<'PY'
import os
import subprocess
import tempfile

with tempfile.TemporaryDirectory(prefix="tuxedo-messages.") as message_data:
    env = os.environ.copy()
    env.update(TUXEDO_DATA_DIR=message_data, TUXEDO_ENV_FILE="/dev/null",
               SECRET_KEY="local-validation-only", DJANGO_SETTINGS_MODULE="core.settings")
    subprocess.run(["uv", "run", "python", "manage.py", "makemessages",
                    "-l", "pt_BR", "--no-wrap"], env=env, check=True)
PY
# Translate new entries in locale/pt_BR/LC_MESSAGES/django.po.
msgfmt --check-format locale/pt_BR/LC_MESSAGES/django.po \
  -o locale/pt_BR/LC_MESSAGES/django.mo
```

Compile the project catalog directly so dependency catalogs are not modified.
Commit the updated `.po` and
`.mo` files together. CI checks that recompilation
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

Without a file filter or grep, this command runs the complete application
browser suite. Existing skipped cases for paused features remain skipped.

Success, failure, and interruption all stop its processes and remove temporary
data. Owned temporary installations live under `.local/test-results/runtime/`;
migration and server logs remain at `.local/test-results/e2e-server.log`.
Playwright retains configured failure screenshots, videos, and traces; CI
uploads browser artifacts when a check fails.

For an advanced, manually managed **disposable** installation, the direct
`npx playwright test --config=tests/playwright.config.js` command still honors
`E2E_BASE_URL` (default: `http://127.0.0.1:8765`). It does not manage a server or
database. The suite creates users and financial records, so never point that
direct command at personal data.

`test:preview` serves only the committed static tour. Screenshot regeneration is
a separate operation, `npm run preview:capture`, documented in
[preview maintenance](docs/preview.md).

The E2E configuration uses absolute repository paths so moving specs into domain
folders does not change asset roots or the disposable executor. Catalogue tests
share `tests/e2e/helpers/catalogue.js`; application tests reuse the existing form
and navigation helpers. `npm run test:unit` executes the dependency-free
JavaScript amount/allocation tests and also runs in CI.

New browser reports live in `.local/playwright-report/`, test artifacts and logs
in `.local/test-results/`, coverage in `.local/coverage/`, and Ruff's cache in
`.local/cache/ruff/`. Playwright clears only `.local/test-results/browser/`,
keeping active runtime and server logs beside it. The [test index](tests/README.md)
maps domain folders and shared helpers. This ignored tree is not installation
storage. Never move installation `.env`, databases, backups or dependencies into
it, and do not remove an old artifact directory merely because a new output
location is configured.

## Reporting performance

`uv run python scripts/benchmark_reporting.py --samples 20 --output .local/test-results/reporting.json`
measures 0, 1,000 and 10,000 synthetic sources in separate disposable processes.
It never accepts an installation database or server. See the
[measurement method and limits](docs/reviews/project-health-2026-10-16.md#reproducible-reporting-measurements)
before comparing results. Benchmark observations guide focused changes; they
are not timing assertions in the test suite.

## Docker validation

The Docker workflow validates the single-instance SQLite image on Linux amd64
and arm64. It builds from the locked dependencies and runs lifecycle,
backup/restore and browser checks before publishing stable releases.

```bash
docker build -t tuxedo-finance:test .
uv run python scripts/docker_smoke.py --image tuxedo-finance:test
npm run test:e2e -- --docker-image tuxedo-finance:test
```

Both Docker runners own their Compose project, ephemeral key, loopback port and
named volume. They discard inherited installation/Compose settings and remove
only their own resources. Logs remain under `.local/test-results/`. Never target the
installation owner's database, server or volume. Docker Engine 28+ or a current
Docker Desktop and Compose v2+ are the supported installation baseline.
See [Docker operations](docs/docker.md) for configuration and release delivery.

## Before proposing a change

Run the applicable checks above and `git diff --check`. Review the diff for
unintended generated files and private data. For documentation changes, verify
relative links, section anchors, images, and rendered layout; compare both
READMEs for equivalent commands, features, and version badges.

The [documentation index](docs/README.md) identifies each guide's owner. Keep
current instructions in that guide and dated findings, test counts and benchmark
evidence in [reviews](docs/reviews/README.md). Historical reviews must state their
date and point to the current contract; retain their evidence and limitations.
Do not copy the same detailed interaction protocol into several app guides:
link to the shared frontend contract and describe only the app's domain behavior
and deliberate exceptions. Keep `AGENTS.md` as the implementation checklist,
with setup and executable commands here.

The single application CI job uses the same lockfiles and isolated browser
executor as local development. It checks the supported SQLite configuration;
it does not certify other databases or deployment stacks. Describe relevant
validation and remaining gaps in the pull request. Avoid broadening a successful
test run without a new change or unresolved concern.

## License notices

Preserve existing notices. Where practical, new distributable source files
should include `SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0`.
