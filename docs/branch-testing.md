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

For this UI/UX iteration, check these tasks in both themes on computer and phone:

1. Navigate through Home, Transactions, Accounts, Investments and Plan. Find
   Reports, Net worth, Categories, Imports, Invoices and every simulation from
   the owning workspace. Check the account settings, language and logout.
2. From a searched account row, open Update account and choose a manual entry
   or statement. Confirm the account selection and return to the same search
   after Cancel. Check that row actions open only deliberately.
3. Open a card invoice from Home or Accounts. Record a partial payment made
   at the bank and inspect the remaining amount. Recover from an invalid amount
   without losing the paying account. Existing automatic cards stay automatic.
4. Record an operation or dated price from an investment position and return
   to that position. Verify a filtered ledger also retains its origin.
5. Create/edit a split transaction in one submission, including an invalid
   sum. Create a goal with an optional initial real-balance reserve; insufficient
   backing must preserve the form and create neither a goal nor a reserve.
6. Review a small import: collapsed details stay reachable, errors and the next
   required decision remain visible, reuse of a compatible mapping is explicit,
   and confirmation still precedes financial posting. Check Back/Forward,
   keyboard choices near the bottom bar and the no-JavaScript path.

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
3. **Imports:** stage a small CSV with date, description and signed amount;
   select its columns, date format and decimal convention. Review each row and
   inspect the final confirmation. Compare its closing balance with the ledger.
   Repeat the file and a bank identifier to inspect deduplication. Match existing
   cash evidence for investments and transfers instead of creating an expense.
   Undo an unchanged batch; edit an imported record and verify undo refuses the
   whole batch. OFX uses the same review and final confirmation.
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
8. **Wealth:** inspect assets, incurred card debts, card credits and the monthly
   series. An equal-amount transfer between same-currency accounts or a goal
   reserve leaves net worth unchanged; paying an
   already recognized card debt exchanges cash for debt. Full installment debt
   is included; future recurring purchases are excluded. Missing opening dates,
   prices and FX are visible, without an inferred percentage return.
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

### Navigation and UI/UX iteration — 14 October 2026

Validation of the current navigation changes also used synthetic or disposable
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

This UI/UX iteration adds no migrations or dependencies. The previous container
lifecycle checks were not repeated. Browser checks use Chromium; acceptance on
the owner's actual computer, phone and financial data remains pending. Banks,
Cloudflare, deployment and integration into `main` remain outside this iteration.

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
