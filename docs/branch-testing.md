# Personal finance branch testing

The current checkout includes unreleased personal-finance and assistant work.
This walkthrough supports manual owner acceptance before any separate decision
to integrate into `main` or publish. Running it does not accept the candidate,
change its version or publish a container, tag or release. The
[PRD status table](product-requirements.md#current-delivery-status) distinguishes
current interfaces from paused and gated capabilities.

## Preview a disposable copy

From the checkout under review and with the locked dependencies installed,
explicitly keep real assistant authorization and inference off:

```bash
uv sync --locked
ASSISTANT_OPENAI_AUTH_ENABLED=False ASSISTANT_OPENAI_INFERENCE_ENABLED=False uv run python scripts/preview_branch.py
```

Open <http://127.0.0.1:8766/> and sign in with your existing user. The command
locates the installation's SQLite database using `TUXEDO_DATA_DIR` and the
configured environment file. For a different source or a busy port:

```bash
ASSISTANT_OPENAI_AUTH_ENABLED=False ASSISTANT_OPENAI_INFERENCE_ENABLED=False uv run python scripts/preview_branch.py --source-database /absolute/path/db.sqlite3 --port 8767
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
ASSISTANT_OPENAI_AUTH_ENABLED=False ASSISTANT_OPENAI_INFERENCE_ENABLED=False uv run python scripts/preview_branch.py --bind 192.168.1.25
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

1. Follow the same six direct destinations on desktop and phone: Home,
   Transactions, Accounts, Investments, Plan and Analytics. Home keeps operational
   indicators; Analytics has Finances and Investments with independent chart
   periods. Check their section tabs and source links, including the selected
   month when opening Analytics from Home. Back/Forward and form Save/Cancel
   must retain the explicit local origin and filters. Compact headings and
   opening summaries must preserve long labels, warnings and expandable
   details rather than forcing equal panel heights.
2. Type and delete in consultation searches; change short choices, months and
   ordering. Results update without losing the caret, focused control or page
   position. Clear remains near active criteria. Read-only filters must not
   trigger unsaved-form warnings. Repeat with the native GET fallback.
3. Create and edit a transaction with each available payment instrument. Check
   persistent account/card miniatures, their search, exact category splits and
   server-error recovery. Creation choices begin empty; edited/bound values and
   explicit shortcut context remain selected.
4. In Accounts, follow Accounts, Invoices, Loyalty and Exchange rates. Open a
   bank from its institution link, then minimize through the title bar and its
   labelled action; account content must not minimize it. Inspect the separate
   account surfaces, cards and reserves, then follow invoice and movement
   actions. Check compact invoice/FX criteria, native invoice credits and the
   distinction between automatic and confirmed payments.
5. In Investments, follow My investments, History, Prices and Setup. Complete
   guided entry and full product/asset configuration; inspect archived entries,
   observed-price filters and operation context. Save a position emoji and
   verify that another position in the same asset is unaffected. In Plan, use
   This month, Goals, Simulations and Alerts. Review budgets, backed goals and
   signal settings; inside Simulations, check Salary, Yield and Saved drafts,
   including overrides and explicit save/duplicate/compare/delete actions.
6. Use Tab/Shift+Tab, arrows, Enter and Space throughout. Focused fields,
   searchable results and final actions remain above fixed navigation on short
   phone viewports. Test invalid submissions, conditional transitions and native
   forms with JavaScript disabled. Hover/focus/touch help follows its shared
   contract; menu actions require deliberate activation.
7. Confirm that Net worth and statement operations remain absent while paused.
   Old operation URLs return to the owning workspace without executing writes;
   owned confirmed/undone import history remains read-only. The redesign roadmap
   is documentation, not an application page.

The static tour captures the checked-out application, including unreleased
changes, as described in [preview maintenance](preview.md). This disposable
interactive preview supports owner acceptance; no integration, bank
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
   Analytical graphs belong to Analytics rather than Home.
8. **Wealth (paused):** its navigation section is hidden and old direct URLs
   return to Home; underlying calculations remain available to their other consumers.
9. **Confirmed invoices:** set today as the start date in a card's settings and
   use an invoice due on or after it. Record a partial payment from an account
   in the invoice currency. Inspect the
   real debit and remaining forecast obligation, then edit/delete the payment.
   Repeating the same submitted confirmation must not create a second debit.
   Earlier automatic invoices stay automatic; confirmed invoices retain their
   mode even if the card start date changes.
10. **Invoice credits:** add a credit with its owned card, reference month,
    native currency and source evidence. Inspect the reduced invoice obligation,
    category reporting and monthly outlook without creating a bank-cash income
    or a second expense. Edit/delete it and verify that actual confirmed
    payments retain their evidence.

Core financial workflows remain local. Financial records, price observations,
private drafts and signal reviews stay in the installation database. No bank
connection, external quote feed, AI service or presentation CDN is required.
An explicitly enabled ChatGPT connection is optional and sends bounded necessary
context externally; it is outside this provider-disabled walkthrough. Inter's
font and license are included in `static/fonts/`.

- [ ] Owner completes the manual checks for the exact checkout and records any
      remaining issues before separately approving integration or publication.

## Assistant review

A disposable copy does not authorize connecting an account or sending copied
financial information to a model. The preview helper inherits explicit process
settings; keep real authorization and inference off during this walkthrough:

```bash
ASSISTANT_OPENAI_AUTH_ENABLED=False ASSISTANT_OPENAI_INFERENCE_ENABLED=False uv run python scripts/preview_branch.py
```

Check the unavailable-provider state, local history, Markdown copying and
Minimize/Restore/Close on computer and phone in both themes. A retained selected
account can remain visible as metadata while sending is disabled. Opening chat
must preserve an edited financial form, workspace geometry and focus; logout or
an account change must not reveal the previous user's transcript through history.

Streaming, canonical simulation and confirmed-action interactions use synthetic
fixtures through the isolated browser runner, without a linked account:

```bash
npm run test:e2e -- tests/e2e/assistant/connections.spec.js tests/e2e/shared/history-privacy.spec.js
npm run test:e2e -- --assistant-fixtures \
  tests/e2e/assistant/streaming.spec.js \
  tests/e2e/assistant/chat-ux.spec.js \
  tests/e2e/assistant/actions.spec.js \
  tests/e2e/assistant/consultation.spec.js \
  tests/e2e/assistant/copy-markdown.spec.js
```

Connection preparation cases require the ordinary disabled gates; do not select
the synthetic ready-provider configuration for those cases.

Those cases exercise model/effort preferences, thinking/writing/cancellation,
targeted reads, monthly simulation, private exports and reviewed local changes.
Reads/simulations must not save records; only the separate confirmation can
create, categorize, edit or delete a transaction, create a goal or create a
category budget: exactly six supported local actions. Repeat confirmation must
not duplicate the write. ChatGPT is the only connected provider; there is no
paid API-key fallback or Internet/news tool. Real model validation has a separate
approved account/context/usage scope and does not follow from this manual
acceptance checklist. The real Open Finance pilot remains paused. Its prepared
operator-only probe makes no application database queries or ledger writes and
does not enable a product bank connection.

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
