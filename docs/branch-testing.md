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

Use the [interface map](interface-map.md) for the current routes and component
families, and the [shared interaction contracts](frontend.md) for keyboard,
filters, help and departure behavior. In both themes on computer and phone:

1. Follow each workspace's section tabs and source links. Confirm that shortcuts
   reach the record or period described, and that Back/Forward and form
   Save/Cancel retain the explicit local origin and its filters.
2. Type and delete in consultation searches; change short choices, months and
   ordering. Results update without losing the caret, focused control or page
   position. Clear remains near active criteria. Read-only filters must not
   trigger unsaved-form warnings. Repeat with the native GET fallback.
3. Create and edit a transaction with each available payment instrument. Check
   persistent account/card miniatures, their search, exact category splits and
   server-error recovery. Creation choices begin empty; edited/bound values and
   explicit shortcut context remain selected.
4. Open and minimize a bank workspace, inspect its accounts, cards and reserves,
   and follow invoice and movement actions. Check compact exposed invoice/FX
   criteria and the distinction between automatic and confirmed payments.
5. Complete the guided investment entry and full product/asset configuration;
   inspect archived entries, observed-price filters and operation context.
   In Plan, review budgets, backed goals, signal settings, salary/CLT inputs,
   yield overrides and explicit draft save/duplicate/compare/delete actions.
6. Use Tab/Shift+Tab, arrows, Enter and Space throughout. Focused fields,
   searchable results and final actions remain above fixed navigation on short
   phone viewports. Test invalid submissions, conditional transitions and native
   forms with JavaScript disabled. Hover/focus/touch help follows its shared
   contract; menu actions require deliberate activation.
7. Confirm that Net worth and statement operations remain absent while paused.
   Old operation URLs return to the owning workspace without executing writes;
   owned confirmed/undone import history remains read-only. The redesign roadmap
   is documentation, not an application page.

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

Current validation commands and isolation rules live in
[Contributing](../CONTRIBUTING.md). Run them for the exact checkout under review;
a historical passing count does not establish this checkout's status.

Earlier test counts, screenshots and iteration notes are preserved in the
[branch validation history](reviews/branch-validation-history.md). New validation
reports should identify the revision, date, scope, environment, failures and
remaining manual checks, without duplicating the current interaction contract.

## Performance evidence

Use the current reproducible benchmark command and measurement limits in the
[project health review](reviews/project-health-2026-10-16.md#reproducible-reporting-measurements).
Earlier synthetic observations remain in the
[historical performance section](reviews/branch-validation-history.md#performance-evidence);
they are dated evidence rather than current latency guarantees.
