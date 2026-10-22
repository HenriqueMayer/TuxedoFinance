# Project health review — 2026-10-16

**Dated evidence:** findings, validation counts and measurements describe this
maintenance review, not the present checkout's test status. Use the
[documentation index](../README.md), owning app guides and
[frontend contracts](../frontend.md) for current behavior; the
[review archive](README.md) retains the subsequent interface evidence.

This review covers the local-first application on
`feat/personal-finance-evolution`, starting at `5b7382a`, and the subsequent
unreleased maintenance in this working tree. It compares the implementation
with the owner-supplied architecture/refactoring report and interactive summary.
The supplied material is architectural analysis, not a personal financial
statement. Its originals remain unchanged outside the repository.

## Verified findings and maintenance

| Finding | Decision and acceptance evidence |
|---|---|
| HTMX restored private HTML by URL after logout and another login. Native BFCache restored Alice's frozen document after Bob logged in through another tab; native form history also restored unsent values onto Bob's fresh HTML. | Disable DOM snapshots, purge legacy caches and reauthorize history with server GETs. Mark authenticated HTML private/no-store, guard persisted returns and disable native draft restoration on editable private POST forms. Restore only identity-checked snapshots over authorized defaults. Cover anonymous history, user changes, another tab, no-JavaScript and asset/login recovery. See [private history](../frontend.md#private-history). |
| A BRL transfer could debit 100 and credit 150 without another financial event. | Require equal amounts for same-currency endpoints; retain cross-currency FX evidence and explicit fees as separate activity. Cover rejected creation without partial posting and unchanged cash. |
| A future FX rate changed current-month realized spending and disagreed with budgets. | Use the realized cutoff for realized occurrences, including category/source composition. Only future occurrences use forecast month-end rates, so FX revaluation cannot create remaining planned spending. |
| Several cash endpoints accepted operations before a known account opening. | Share the date guard across transfers, investments, loyalty, payments and transactions. Preserve unknown dates and provide read-only legacy-conflict inspection. |
| Category edits admitted descendant cycles, while import used a separate rule. | Share graph validation, exclude descendants from the existing picker and revalidate in the atomic save. Keep legacy relationships readable and repairable. |
| Category CSV could raise an uncaught parser error or silently discard columns. | Bound bytes/records, require the exact structure and reject malformed input before atomic import. Cover BOM/Unicode/quoted multiline round trips and recovery. |
| Empty foreign accounts produced missing-FX warnings. | Convert zero to zero without a rate. Nonzero recorded cash, reserves and unpaid obligations retain missing evidence even when they offset to a zero net forecast. |
| Canonical catalogue/reviews described superseded navigation and help. | Align the catalogue and its browser assertions; label delivery reviews as historical and link the current contracts. |
| Full browser validation exposed stale month/account navigation tests and a month panel that closed during internal Shift+Tab. | Align tests with the current controls and bank workspaces. Preserve internal focus transfers using `relatedTarget`; retain month/history assertions across themes, languages and mobile. |

The accounting sources of truth, URLs, native fallbacks and migration chain
remain intact. No source records are automatically repaired. The root layout
retains Django's domain apps and shared manifests; runtime databases, backups,
environment files, dependencies and local results are not cleanup targets.

## Financial boundaries and decisions still open

- Points purchases contribute to monthly expenses and their cash-flow
  composition, but category budgets and account/card/category/recurrence breakdowns
  currently cover categorized transactions. This limitation is now explicit in
  the [report contract](../apps/dashboard.md#coverage-of-expense-breakdowns).
  Adding a category or budget treatment requires a separate decision; another
  cash movement must not be invented to reconcile the breakdowns.
- The automatic invoice mode derives settlement from the due date. Manual mode
  records explicitly confirmed payments. Changing the default or relabeling
  the workflow is a product decision, not part of these financial corrections.
- A decrease in a monetary position may represent a loss or internal fee.
  The positive-yield workflow currently does not model this. A withdrawal is
  appropriate only when it actually credits a bank account; do not use it to
  represent an internal loss. A negative-adjustment workflow remains open.
- "Projected (month)" is monthly activity without an opening balance. Renaming
  it, setting stale-price thresholds and choosing the installation's financial
  timezone remain separate decisions. Existing UTC/application versus system
  calendar calls require a dedicated boundary test before a timezone change.
- Statement import and net-worth interfaces remain paused under the existing
  [roadmap](../roadmap.md). This maintenance does not reactivate either one.

## Assessment of external proposals

| Proposal | Current assessment |
|---|---|
| WAL, IMMEDIATE and a shared conversion context as new foundations | Already present. Measure remaining costs instead of repeating the implementation or lowering timeout automatically. |
| Split services/selectors and shared financial commands | Useful for a distinct responsibility or demonstrated duplication. No blanket app relocation, DTO layer or file-length threshold is justified. |
| Monthly persisted snapshots and mutation-version tables | Add invalidation and compatibility obligations. Existing diff reconciliation and guarded undo should be replaced only for a reproduced failure or measured cost. |
| CSV fuzzy matching as automatic identity | Similarity is not identity: two equal payments on the same day may be legitimate. Retain explicit review when bank IDs are unavailable. |
| Idiomorph as a universal solution for focus/history | The app already has tested control, viewport, disclosure and history contracts. A new runtime must solve a measured problem without losing those guarantees. |
| Immediate reactivation of net worth/imports | Their engines partly exist; the remaining gate is a deliberate product/usability review. |

The supplied interactive benchmark scores and latency values are constants with
no documented measurement method, dataset or environment. Treat them as
illustrations. Its split simulator also fails to preserve category totals:
100 in seven installments at 60%/40% produces 60.01/39.99. The application already
preserves both category and installment totals and retains that algorithm.

The SQLite claims also need qualification. WAL permits one writer at a time;
`IMMEDIATE` does not eliminate all contention. Keep transactions short and
measure before adding memory/cache settings. Sources:
[SQLite WAL](https://www.sqlite.org/wal.html),
[Django SQLite transactions](https://docs.djangoproject.com/en/6.0/ref/databases/#transactions-behavior).
The supplied competitor, tax and advisory claims have not been revalidated here
and are not evidence for product superiority or a new financial rule.

## Reproducible reporting measurements

Run from the repository root with the locked Python environment:

```bash
uv run python scripts/benchmark_reporting.py --samples 20 --output test-results/reporting.json
```

The command always owns a temporary database, environment file and signing key.
Its worker refuses an already configured Django installation. Each record count
runs in a fresh process, seeds five years of synthetic BRL spending, projects the
ledger once and measures warm synchronization and full authenticated dashboard
and report GETs. Up to twelve sources recur monthly; roughly 10% of the remaining
sources use six credit installments. It accepts no database/server target.

The JSON records median/p95 latency, SQL count, financial write count and peak
Python allocations. Timing excludes seeding, the initial sync, SQL capture and
memory tracing. Memory is a separate warm call's Python heap peak, not process
RSS. These are local Django test-client observations on a shared development
host; they exclude HTTP transport, browser rendering, cold caches and concurrent
SQLite writers. The source revision and working-tree status travel with results.

The first measured optimization reuses one owned, request-local transaction list
across the report's evolution, instrument and recurrence charts. Previously each
chart loaded and hydrated the same history and split relations independently.
Explicit shared sources are checked for ownership; their lifetime ends with the
request. No persisted snapshot, global cache or new service was introduced.

Observed report GETs, twenty warm timing samples per case:

| Sources | Median ms before → after | p95 ms before → after | SQL before → after | Peak Python MiB before → after |
|---:|---:|---:|---:|---:|
| 0 | 71.4 → 69.1 | 74.1 → 73.1 | 84 → 82 | 0.829 → 0.834 |
| 1,000 | 382.1 → 237.8 | 563.3 → 248.0 | 88 → 84 | 14.950 → 6.661 |
| 10,000 | 3,121.1 → 1,648.2 | 3,404.9 → 1,689.3 | 88 → 84 | 70.430 → 53.289 |

The 10,000-source report median fell about 47%, with about 24% fewer peak Python
allocations in the separate memory probe. Every profiled warm operation issued
zero financial writes and the movement counts were identical before/after.
Dashboard and synchronization were controls: at 10,000 sources their median
times changed from 1,456.1 to 1,476.4 ms and 627.1 to 637.0 ms respectively;
neither was the optimization target. Small timing variations are not evidence
of a general improvement or regression on a shared host.

Environment: Python 3.12.13, Django 6.0.8, SQLite 3.50.4, Linux x86_64,
`DEBUG=True`, cutoff 2026-10-16. See the
[raw measurement snapshot](project-health-2026-10-16-performance.json) for
all counts, memory probes, synchronization times and method metadata.
These results do not establish concurrent-write capacity or production latency.

## Validation

These are dated results for the maintenance batch, before the separate
catalogue-only visual experiment. Later work may add browser scenarios.

All database/server checks used disposable installations. No owner database,
signing key, active server, Docker volume or downloaded original was modified.

- The complete Django suite passed **624 tests** with **94% combined branch/line
  coverage** under the existing measurement scope. The separate executed
  application-only diagnostic was **90%**; see the
  [coverage policy](../coverage-baseline.md). The nine asset/privacy unit tests
  also passed again after the final browser changes.
- **19 repository-tool tests** and **6 static-preview browser tests** passed.
- Django system checks, version consistency and the pending-migration check
  passed. Focused executable-correctness lint, JavaScript syntax,
  `git diff --check`, documentation links and the benchmark JSON were checked.
- A temporary CSS rebuild matched the committed asset. Gettext checks passed
  with **1,619 translated messages**, no fuzzy or untranslated entries, and the
  compiled Portuguese catalogue was updated.
- Python/npm dependency audits passed during the diagnosis in this session;
  this maintenance did not change dependencies or lockfiles.

Browser validation was iterative rather than one final all-green invocation.
The complete application run collected **268 cases**: **248 passed, 14 failed
and 6 were already skipped**. Failures exposed incorrect new fixtures, stale
month/account navigation expectations and the internal month-focus defect.
Those issues were fixed without weakening financial or ownership assertions.
The affected files then passed through the official isolated executor:

| Final targeted verification | Result |
|---|---:|
| Banking integrity: both themes and native recovery | 3 passed |
| Category hierarchy/CSV: both themes and native recovery | 3 passed |
| Monthly workspace, compact month choice and report months | 22 passed |
| Planning workspace and owned reserve navigation | 3 passed, 2 already skipped |
| Private history, previous-workspace recovery and asset refresh | 22 passed |
| Native/no-JavaScript regressions after private-form protection | 51 passed, 1 already skipped |

Three additional privacy regressions raised the final inventory to **271
cases**. All **265 active scenarios** have passing evidence across the complete
run and targeted repetitions; **6 paused-import cases remain skipped**. Counts
in the table overlap and must not be added together. There was no further full
invocation after the final corrections. The privacy cases require an actual
`pageshow.persisted` BFCache event and a fresh authorized GET, with no POST
replay; they also verify a clean field after account changes and native invalid
POST recovery followed by an explicit save.

Browser evidence is from bundled Chromium. Docker lifecycle/image validation
and other browser engines were not exercised by this maintenance. No release,
merge or publication was performed.
