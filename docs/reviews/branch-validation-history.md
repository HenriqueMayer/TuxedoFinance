# Branch validation history

**Historical evidence:** these dated records were moved from
[`branch-testing.md`](../branch-testing.md), preserving the reported results,
limitations and iteration chronology. They describe earlier checkouts, browser
fixtures and previews, including interaction patterns subsequently replaced.
They are not a current test report or instructions to recreate old navigation.

Use the [current owner walkthrough](../branch-testing.md),
[interface map](../interface-map.md), [frontend contracts](../frontend.md) and
[developer checks](../../CONTRIBUTING.md) for present behavior. Publication and
owner acceptance remain separate decisions. Local preview ports, runtime
versions and test counts below are historical observations.

## Automated validation


Local validation on 13 October 2026 used synthetic or disposable databases:

- All 470 Django tests passed, with 93% coverage in the repository's configured
  coverage scope. All 15 repository-tool tests passed.
- All 165 browser scenarios were verified: 149 passed in the complete run and
  the 16 affected scenarios passed after their fixes in an isolated rerun.
  All six existing static-tour tests passed.
- A synthetic database with the v0.10.0 schema was copied and upgraded through
  the preview helper. The original file hash, schema, automatic invoice and
  cash movement remained unchanged; the upgraded copy served the login page.
- The local Docker image built successfully and passed installation, recreation,
  persistence, backup/restore and idempotent-migration smoke checks. All 13 new
  browser scenarios also passed against that disposable container installation.
- Django checks, the migration dry run, version consistency, executable lint,
  translation format/compiled-output checks, reproducible CSS, the pinned HTMX
  checksum and `git diff --check` passed. npm and the locked Python runtime
  dependency audits reported no vulnerabilities.

The local environment used Python 3.12.13 and Node.js 22.23.3. Docker checks ran
on Linux amd64 with Engine 26.1.5 and Compose 5.6.0; they do not certify arm64 or
replace the documented Engine 28+ installation baseline. Manual acceptance on
the owner's financial data remains pending, using the disposable preview above.

### Initial navigation and UI/UX iteration — 14 October 2026

Validation of the initial navigation changes also used synthetic or disposable
databases:

- All 521 Django tests passed in the final complete run, with 94% coverage in
  the configured scope. All 17 repository-tool tests passed.
- All 186 interactive browser scenarios were verified: 150 passed in the
  complete run, and the remaining 36 passed in isolated reruns after fixes.
  The ten affected transaction, goal and import scenarios were checked again
  after the final keyboard and review-continuity changes and passed. All six
  static-tour tests also passed.
- Browser checks cover desktop and mobile viewports, English and Portuguese,
  both themes, real keyboard events, touch and native submissions without
  JavaScript. The Portuguese bottom bar was checked at 320px while navigating
  through all five destinations, including their active labels and touch targets.
- Django checks, migration dry run, version consistency, executable lint,
  JavaScript syntax, translation format/compiled-output checks, reproducible CSS,
  pinned HTMX and `git diff --check` passed. npm and locked Python runtime
  dependency audits reported no known vulnerabilities.

That initial UI/UX iteration added no migrations or dependencies. The previous container
lifecycle checks were not repeated. Browser checks use Chromium; acceptance on
the owner's actual computer, phone and financial data remains pending. Banks,
Cloudflare, deployment and integration into `main` remain outside this iteration.

### Area-by-area simplification — 14 October 2026

The completed area-by-area simplification was verified with synthetic or
disposable databases, before the later compact-control and category-graph changes:

- All 563 Django tests passed with 94% combined coverage in the existing scope
  (including executed test modules and migrations). All 17 repository-tool tests
  and all six static-tour tests passed.
- All 212 active interactive browser scenarios were verified across the complete
  run and focused reruns. Six statement-operation scenarios are intentionally
  skipped while that interface is paused; separate tests cover the server gates,
  stale POST rejection and owned read-only import history.
- The final 29-scenario rerun covers live-filter races, preferred-date errors,
  typing/deleting/Clear, fresh Back/Forward restoration, the monthly workspace in
  both languages/themes at desktop/mobile widths, and preserved POST/simulation
  history. A pending-query regression first reproduced mismatched text/results
  before the minimal fix, then passed in both themes. Keyboard, touch and native
  submissions without JavaScript remain covered.
- Django checks, migration dry run, version consistency, executable lint,
  JavaScript syntax, translation format/compiled-output checks, reproducible CSS
  and `git diff --check` passed. npm and the locked Python runtime dependency
  audits reported no known vulnerabilities.
- A synthetic `investments.0009` database was copied with the read-only SQLite
  backup helper and upgraded to `0010`. Default participation, the 1,300 BRL
  available balance and an existing automatic card remained correct; the
  original database hash stayed unchanged.

This iteration adds `investments.0010_position_planning_setting`, an additive
table for explicit cash-position participation. Existing positions remain
included by default; no source balances or operations are rewritten. The preview
helper applies it only to the disposable copy. No dependencies or version changes
were introduced, and the previous Docker lifecycle checks were not repeated.
Browser checks use Chromium and simulated desktop/mobile viewports; acceptance
on the owner's actual computer, phone and data remains pending. No merge into
`main`, publication, bank connection or Cloudflare deployment is authorized by
these automated checks.

### Compact consultation and category graph — 14 October 2026

- The full Django run passed all 571 tests with 94% combined coverage in the
  existing scope (including executed test modules and migrations). Follow-up
  checks passed all 33 category/localization tests after the graph-origin
  refinement and all eight banking-organization tests after the bank changes,
  against disposable databases.
- All 230 active interactive browser scenarios were verified across the broad
  run and focused reruns. Six statement-operation scenarios remain intentionally
  skipped while their interface is suspended. The broad executor was terminated
  near its end; the final 47-scenario group completed the remaining layouts and
  verified the corrected category menus, graph origins, Portuguese graph, live
  filters, asset refresh and transaction keyboard/viewport behavior.
- The graph initially reproduced a stale parent selection after a new child
  search. The final regressions require the unique matching node to be selected
  and entirely visible, retain search focus/page scroll, and preserve deliberate
  ancestor fragments through editor Cancel. Real touch pan/pinch and the complete
  native hierarchy are covered separately.
- All 17 repository-tool tests and all six static-tour tests passed. Django
  checks, migration dry run, version consistency, executable lint, JavaScript
  syntax, translation format/compiled-output checks, reproducible CSS and
  `git diff --check` passed. npm and the locked Python runtime audits reported
  no known vulnerabilities.

This iteration adds no migrations, dependencies or version change. The
published static tour remains unchanged; container lifecycle checks were not
repeated. Browser checks use Chromium and simulated desktop/mobile viewports,
with English/Portuguese, both themes, real keyboard events, touch and native
submissions. Acceptance on the owner's actual devices and data remains pending.
The roadmap exists only in documentation. No merge into `main`, publication,
bank connection or Cloudflare deployment is authorized by these checks.

### Stable controls, organic network and compact Banking — 14 October 2026

This iteration was checked using synthetic or disposable databases:

- All 572 Django tests passed. A final 49-test category, localization and Banking
  run also passed after the last markup refinements; Django checks and the
  migration dry run reported no issues or pending model changes.
- All 106 selected interactive browser scenarios passed across the scoped runs:
  61 cover Transactions, category disclosures/network, Banking organization and
  consultation months; 35 cover live filters, contextual actions, FX, reserves,
  payments/splits, rewards, asset refresh and navigation; ten cover shared form
  choices, conditional transitions, error recovery and native submissions.
- The two explicit classic-scrollbar cases launch Chromium without hidden or
  overlay scrollbars. Their JSON evidence records identical toolbar boxes and
  a retained 8px layout gutter in this local browser, while the rendered
  scrollbar disappears for the short list. Every compared control keeps its
  position and dimensions within 1px. The tests measure actual layout width:
  root `clientWidth` excludes only a rendered scrollbar and cannot alone measure
  a reserved empty gutter.
- Graph checks exercise settling/reduced motion, visual mouse/touch/keyboard node
  arrangement, real links, exact unchanged JSON sources and no financial POSTs.
  Repeated Shift+arrows retain visible focus inside the canvas. Month checks
  include a 390×480 viewport, internal result scrolling and deliberate dismissal
  by an outside wheel gesture. Native controls remain available without JavaScript.
- All 17 repository-tool tests and six static-tour tests passed. JavaScript
  syntax, executable lint, version consistency, translation format and compiled
  output, reproducible CSS and `git diff --check` passed.

No migrations, dependencies or version changes were introduced in this iteration.
The shared picker change is an explicit opt-in for fixed month popups; ordinary
form choices retain their existing scrolling contract. Dashboard, Reports,
Investments and Plan retain their existing implementation. The public static tour
is unchanged, and Docker lifecycle checks were not repeated. Automated browser
checks use Chromium and simulated desktop/mobile input; acceptance on the owner's
actual devices and data remains pending. No merge, publication, bank connection
or Cloudflare deployment is authorized by these checks.

## Performance evidence

Measurements are synthetic local observations, not production guarantees. They
use loopback Django requests, three samples per operation, a 24-month fixture
with recurring and installment transactions, and no personal data. SQL totals
include transaction-control statements.

| Transactions | Warm sync median | Warm sync SQL / writes | Dashboard median | Dashboard SQL / writes | Reports median | Reports SQL / writes |
|---:|---:|---:|---:|---:|---:|---:|
| 30 | 36.58 ms | 7 / 0 | 326.52 ms | 71 / 0 | 650.64 ms | 88 / 0 |
| 300 | 202.05 ms | 7 / 0 | 473.19 ms | 71 / 0 | 684.35 ms | 88 / 0 |
| 1,000 | 333.97 ms | 7 / 0 | 1,228.98 ms | 71 / 0 | 1,645.86 ms | 88 / 0 |

The original diagnostic's 1,000-transaction fixture recorded 17,248 SQL
statements and 4,310 writes for warm synchronization. Its fixture and date differ
from the final measurement, so these numbers do not establish a like-for-like
percentage speedup. The reproducible invariant is narrower: unchanged
projections perform no data writes, and the measured query counts remain
constant across these three fixture sizes. Focused regression tests cover that
invariant, correct source updates and missing exchange rates.

The final fixture spans November 2024–October 2026, with 20% recurring and 25%
credit transactions, some six-installment purchases, and a projection horizon
through October 2027. At 1,000 records, observed ranges were 307.60–427.21 ms
for synchronization, 983.33–1,398.55 ms for Dashboard and 1,533.19–2,249.41 ms
for Reports. Source-transaction field hashes stayed unchanged at all sizes.
Database size, price history, currency mix, hardware and cold caches can change
timing. Request-time synchronization still uses an atomic transaction and SQLite
still serializes writers; the improvement does not introduce concurrent writes.

After manual acceptance, the owner decides which adjustments remain and when to
integrate the branch. A successful automated run does not replace that decision.


### Bank pages, simpler categories and shared shell — 15 October 2026

- All 574 Django tests passed; coverage measured with `--branch` was 94%. Django system checks and
  migration-drift checks passed; a final 22-test Banking/category subset passed
  after the fragment navigation adjustments. No schema or dependency changes
  were introduced in this iteration.
- Selected real-browser coverage passed 110 distinct scenarios across scoped
  batches and focused rechecks. It covers desktop/mobile viewport sizes, both
  themes, Portuguese/English, keyboard/touch, native GET/POST/help without
  JavaScript, fixed category filter geometry, retained account/card actions,
  reserves, invoice payments, FX, history and shared help/footer behavior.
- Initial interaction runs exposed deferred horizontal scroll from a preceding
  card search dismissing the month popup, and boosted record links failing to
  reveal the collapsed bank history. Both received focused fixes and passed
  rechecks. The action-only POST fixture now explicitly includes its account
  in planning; history tests deliberately reopen the default-collapsed section
  after reload instead of selecting inaccessible headings.
- All 17 tooling tests, executable-correctness Ruff, version consistency,
  `git diff --check`, local documentation links, CSS reproducibility and gettext
  format/compiled-byte checks passed. The catalog has no fuzzy or untranslated
  active Portuguese entries. Synthetic desktop/mobile screenshots were inspected
  in both themes; generated screenshots remain local evidence.
- Accounts now opens institution links and dedicated bank pages, with no
  overview text search. Account amounts, daily card actions and configuration
  are grouped by account; Recent activity is secondary. Categories retains one
  collapsed native hierarchy and removes the graph. The shared footer is quiet,
  and mouse help closes immediately at the question-mark boundary.
- The local preview was restarted on loopback port 8768 from a verified backup
  of its existing disposable database. Its saved test records were retained;
  the installation database was not migrated or changed. No new demo data or
  test accounts were inserted into that preview by the browser suite.
- Acceptance on the owner's actual computer/phone and preferred browsers is
  still pending. Dashboard, Reports, Investments and Plan domain/view templates
  remain unchanged; the authorized shared footer/help changes apply there too.
  Docker, integrations and deployment were outside this iteration. No merge,
  main push, tag, release or publication was performed.


### Refined filters, cash-pot cards and invoice navigation — 16 October 2026

- All 579 Django tests passed with 94% coverage measured using `--branch`.
  System checks and migration-drift checks passed. Five focused invoice tests
  passed again after canonical card-link rendering was finalized.
- Selected browser coverage passed 52 distinct scenarios across the scoped run
  and focused rechecks: real keyboard/touch input, both themes, PT-BR/English,
  native GET/POST, invoice payments, compact cash-pot cards, card overview and
  history, invalid-date contrast and Back/Clear context. Transaction geometry
  remained stable from 320 to 1536px and with classic desktop scrollbar gutters.
- Initial fixture failures correctly rejected opening dates on zero-valued
  configured assets. Those fixtures now omit the nonexistent opening date.
  Search checks distinguish a card's full name from the shared account name;
  canonical card links omit empty query markers. No financial validation was
  relaxed. Final focused rechecks passed.
- Cash-pot and invoice-overview screenshots were visually inspected on desktop
  and mobile in both themes. Transaction selection/border screenshots and native
  Portuguese labels were inspected too. Card counts, ownership, empty cards,
  legacy card-filter redirects and independent card/history pagination have
  dedicated server coverage.
- Ruff, `git diff --check`, CSS reproducibility and gettext format/compiled-byte
  checks passed. No migrations or dependencies changed. The manual preview was
  restarted on loopback port 8768 from a verified backup of its active disposable
  database, preserving its test records and leaving the installation untouched.
- Actual device/browser acceptance remains with the owner. No merge, main push,
  version/tag, image, release, bank integration or publication was performed.


### Clearer Investments and Plan — 16 October 2026

- Investments now uses one divided list with aligned holding, registered-value
  and Update columns. The phone layout retains the same information and its
  explicit row anchor. Purpose and history criteria remain available through a
  stable More filters rail. Text search does not silently redefine the scoped
  total, and acquisition-cost/missing-price warnings remain visible.
- Update uses a compact action list. Native Cancel navigation honors the
  validated position fragment instead of returning to the heading. Check both
  Cancel from the chooser and Cancel from an operation form on a phone.
- Plan puts the selected month beside its title and distinguishes the projected
  month-end amount from recorded available cash and reserved balances. The month
  picker resets to This month; optional month filters elsewhere still reset to
  all months. Budgets share aligned rows with forecasts/options in context.
- Goals show backed reserved progress against the goal, explicit goal-amount
  labels and visible shortfall/FX notices. Tools groups simulations separately
  from local signals and saved drafts. Existing fields, financial calculations,
  date validation and owned return contexts retain their contracts.
- Owner review: switch themes and months, type/delete a search, open/close More
  filters, check Clear and Back/Forward, update a holding and cancel to its row,
  edit/copy/remove a budget, and inspect a funded goal and each Tools destination.
  The desktop and phone previews use the same branch; device acceptance remains
  with the owner before any merge or publication.

Validation for this iteration:

- All 579 Django tests passed with 94% coverage measured using `--branch`;
  system and migration-drift checks passed. All 42 Planning tests passed again
  after the final goal-label changes.
- Scoped browser runs and focused rechecks passed 50 distinct scenarios, with
  no unresolved failures: keyboard/touch, 390/1440px, light/dark, English/PT-BR,
  native forms, errors and conditional choices, owned row returns, live filters,
  required/optional month resets, Back/Forward, budgets, goal backing, archive/
  restore and existing calculation flows. Required label markers and deliberately
  overlaid menus are accounted for in the interaction selectors.
- Screenshot review covered desktop/phone holdings, monthly outlook, budgets,
  funded-goal progress and grouped tools. Native progress styling now resolves
  the configured caramel token explicitly within the financial workspace.
- Ruff, `git diff --check`, compiled CSS reproducibility, gettext format and
  compiled-byte checks passed; the catalog has no untranslated/fuzzy entries.
  No migrations or dependencies changed.
- The loopback preview on port 8768 uses the verified private backup of the
  previous disposable preview and the current code/catalog. Its preserved test
  records remain separate from the installation. No merge, main push, version,
  tag, image, external integration or publication was performed.
