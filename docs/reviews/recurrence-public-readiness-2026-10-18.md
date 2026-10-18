# Recurrence guard and public documentation — 2026-10-18

**Outcome: fixed.**

This delivery starts from `2ebeeb3` and addresses the recurrence resource finding
and nine documentation observations from the repository's public-readiness
review. The owner approved a limit of **1,200 projected monthly occurrences per
transaction**. Publication, merge and release remain outside this delivery.
The current contract lives in the
[Transactions guide](../apps/transactions.md#recurrence-projection-and-recovery).

## Finding and enforcement

An authenticated transaction POST could submit an open-ended fixed schedule
starting in year 0001 against an owned account with an unknown opening date.
The original isolated reproduction generated 24,322 derived movements in about
4.11 seconds and held another SQLite writer for about 4.04 seconds. This was a
low-severity authenticated resource-exhaustion finding, not an ownership bypass.
Those measurements describe the pre-patch reproduction, not a performance
benchmark or the current implementation.

The patch uses the existing model-validation and ledger-service boundaries.
`transactions.projection` calculates each source's actual effective/billed
window arithmetically. Short ended historical schedules, one-off purchases and
installments no longer traverse unrelated empty calendar years. Excessive fixed
schedules fail with a field error before normal form writes. Direct-ORM and
legacy sources fail service preflight before the service acquires SQLite's
writer; source state is checked again inside its atomic transaction before
backfill, reconciliation or deletion. An existing caller can already own a
source-write transaction; ordinary guard failures roll that workflow back.

The bound counts actual occurrences through the requested projection horizon,
normally twelve months ahead. It accepts 1,200 and refuses 1,201, without an
arbitrary minimum date or automatic truncation. No schema or data migration is
introduced. Financial calculations, category allocations, installment cents,
credit billing offsets, source keys and confirmed invoice payments retain their
existing contracts.

Implementation changes belong to the
[schedule policy](../../transactions/projection.py),
[model validation](../../transactions/models.py),
[ledger service](../../transactions/services.py),
[recovery middleware](../../transactions/middleware.py),
[editing views](../../transactions/views/editing.py) and
[middleware registration](../../core/settings.py).
Regressions live in the owning
[guard tests](../../transactions/tests/test_projection_guard.py),
[historical projection tests](../../transactions/tests/test_projection_limits.py),
[Reports query contract](../../dashboard/tests/test_reporting_efficiency.py) and
[browser spec](../../tests/e2e/transactions/recurrence-limits.spec.js).

## Recovery and independent review

Financial GETs that encounter an excessive legacy source return to the owned
Transactions list with an explanation. Native requests use a redirect; HTMX
and asset-aware requests receive an empty HTTP 200 with `HX-Redirect`, so a full
Transactions page cannot be swapped into a Reports chart island. Bound create
and update failures retain their unsaved values and do not emit success notices.

Multiple excessive sources can be explicitly repaired or deleted one at a time.
Such owner-directed repairs preserve derived movements and invoices unchanged
while another blocker remains, display a pending-synchronization warning, and
keep synchronized financial consultation blocked. The last repair permits full
reconciliation. Ordinary unrelated writes still roll back when blocked.

A fresh read-only investigator traced the original boundary before the patch.
A separate fresh read-only reviewer inspected the candidate after focused
tests. Both concrete review findings were confirmed and corrected: sequential
legacy recovery and HTMX island redirects. Dedicated regressions cover each;
no second review cycle or broader architecture change was introduced.

## Documentation corrections

The public guides now accurately describe the current static captures rather
than an assumed published release; seven preview sections; version-check
consistency without an immutability guarantee; local historical implementation
evidence; HTMX 2.0.10's 0BSD license; the default paused import queue; the actual
`/i18n/setlang/` endpoint; the approved mobile-label exception; and an ordinary
expense rather than a removed investment transaction type in the catalogue.

The owning Transactions, architecture and data-model guides describe the guard
and explicit recovery behavior. The English and Brazilian Portuguese catalogues
include all three new notices. Comparing the compiled catalogue with the base
commit found three additions and no changed existing translation; generated
source references also follow the earlier module moves.

## Verification

Validation uses the temporary installation settings in
[Contributing](../../CONTRIBUTING.md#python-checks) and the disposable
`npm run test:e2e` executor. No check targets the installation's database,
environment file, backups or developer server. Test identities and financial
fixtures are synthetic.

The original exploit is now refused with HTTP 200 and a bound date error,
without a saved transaction or movement, for account, PIX, debit and credit
channels. Direct-ORM sources also fail before `BEGIN` or any projection write.
Controls preserve an ended January–March year-0001 history, shifted final card
bills, exact historical amounts and idempotent identifiers/timestamps. Boundary
checks cover 1,199, 1,200 and 1,201 occurrences, including partial horizon days.
Other regressions cover source changes between preflight and locked reads,
cross-user isolation, sequential repair/deletion, rollback and success notices.

| Check | Current result |
|---|---|
| `uv run coverage run --branch manage.py test`, isolated | 745 passed in 179.2 seconds |
| `uv run coverage report --show-missing --fail-under=70` | Passed; 95% with the repository's current configuration, which includes tests and migrations |
| Focused projection, split, ledger and reporting tests | 46 passed |
| `uv run python -m unittest discover -s tests/tooling`, isolated | 40 passed |
| `npm run test:unit` | 16 passed |
| `manage.py check`, `makemigrations --check --dry-run`, isolated | Passed; no migration changes |
| `uv run python scripts/check_version.py` | Version 0.10.0 is consistent |
| `uvx --from 'ruff>=0.9,<1' ruff check . --select F --ignore F401` | Passed |
| `npm run build:css -- .local/test-results/recurrence-app.css` and `cmp` | Passed; committed CSS is unchanged |
| `msgfmt --check-format` and compiled-catalogue `cmp` | Passed |
| `uv run python scripts/check_docs.py` | 60 documents, 538 local references, none unresolved |
| `git diff --check` | Passed |

The first full Django run executed all 745 cases and found one outdated query
expectation: Reports now has an additional preflight source read before the
writer. The regression still requires one shared categorized read across all
chart islands, correct financial totals and no unchanged ledger writes. After
that expectation was updated, the focused 46 and final full 745 passed.

`npm run test:e2e -- tests/e2e/transactions/recurrence-limits.spec.js` passed all
seven cases in 25.3 seconds. They use real keyboard events, desktop/phone,
light/dark, a no-JavaScript phone correction and long names. Screenshots show
the selected instrument and bound errors remain readable and final actions
remain above the mobile dock. The two Reports browser cases emulate the
middleware's empty-200/`HX-Redirect` response on a real HTMX period request;
Django tests independently exercise the real exception response. The browser
then requires full navigation and removal of the old chart regions and balance.
The Portuguese error is also checked through a real Django POST.

An integrated browser run selected the existing catalogue, banking integrity,
reserve controls, reward redemptions, forecasts, Reports periods, shared design
and payment/split specs through `npm run test:e2e`. It used
`--output=.local/test-results/recurrence-existing-browser` and initially passed
80 of 82 cases in 6.6 minutes. Both reward-redemption cases stalled during
native pointer actionability checks; their final native save assertions were
not reached. A separate repeat reproduced the stalls and was stopped after
the first two repeated failures, without changing assertions or timeouts.

The unchanged two-case reward spec also failed against an archived copy of
`2ebeeb3`, with the same native click stalls. Playwright's installed retry code
uses an in-page 20ms timer after initial element instability; a separate blank
page probe confirmed this timer stays pending when JavaScript is disabled.
The existing 180ms bank-panel entry animation triggered that retry. This was
a pre-existing test-harness failure, not a changed financial result.

The [reward regression](../../tests/e2e/banking/reward-redemptions.spec.js) now
uses runner-side polling to wait for the existing animation to finish before
the two native pointer actions. It preserves both real `.click()` calls, every
assertion, the original 30-second timeout and the application's motion. That
test-only correction passed both archived baseline cases in 19.3 seconds. On
the current source it passed 2/2 in 19.5 seconds, then 4/4 in two additional
repetitions in 39.3 seconds. The final native edit/save and exact IOF amount
assertions were reached and passed in both languages/viewports.

Together, the seven new cases, 80 initially passing existing cases and two
corrected existing cases provide passing results for **89 distinct selected
browser scenarios**. The initial integrated run was not clean; its failures
and the interrupted redundant repeat remain recorded rather than reported as
passes. No test was skipped and no timeout increased.

Ignored evidence remains under `.local/test-results/recurrence-public-review/`
(13 inspected screenshots), `recurrence-existing-browser/` (initial integrated
failures), `recurrence-redemption-recheck/` (unmodified repeat), and
`recurrence-rewards-animation-browser/` / `recurrence-rewards-animation-repeat-browser/`
(final pointer checks). The tracked-tree baseline copy and its original/fixed
artifacts remain under `recurrence-baseline-vh_4vkml/` in the same ignored tree.
All runners disposed of their owned databases and stopped their servers.

## Limits

This is a targeted fix and documentation correction, not a new repository-wide
security audit. The complete application browser inventory was not rerun;
the selected 89 scenarios and full Django suite define this validation scope.
The per-source bound does not provide an aggregate user quota
or multiple concurrent SQLite writers. Existing installations are not rewritten
or silently reconciled during delivery. Docker images, hosted deployment,
remote CI, merge, tags and publication are not exercised or performed.
