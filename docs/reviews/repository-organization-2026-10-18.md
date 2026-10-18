# Repository organization — 2026-10-18

This delivery implements the first two agreed organization lots on top of
`7505d4f`. The first local commit is `ba5e728`; the second groups browser tests
and records the resulting contributor contracts. No publication or release is
part of this delivery.

## Responsibilities and boundaries

The number of tracked root files decreases from 22 to 20. Root manifests,
licensing, contributor entry points and `manage.py` retain their existing roles.
Tailwind configuration moves to `assets/tailwind.config.js`; application
Playwright configuration moves to `tests/playwright.config.js`. Commands resolve
these paths explicitly rather than depending on root-level config discovery.

Preview capture utilities move from `.github/preview/` to `scripts/preview/`,
their browser configuration to `tests/preview/`, and their guide to
[preview.md](../preview.md). `.github/` owns provider workflows. Preview servers
use owned readiness checks and disposable capture data; the committed public
tour was not regenerated or changed.

New generated files go under ignored `.local/`: coverage, Ruff cache, browser
results, reports and disposable runtime. Browser output cleanup has a dedicated
directory; it cannot clear the live runner database or persistent server log.
CI artifact paths follow this layout and explicitly include hidden directories.
CI also runs the existing dependency-free JavaScript amount/allocation tests
through `npm run test:unit`.

The 78 application browser specs are grouped into nine domains: banking,
categories, dashboard, investments, planning, transactions, ingestion, catalogue
and shared. Their 475 test declarations, project assignments, expected statuses
and annotation payloads remain present. Shared helpers own repository paths and
bounded catalogue routing instead of duplicating seven catalogue loaders. The
[test index](../../tests/README.md), [contributor guide](../../CONTRIBUTING.md)
and [agent contract](../../AGENTS.md) describe the new ownership.

All 420 recorded runtime-source hashes match the starting revision, including
Django apps and their Python tests, templates, static assets and translations.
The Tailwind rebuild is byte-identical to committed CSS. Existing environment,
database, backup, dependency and diagnostic entries were preserved; their paths
were not migration inputs. No app package moves to `apps/` or `src/`.

## Validation

Validation ran locally on Linux with synthetic data and the existing locked
dependencies. Browser commands used the official disposable runner and
Chromium, with desktop and emulated phone cases in both themes. No test pointed
at the personal installation database or server.

| Check | Observed result |
|---|---|
| Version consistency, Django system checks and migration check | Passed; no pending model changes. |
| Full Django suite | 723 tests passed. |
| Combined line/branch coverage | 95% under the existing measurement scope and 70% floor. Executed tests and migrations remain included; this is not application-only coverage. |
| Python repository-tool suite | 32 tests passed. |
| JavaScript amount/allocation suite | 16 tests passed through `npm run test:unit`. |
| Static tour browser suite | 6 tests passed; its test inventory is unchanged. |
| Application browser suite | 469 unique cases passed after the full traversal and focused reruns; 6 existing paused-import cases remained skipped. |
| Lock consistency, focused Ruff rules and whitespace checks | Passed. |
| Compiled CSS and runtime preservation | Byte-identical CSS and 420 unchanged runtime-source hashes. |

The application browser inventory was traversed in three disposable shards:
the first pass produced 440 passes, 29 failures and 6 skips. The failures exposed
test expectations from before the approved interface refactor: selected names
inside neutral payment filters, old marker containers, links without their
retained return context, outdated translated copy, and a help-icon Tab stop.
One category-history case also clicked an old tree before the Clear response
finished. These tests now assert the current identity, context and completed
transition. Financial totals, ownership, native fallback and keyboard checks
remain in place.

Focused passing reruns covered all 29 failed cases and two previously passing
native cases. Repeated cases replace their earlier result; they are not added
to the 475-case inventory. The final 469/6 result therefore combines the complete
traversal with those reruns, rather than describing one clean full-suite
invocation. No new skip was introduced. The six retained skips belong to the
deliberately paused statement-import interface.

Raw shard reports, rerun logs and the unique-case reconciliation were inspected
locally; generated evidence is not a tracked runtime dependency. Current output
locations are documented in the test and contributor guides.

## Remaining scope

The later lots—app-internal Python organization and larger frontend/document
splits—remain separate work. Neither a broad architecture migration nor
performance improvement is claimed here.

Real Docker execution, physical mobile devices, other browser engines, remote
CI, dependency vulnerability audits and release/publication checks were not run
as part of this organization round. Tooling tests cover the Docker command
contracts without establishing that a container was built or run.
