# Contributing to Tuxedo Finance

Thank you for improving Tuxedo Finance. By submitting a contribution, you agree that
it is provided under the repository's [PolyForm Noncommercial License](LICENSE)
and that copies and modified distributions preserve the required copyright and
license notices.

## Before opening a change

- Keep Tuxedo Finance a small, self-hosted personal-finance application; do not add
  SaaS-scale infrastructure or unsupported deployment packaging.
- Preserve user isolation, Decimal-based financial calculations, accessibility
  and no-JavaScript fallbacks.
- Update README, PRD, data model and affected app documentation with code.
- Add or update English and Brazilian Portuguese interface strings together.
- Record user-visible changes under `Unreleased` in
  [`CHANGELOG.md`](CHANGELOG.md). Version numbers and tags are prepared through
  the documented [release workflow](docs/versioning.md), not on feature branches.
- Run `manage.py check`, `makemigrations --check --dry-run`, tests and
  `compilemessages` before proposing a change. Frontend changes must also
  rebuild Tailwind and pass the Playwright smoke suite.

## Test strategy and CI

The supported path is Python 3.12, `uv`, Django's test runner, SQLite and the
frontend tools pinned by npm. The application CI job reproduces that local workflow
from both lockfiles. A separate Docker workflow checks the supported single-instance
SQLite image on Linux amd64 and arm64; other databases and SaaS deployment
matrices remain outside the supported path. It runs Django
checks, missing-migration checks, translation compilation, the full suite with
branch coverage, Ruff, locked Python and npm dependency audits, generated-asset
consistency and focused Chromium smoke tests. Browser failures upload screenshots,
video and trace artifacts for diagnosis.

The separate static-preview suite checks both languages, theme persistence,
image loading, the screenshot dialog and mobile overflow. Run it with
`npm run test:preview`. When the public interface tour needs new screenshots,
run `npm run preview:capture`; it creates localized synthetic profiles in a
guarded temporary SQLite database and removes all temporary data. Never replace
that isolation with the repository-root `db.sqlite3` or real financial records.

Coverage is reported as XML and HTML artifacts. CI enforces a repository-wide
70% line-coverage floor; branch coverage is reported but not independently
gated. Keep tests for all affected user flows and record additions, obsolete
assertions and known gaps in the pull request description rather than deleting
valuable tests to make an intermediate build pass. See
[`docs/coverage-baseline.md`](docs/coverage-baseline.md) for the exact local
commands.

## License notices

Do not remove or weaken the copyright or license notices in this repository.
Where practical, new distributable source files should include the concise
identifier `SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0`.

## Isolated application and container checks

Use an empty environment file and temporary data directory for Django checks:

```bash
(
  check_dir=$(mktemp -d)
  trap 'rm -rf -- "$check_dir"' EXIT
  export TUXEDO_DATA_DIR="$check_dir" TUXEDO_ENV_FILE=/dev/null
  export SECRET_KEY=local-check-only DEBUG=True HTTPS=False ALLOW_SIGNUPS=True
  uv run python manage.py check &&
  uv run python manage.py makemigrations --check --dry-run &&
  uv run coverage run --branch manage.py test &&
  uv run coverage report --show-missing --fail-under=70
)
uv run python -m unittest discover -s tests/tooling
npm run test:e2e
docker build -t tuxedo-finance:test .
uv run python scripts/docker_smoke.py --image tuxedo-finance:test
npm run test:e2e -- --docker-image tuxedo-finance:test
git diff --check
```

`npm run test:e2e` owns its database and loopback server. The Docker option owns
its Compose project and named volume as well. Both ignore inherited installation
settings and `E2E_BASE_URL`; do not replace these runners with a suite targeting
a personal installation. Logs and browser failure artifacts are retained under
`test-results/`. Install Chromium with `npx playwright install chromium` first.
See [Docker operations](docs/docker.md) for container validation and delivery.
