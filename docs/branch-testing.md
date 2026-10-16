# Personal finance branch testing

The work on `feat/personal-finance-evolution` is unreleased. It is intended for
manual testing before the owner authorizes integration into `main`. The branch
does not change the version or publish a container, tag or release.

## Preview a disposable copy

From this branch and with the locked dependencies installed:

```bash
uv sync --locked
uv run python scripts/preview_branch.py
```

Open <http://127.0.0.1:8766/> and sign in with your existing user. The command
locates the installation's SQLite database using `TUXEDO_DATA_DIR` and the
configured environment file. For a different source or a busy port:

```bash
uv run python scripts/preview_branch.py --source-database /absolute/path/db.sqlite3 --port 8767
```

The helper uses SQLite's read-only online backup API, checks the copy's
integrity, gives it private file permissions and migrates **only the temporary
copy**. The loopback server has an ephemeral signing key and signups disabled.
Existing login credentials work; existing browser sessions do not transfer.
Stop with Ctrl+C. The preview and its edits are discarded. Rerunning it starts
with a fresh copy; changes made during preview are not promoted automatically.
The original database and installation environment are untouched.

Do not start the branch with an ordinary `manage.py migrate` against personal
data during this review. Automated browser tests also use their own disposable
database, through `npm run test:e2e`; the direct Playwright command must never
target the preview or a personal installation.

## Computer and phone review

The preview is loopback-only unless you explicitly choose a private IPv4 address.
To test on a phone, connect both devices to a trusted private network and supply
this computer's LAN address, for example:

```bash
uv run python scripts/preview_branch.py --bind 192.168.1.25
```

Replace the example with the address assigned to your computer. Open
`http://192.168.1.25:8766/` on either device. The helper binds only that interface,
accepts exactly that host plus loopback, disables signups and still migrates only
the disposable copy. It rejects wildcard/public bindings. This temporary preview
uses HTTP, so use it only on your trusted LAN and stop it after testing. Do not
forward the port on your router. If the local firewall or Wi-Fi client isolation
blocks the connection, review those settings before enabling only the chosen
local port/interface; the helper never changes them.

For the area-by-area simplification, check these tasks in both themes on computer
and phone, in English or Portuguese. These are acceptance tasks for the current
branch; automated validation is reported separately by iteration below.

1. Keep Dashboard/Reports usable. Net worth, Import statements and Roadmap must
   not occupy navigation or menu entries while paused. Open an old statement
   operation URL and confirm it returns to Transactions; an old Net worth URL
   returns to Home. Stale import POSTs cannot confirm or undo anything. Posted
   import provenance remains available as owned read-only history when it exists;
   the roadmap remains in project documentation.
2. Check the compact transaction bar: search, billed month and the All/Income/
   Expenses choices remain visible. Search a category name, then open Filters
   with Enter/Space to refine an exact category, recurrence, event date and
   ordering. The active indicator and Clear stay near the controls. Alternate
   All/Income/Expenses and a long named month: search and controls must keep their position
   and size, including when a long list becomes one result. Expanded criteria
   appear below the rail. Type/delete
   search text and change choices without Apply; check caret, focus, scroll and
   Back/Forward. Save/Cancel return to the currently filtered list. Repeat with
   JavaScript disabled, opening the native disclosure and submitting Apply.
3. Open the consultation month panel, set its year, type `sete` in Portuguese
   (or `sept` in English) and press Enter to select September. An ambiguous month
   prefix needs an explicit choice. Try a blank/out-of-range year: the panel must
   keep the error and entered choices without applying a month. Clear an applied
   month, including with an invalid unused draft year, and check its caption,
   results and ISO URL agree. Escape and Tab-away close the panel; ordinary
   category/account searches still require arrow selection before Enter. Without
   JavaScript, the original month input and GET submit remain usable.
4. Categories opens a compact grouped List with descendants initially collapsed.
   Parent/leaf names, types and counts align in desktop columns; smaller screens
   put metadata below names and keep comfortable actions. Use a
   parent name with Enter/Space to expand/retract only its descendants; the
   parent's Edit and secondary actions remain available. Test Expand all and
   Collapse all, including nested groups. Search a child: its owned ancestors
   appear as parent context, matching paths open, and the count includes matches
   rather than the extra ancestors. Opening More filters must leave its trigger
   and search in the same positions; choose criteria, collapse it, search and
   Clear without the rail moving. The graph and view switch are absent; old
   `?view=tree` bookmarks show the same list and filters.
5. In light and dark mode, check the shared footer: small attribution and legal
   text with a thin divider, without the large logo/banner. Hover a `?`: text is
   visible only while the pointer stays on the icon and closes on entering the
   explanation. Mouse clicks cannot pin it. Test Tab, Enter/Space, Escape,
   touch toggling, unrelated background updates and native help without JavaScript.
6. Open Accounts: all owned banks appear as compact name/color/count links,
   without the old bank/account/card/pot search. Open a bank and check account
   cards, the separate amount grid, New transaction and account options.
   Credit-card invoices/purchases and editing belong to the owning account;
   Account details retains opening balance and debit cards. Check menus fit on
   phone screens in both languages. Move an account or cash pot into Reserves,
   restore participation and check money/history are unchanged. Cash pots use
   compact cards with aligned amounts, a separate participation action and one
   redemption hint per group. After a planning
   update, open an editor or transaction and Cancel back to the same bank page.
   Open Recent activity for redemptions, invoices and movements; check a
   redemption error remains visible there. Browser Back returns to the overview.
7. Open Invoices as a card grid. Search by card/account/bank, choose bank,
   month or status in Filters, then open one card's dated invoice history. Empty
   cards remain reachable without month/status criteria. Clear stays in that
   card's history; Back returns to the filtered card grid. Try an old `?card=`
   bookmark and check the scoped redirect, then repeat without JavaScript. Record a partial confirmed payment and recover an invalid
   amount. Search local rates, open pair/date criteria and recover invalid dates
   beside the original control. Criteria show their active indicator and Clear;
   returned field errors reopen a closed disclosure without moving focus or
   replacing the input. Create a rate using the ordinary Save/Cancel flow.
8. Add an application through the guided form, including a zero opening, a
   monetary reserve and units with acquisition cost. If you need a classification,
   choose it in Advanced before the first operation (existing history locks it).
   Open Update and record an
   operation or local price; History and detailed metrics remain accessible.
9. Plan opens the selected month, available cash after known commitments and
   budgets. Distinguish the recorded cutoff from projection and reservations.
   Create/edit a category limit; open Goals or Tools for the less frequent tasks.
10. Create a split transaction or a goal with a real reserve, including invalid
    sums/capacity. Errors keep entered choices and never create partial records.

The public static tour still represents the published release. This branch's
interactive preview is the acceptance environment; no integration, bank
connection, Cloudflare deployment or publication is implied by these tests.

## Acceptance checklist

Use real keyboard navigation in both themes. For a focused fallback check,
disable JavaScript and submit the native forms. Each new operation below can be
created in the disposable preview without affecting the installation.

1. **Compatibility:** compare existing account balances, invoices, transactions,
   investment quantities and effective FX snapshots. Existing cards retain
   automatic settlement. Old opening dates stay unknown until explicitly dated;
   warnings must not manufacture historical dates or market returns.
2. **Investments:** use an initially empty product/asset position in the same
   currency as its funding account, without fees. Buy one unit at 100 and sell
   it at 150. The remaining quantity and cost are zero; the realized result is
   50 in the asset currency. Partial sales preserve weighted
   remaining cost. Record a dated local price and inspect historical valuations;
   removing it uses the preceding observation or remaining cost. Declaring fees
   in the asset currency changes cost/results, never the actual bank amount.
3. **Imports (paused):** opening upload/review/confirm/undo returns to Transactions.
   No paused import shortcut is offered in tabs or account actions.
   Posted confirmed/undone history is read-only, user-owned and never offers an
   undo while paused. Existing posted movements remain inspectable at source.
4. **Budgets:** set an expense-category limit and copy it to the next month.
   Inspect recorded and forecast spending, including child categories, category
   splits and reference FX limitations. An overlapping parent/child limit in the
   same month/currency is rejected.
5. **Goals:** reserve part of an actual account or monetary cash-pot balance.
   Check available planning funds and target progress; the reserve creates no
   asset or transfer. Reduce its source balance to inspect proportional backing.
   Archive and restore the goal; insufficient funds must require review.
6. **Signals:** inspect possible duplicate/increased expenses, exceeded budgets
   and cash shortages. Each suggestion explains its evidence and scope.
   Acknowledge, dismiss and reopen it; these actions must not edit finances.
7. **Category splits:** split a transaction between two or more categories. Its
   parts must add up exactly, including installment cents. The source still
   generates one payment or invoice obligation. Inspect filters, reports, budget
   consumption and the `category_splits` field in transaction CSV exports.
8. **Wealth (paused):** its navigation section is hidden and old direct URLs
   return to Home; underlying calculations remain available to their other consumers.
9. **Confirmed invoices:** set today as the start date in a card's settings and
   use an invoice due on or after it. Record a partial payment from an account
   in the invoice currency. Inspect the
   real debit and remaining forecast obligation, then edit/delete the payment.
   Repeating the same submitted confirmation must not create a second debit.
   Earlier automatic invoices stay automatic; confirmed invoices retain their
   mode even if the card start date changes.

The new features are local. Statements, decisions, price observations and signal
reviews stay in the installation database. No bank connection, external quote
feed, AI service or presentation CDN is required. Inter's font and license are
included in `static/fonts/`.

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
