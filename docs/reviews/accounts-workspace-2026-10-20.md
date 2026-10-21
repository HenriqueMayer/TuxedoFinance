# Accounts workspace reimagining — 2026-10-20

## Scope

Reorganize Accounts with the same editorial hierarchy as Investments and Plan.
Keep card artwork, existing financial services and private local records. No
publication, bank connection, live model request or installation migration was
performed for this review.

The working tree already contained 140 modified/untracked paths from earlier
assistant, account-control and invoice-credit work. The pre-task manifest and
copies are preserved under `.local/accounts-reimagining-2026-10-20/before/`.
This report describes this presentation batch; it does not claim those earlier
changes were introduced here or committed separately.

## Delivered behavior

- Four explicit sections: Accounts, Invoices, Loyalty and Exchange rates.
  The horizontal phone rail reveals a focused link completely. Native links,
  authorized Back/Forward, HTMX and form departure protection remain in place.
- One divided institution directory and account surface, rather than repeated
  nested account boxes. Real balance, reserved balance and planning availability
  keep their existing labels and amounts. The internal bank window, Minimize,
  reserve disclosures and participation POSTs retain their IDs and behavior.
- Existing card colors, gradients and miniatures are unchanged. The selected
  card and statement detail now retain that identity. Invoice history aligns
  month/due date, status, native total/remaining and actions; phone rows stack.
  Payment entry, credits, editable sources and nested return origins remain.
- Loyalty programs have a searchable, paginated overview with their own units,
  linked cards and ten recent entries. Full program history has independent
  pagination and notes search. Existing entry, redemption and program editors
  retain explicit local Save/Cancel origins and generated-entry locks.
- Loyalty display queries ignore foreign legacy relationships. Point balances
  are aggregated independently of card-search joins to avoid duplicate totals.
  No ledger model or mutation service was changed in this batch.
- Interface map, banking/interaction guides, both READMEs, Design Lab and public
  preview descriptions were updated. Only the four Banking preview images were
  retained from a disposable synthetic capture; the other 28 images were
  restored byte-for-byte.

## Validation

| Check | Evidence/result |
|---|---|
| Isolated Django check and migration drift | Passed; no model migration required. |
| Full Django suite | 1,272 passed, including the previously pending working-tree features. |
| Final focused Django suite | 283 passed: Banking, Core and assistant page context. |
| Browser domain sweep | 109 cases exercised; initial 95 passed and 14 failures diagnosed as detailed below. |
| Final browser repeat | 44/45 passed on the scoped repeat; after observing full native page load and settled panel geometry before capture, the complete loyalty file passed 5/5. Every initially failing case has a passing repeat; 109 distinct scoped cases have passing evidence across these runs. |
| Static preview | 21 passed after the Banking capture refresh. |
| JavaScript tooling | 26 passed. |
| Python repository tooling | 44 passed. |
| Source checks | Focused Ruff F checks, JS syntax, CSS rebuild comparison, gettext format/completeness and `git diff --check` passed. |
| Documentation links | 93 documents, 808 local references, zero unresolved (rechecked after adding this review). |

The first browser sweep found partial keyboard visibility in the four phone
rail cases and two over-wide invoice headers. These were corrected in the
shared navigation enhancement and scoped invoice CSS. Two old header assertions
were updated for the deliberate replacement of More options with Loyalty; five
new invoice fixtures were corrected to use a permitted current/future manual
settlement date. One native loyalty screenshot began its actionability check before the new
page and panel geometry settled. Its test now observes the complete native
load and final CSS transform before scrolling; financial assertions and the
application workflow are unchanged. The complete loyalty file then passed. The final
repeat includes every initially failing case plus related presentation,
keyboard, native forms, contextual returns and catalogue cases.

Browsers used only `npm run test:e2e` disposable databases and loopback servers.
Provider authorization and inference remained disabled. Tests and screenshots
cover 320–1440px, both themes, English/Brazilian Portuguese, long names, real
keyboard events, stable live filters, invalid POST recovery, native forms,
owned/foreign records and legacy relationship isolation. Existing touch tests
cover the shared menus, choices and account actions. The installation database,
`.env` and private vault were not used by these checks.

Visual inspection included both Banking preview themes, desktop statement
history, phone statement summaries/payment errors, both phone account themes,
program/card identities, expanded points history and the Design Lab specimens.
Local logs/screenshots are under
`.local/accounts-reimagining-2026-10-20/`; the final browser outputs are also
preserved there before subsequent test runs.

## Limits

This is a focused Accounts browser review plus a full Django suite, not a new
full-application browser sweep. Chromium phone emulation does not establish
physical-device or assistive-technology certification. Real bank integrations,
AI providers and the paused import UI were not exercised or enabled. No push,
release or publication is authorized by these results.
