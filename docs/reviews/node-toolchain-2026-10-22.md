# Node.js tooling baseline — 2026-10-22

## Scope

The application and Docker validation workflows now read Node.js 22.23.4 from
the repository's `.nvmrc`, replacing their Node.js 20 baseline. Contributor
prerequisites use the same pin and explain `nvm use`. This selects the patched
22.x release identified in the
[21 October security announcement](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases).
Node.js remains a development/build/browser-test tool; the Docker application
runtime remains Python.

## Local validation

All frontend checks below used Node.js **v22.23.4** and npm **10.9.9** on Linux
amd64. The existing dependency versions were retained.

- A clean `npm ci`, using copies of both manifests in a temporary directory
  outside the checkout, installed 28 packages and audited 29 with no known
  vulnerabilities. `npm ls --depth=0` matched all four pinned frontend tools;
  fresh PostCSS, Tailwind and Playwright imports succeeded. The directory was
  removed automatically without replacing the checkout's `node_modules`.
- `npm run test:unit`: **26 passed**.
- `npm run build:css -- <temporary-output>` and `cmp` reproduced the committed
  stylesheet exactly; the temporary output was removed automatically.
- `npm audit --audit-level=high`: **0 vulnerabilities**.
- `npm run test:preview`: **34 passed**, using its owned loopback static server.
- `npm run test:e2e -- tests/e2e/transactions/transactions.spec.js
  tests/e2e/shared/navigation-menus.spec.js tests/e2e/shared/dates.spec.js`:
  **36 passed** against an owned disposable Django server/database. Coverage
  includes financial entry/filtering, keyboard navigation, dates, native
  no-JavaScript behavior, both languages/themes and desktop/mobile layouts.
- Isolated Python validation passed the version check, **44 repository-tool
  tests**, Django system checks and the migration dry run (no changes).
- `uv run python scripts/check_docs.py`: **101 documents, 848 local references,
  0 unresolved**; `git diff --check` passed.

Python checks followed the disposable-environment contract in
[Contributing](../../CONTRIBUTING.md#python-checks), with an empty environment
file, temporary data/vault directories and `UV_NO_SYNC=1`. Browser checks also
inherited `UV_NO_SYNC=1`; existing Python dependencies were not resynchronized.

The package manifests, both lockfiles, Dockerfile and compiled stylesheet
remained byte-identical to `HEAD`. No application configuration, installation
data, `.env`, database or backups were changed.

## Boundaries

These are local tooling compatibility checks. This validation did not run the
full Django/application browser suites, Docker lifecycle/multiarchitecture
checks or remote GitHub Actions jobs. Remote validation is tracked in the pull
request. No release, merge or application deployment is part of this change.
Cloudflare deployment remains a study.
