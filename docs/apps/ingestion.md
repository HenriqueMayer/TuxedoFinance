# `ingestion`

**Current interface status: paused.** Upload, mapping, review, confirmation and
undo cannot be used through the application. Existing owned confirmed/undone
history remains available read-only. See the [review gate](#interface-review-gate)
and [redesign roadmap](../roadmap.md); implemented services do not imply an
available import workflow.

This app retains explicitly reviewed local bank-statement services. It stores
bounded evidence and decisions before posting through the existing banking and
transaction services. It does not connect to a bank,
broker, Open Finance provider or external processing service. This workflow is
implemented under Unreleased after `0.10.0`.

| Route family | Default behavior |
|---|---|
| `/imports/`, mapping, review, confirm and undo | GET/POST review gate redirects to Transactions before the workflow executes. |
| `/imports/history/` | Authenticated, owned confirmed/undone provenance; read-only. |
| `/imports/<id>/` | Owned confirmed/undone detail; pending batches cannot bypass the gate. |

The workflow and UI descriptions below document retained implementation for its
future review, rather than steps an installation owner can currently complete.

## Supported evidence

Each upload targets one owned currency-specific `BankAccount`. CSV mapping
requires explicit date/description columns, either a signed amount or separate
nonnegative debit/credit columns, a decimal convention and date format. Optional
columns supply currency and bank identifier. Supported dates are ISO,
day/month/year or month/day/year; encodings are UTF-8 and Windows-1252.

The bounded OFX parser accepts complete bank `STMTTRN` records with posting
date, signed amount, `FITID` and statement currency. It retains an account hint
and optional closing balance/date for review. It is not a general securities,
multi-account or broker-history importer; unsupported/malformed structures are
rejected rather than guessed. Entity declarations are rejected.

Limits are 2 MiB per upload, 500 nonzero cash entries and 40 unique nonempty CSV
headers. Amounts must be finite, fit the cash field and have at most two decimal
places. Currency must match the chosen account; symbol-containing or ambiguous
numeric values are rejected. Tuxedo transaction-report CSVs are rejected because
their billed occurrences are not bank cash entries.

`ImportBatch` retains the filename, exact-file hash, raw local text, mapping,
parsed metadata and optional closing evidence. `ImportedRow` retains normalized
cash data, original row values, the explicit action and eventual source links.
These statement contents are sensitive local database data: normal database
backup, access and retention responsibilities apply. They are not committed
repository fixtures or uploaded to an external service.

## Review and posting state

```text
CSV: upload → STAGED → explicit mapping → READY
OFX: upload → READY
READY → review every row → confirmation → CONFIRMED → guarded undo → UNDONE
```

Staging, mapping and review create no financial records. Every row requires a
deliberate decision, including entries to skip; no duplicate suggestion is
automatically accepted. Available decisions are:

| Action | Accounting effect |
|---|---|
| `SKIP` | Keep review evidence only. |
| `MATCH` | Link an existing owned movement with exactly the same account, date, direction and amount; post nothing. |
| `CREATE` | Create one ordinary account income/expense transaction using an owned compatible category, then derive its cash movement. |
| `PAY_INVOICE` | Confirm one actual-date payment of an owned manual invoice in the account currency through `save_invoice_payment`. |
| `TRANSFER` | Create one paired own-account transfer using the owner's explicit positive counterpart amount; retain native amounts and FX evidence. |

Confirmation validates all saved decisions again and verifies a digest of the
reviewed payload. Non-skipped entries cannot be future-dated or precede a known
account opening. A nonzero account opening with unknown date must be reviewed
and dated before confirmation, including any counterpart account used for a
transfer. No opening balance or date is inferred from the file.

`confirm_batch` runs atomically with owned batch/account/row checks. It posts
canonical transaction, payment and transfer sources, then synchronizes ordinary
transaction projections once after the batch. A failure rolls back the batch's
financial changes. Reconfirming an already confirmed batch is idempotent.
Full imported descriptions remain in row evidence and transfer notes. Paired
transfer movement descriptions are bounded 255-character summaries; a long valid
description does not prevent confirmation or lose the original evidence.

## Duplicates and source preservation

An exact active file hash is unique per owner/account; uploading it again opens
the existing review. Confirmed external bank identifiers are separately unique
per owner/account, including across different files. Repeated identifiers or
the same matched movement twice in one confirmation are rejected. Description,
date and amount resemblance is a weak review hint, not proof of duplication.
Rows without a bank identifier still require the owner's matching decision.

Match the existing movement for a previously recorded recurrence, installment
settlement, investment cash leg or transfer. Do not create another source
transaction for that cash entry. A statement-level card payment should match an
automatic settlement or explicitly pay a manual invoice; it is not a second
consumer expense. The importer never expands one bank entry into recurring or
installment purchase sources, reclassifies a transfer as income/expense, or
imports investment positions from settlement cash.

If closing evidence is provided, reconciliation compares it to the account
ledger at that date and exposes the difference. Confirmation stores that
comparison; it does not create a balancing adjustment or rewrite the opening.
The detail screen also reflects current reconciliation after subsequent edits.

## Guarded undo

Confirmation captures all created source fields, category splits and linked
cash evidence. `undo_batch` first verifies those snapshots and rejects undo if
any created source or its movements have since changed or disappeared. It also
rejects removal of evidence matched by another confirmed import. The operation
then deletes only sources created by that batch, including their canonical
cash legs, and resynchronizes once atomically.

Matched original records and skipped entries are never deleted by undo.
External identities are released and the batch remains `UNDONE` with its local
review history. Uploading the same file afterward starts a new explicit review,
not a silent replay. This is guarded personal correction, not an immutable audit
or automatic rollback of subsequent financial activity.

## Forms and isolation

Every batch, account, category, invoice, movement and counterpart choice is
owner-scoped and revalidated in services. Mapping and action selectors begin
empty. Dependent amount/category/invoice/transfer fields reveal only their
chosen branch; invalid submissions preserve errors and values. Shared partials,
searchable record choices, native no-JavaScript forms, CSRF and explicit POST
confirmation follow the [mandatory form contract](../frontend/forms.md#keyboard-and-choice-contract).
Evidence is escaped in owned local review screens; sensitive import responses
use `never_cache`.

See [banking](banking.md#optional-manual-settlement) and
[transactions](transactions.md#settlement-behavior) for the posting boundaries.

## Compact review and continuity

An owned account shortcut on upload preselects that account. A validated local
origin is preserved through mapping, review, confirmation and undo screens;
Cancel and a completed confirmation can return to the original account/search.
Mapping reuse is an explicit GET choice from the latest confirmed CSV for the
same owner/account, headers, encoding and delimiter. It only prepares fields;
parsing and financial decisions still require their normal explicit submissions.

Review displays 25 rows per page with native details showing original evidence
and decision controls. The first pending row and bound errors are expanded.
Saving one page validates its complete decisions, retains other pages and moves
to the first remaining decision; it never posts financial sources. The optional
bulk action skips only still-undecided entries on the current page whose strong
bank identifiers were already confirmed. Valid choices are preserved, invalid
ones prevent the save, and fuzzy description matches are never bulk-skipped.
The bulk action rechecks its confirmed identifiers and still-empty saved actions
inside the same review transaction before writing any decisions. Undoing the
original import or saving a decision in another tab invalidates the old
suggestion and leaves the submitted subset unchanged.

`save_review(partial=True)` accepts only a nonempty subset of the owned batch.
Confirmation continues validating every row and the complete decision digest.
Read/write responses retain their existing owner scope and `never_cache`.


## Interface review gate

Statement upload, mapping, review, confirmation and undo are paused by
`core.features.review_gate`. Both direct GETs and stale POSTs return to Transactions before
any service executes. The source model, parser, deduplication and posted ledgers
remain intact. `/imports/history/` and owned confirmed/undone detail are read-only,
uncached provenance; pending batches cannot enter the review UI. Core default
settings keep the feature paused; dormant workflow tests explicitly opt in with
an isolated `override_settings`, while default-gate regressions prove no writes.
The dashboard does not advertise paused pending actions. No release date is
promised and bank synchronization remains outside this local iteration.
