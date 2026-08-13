# Contributing to CashFlow

Thank you for improving CashFlow. By submitting a contribution, you agree that
it is provided under the repository's [PolyForm Noncommercial License](LICENSE)
and that copies and modified distributions preserve the required copyright and
license notices.

## Before opening a change

- Keep CashFlow a small, self-hosted personal-finance application; do not add
  SaaS-scale infrastructure or unsupported deployment packaging.
- Preserve user isolation, Decimal-based financial calculations, accessibility
  and no-JavaScript fallbacks.
- Update README, PRD, data model and affected app documentation with code.
- Add or update English and Brazilian Portuguese interface strings together.
- Run `manage.py check`, `makemigrations --check --dry-run`, tests and
  `compilemessages` before proposing a change.

## Test strategy and CI

The supported path is Python 3.12, `uv`, Django's test runner and SQLite. The
single CI job reproduces that local workflow from `uv.lock`; it does not test
other databases, SaaS deployment matrices or Docker packaging. It runs Django
checks, missing-migration checks, translation compilation, the full suite with
branch coverage, Ruff, and a locked-runtime `pip-audit` scan.

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
