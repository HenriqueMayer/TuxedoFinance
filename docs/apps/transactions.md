# `transactions`

`transactions` records categorized economic events. It no longer owns or
derives the account balance; settlement
is expressed through owned banking accounts, cards, invoices, and movements.

## Responsibilities

- CRUD, search and filtering for `INCOME` and `EXPENSE` events.
- Category assignment and optional exact category allocations for income/expense.
- Amount, event date, recurrence and notes; consolidated reporting uses the
  authenticated user's base currency while native amounts remain unchanged.
- Selection of PIX, debit card, credit card, or direct account as the settlement
  path. Own transfers are recorded separately in Banking.
- Atomic synchronization of derived `BankMovement` and `CardInvoice` rows
  through this app's `sync_user_ledger` service.

`INVESTMENT` is removed from `TransactionType`. Investment deposits and
withdrawals belong to the investments workflow and create banking movements
without becoming income or expense.

## Settlement behavior

| Path | Transaction classification | Cash effect |
|---|---|---|
| External PIX received | `INCOME` | Immediate account credit. |
| External PIX sent | `EXPENSE` | Immediate account debit. |
| Direct account | `INCOME` or `EXPENSE` | Effective-date movement. |
| Debit card | `EXPENSE` | Effective-date movement. |
| Credit card | `EXPENSE` | Added to `CardInvoice`; no purchase-date account movement. |
| Own-account transfer | Banking transfer | Paired debit/credit movements; excluded from income/expense. |

PIX is therefore a settlement capability, not a transaction type. A PIX to or
from another person remains a normal categorized transaction.

## Form and validation

The default form captures title, positive amount, type, category, event date and
payment channel. It progressively reveals only the matching settlement fields:

| Channel | Available fields | Server rule |
|---|---|---|
| Bank account | Owned bank account | Valid for income and expense. |
| PIX | PIX-enabled owned bank account | Valid for income and expense. |
| Debit card | Owned debit card and its account context | Expense only. |
| Credit card | Owned credit card, installments and bill choice | Expense only. |

Changing channel clears controls that no longer apply in the enhanced browser
experience. The no-JavaScript fallback keeps the normal selects available, and
the server rejects incompatible direct submissions. Recurrence and notes are
kept under optional advanced options. Category selection is enhanced as an
accessible, accent-insensitive search over the category and parent name; it
immediately excludes categories explicitly classified for the other transaction
type. Reaching a record search with Tab or opening its results scrolls just enough
to show the input and list below the sticky header, while preserving keyboard
focus. This also applies to the credit-card selector revealed by the payment
channel. Its native select remains the no-JavaScript fallback. Unclassified legacy
categories intentionally remain available for both types. Choices are limited to
the user's banks, accounts, cards and categories. Validation enforces:

- category required for every transaction;
- an income-only or expense-only category can only classify its matching type;
- PIX only on an account with `pix_enabled=True`;
- owned instruments that match the selected settlement path;
- installments only for credit cards and assigned across invoices without
  creating account movements for individual installments.

Positive reward-redemption IOF appears as a generated expense in its funding
currency, with a unique `reward_redemption` link. Transaction lists mark it as
**Managed by reward redemption** and link to bank redemption history. Direct
edit/delete routes and admin actions reject that expense; its inline source form
reconciles the charge and invoice. Generated titles display and search in the
active language, including migrated sources. Billed-month filters, CSV and
instrument/category reports include the expense normally. Account IOF retains
its original redemption movement; card IOF joins the aggregate invoice once.

Synchronization derives recurrence and installment amounts from the original
transaction without inserting recurrence or installment `Transaction` rows.
An older positive IOF source missing its expense is materialized once before
synchronization; the migration already backfills existing redemptions. It creates or updates
movements and invoices through a projection horizon, normally twelve months
beyond today. Future-effective rows may exist in the database, but balance
queries exclude them until their effective date. See
[request-time synchronization](../architecture.md#request-time-synchronization).

Reconciliation compares projected values to existing rows and saves only actual
changes. Unchanged rows retain their identifiers and timestamps; source keys
prevent duplicate movements. Manual invoice payments are confirmed evidence,
not disposable projections, and remain protected when a source or forecast
horizon changes. Atomic synchronization still uses SQLite's serialized writer
behavior; skipping unchanged writes does not provide concurrent row locks.

## Category splits

`TransactionSplit` optionally allocates a source transaction to two or more
owned compatible categories. The positive, distinct category amounts must sum
exactly to the source amount; the form supports at most twenty rows. The parent
category stays required as a legacy/fallback field. When splits exist, reports
use the allocations instead of adding that parent category again.

Splits do not create transactions, installments, movements or invoices. They
therefore cannot change the transaction's cash or statement total. Editing an
amount or type must keep its allocations valid. Generated redemption IOF remains
managed from its source and cannot be split through the ordinary transaction
editor.

`category_allocations_for_month` distributes installment cents proportionally
over remaining category capacities. It floors shares, assigns remainders in
stable order and carries the unallocated capacity to the next installment.
Each monthly split equals that installment exactly, no allocation becomes
negative, and the full plan reproduces the original category totals. Fixed
recurrences reuse their source allocations for each occurrence without copying
source records.

## Listing and reporting semantics

The list opens on the full history. Search covers title, notes, category and split
category, bank, account and card labels. The compact consultation bar keeps search,
billed month and the **All**, **Income** and **Expenses** choices visible. A single
native **More filters** disclosure contains event date, recurrence and ordering
on one compact row where space permits, wrapping at narrower widths. Category
lookup uses the general search instead of a second category picker. Its badge
counts additional criteria; Clear stays
next to the controls whenever any filter or nondefault ordering is active.
Applied additional criteria and invalid dates open the disclosure on a fresh GET.
Live updates preserve its mounted controls and the user's disclosure choice.
At each responsive breakpoint the bar uses fixed grid tracks for its primary
controls and action slots: one rail on wide desktop viewports, two rows on
smaller desktops, and explicit stacked tracks on mobile. An empty Clear slot
remains reserved when its link is
absent; there is no inactive control or extra keyboard stop. Month captions and
count badges cannot resize the search or move the type choices. The disclosure
summary stays in its action slot while its native content expands below the
toolbar; the native Apply fallback has its own row. Only the transaction
workspace reserves the viewport's scrollbar gutter, so shorter filtered lists
do not change the available horizontal space. Other workspaces retain their
existing layout.
All controls work through ordinary GET requests, including without JavaScript.
Enhanced filtering, card/recurrence
selection, sorting and pagination preserve viewport position and keyboard focus
through the [shared navigation contract](../frontend.md#preserve-the-users-location).

**All**, **Income** and **Expenses** use equal compact cells in a single horizontal
row. On smaller screens, labels and counts stack inside the same 44px target
instead of changing the row's geometry as values change. They count records
matching search, billed
month and exact date, before category and recurrence refinements. A fixed
transaction or installment plan counts once, not once per occurrence. Cards do
not total monetary amounts.

Existing `category=<id>` URLs retain their exact owned parent/fallback or
allocated-category meaning, without including descendants. The GET form carries
that criterion as an unlocalized hidden identifier and names the active category
inside the disclosure, with an individual Clear action. This preserves old links,
pagination and editor return context without an invisible restriction or a second
search widget. Other institution/product selectors in the application remain
available because exact record identity differs from matching text. Recurrence shortcuts
are All, Fixed (`is_fixed=True`), Installments (`is_fixed=False`, `installments>1`)
and One-off (`is_fixed=False`, `installments=1`). Income hides Installments and
clears an incompatible installment selection.

The list accepts `category=<id>` and `recurrence=fixed|installment|oneoff` alongside
`q`, `month=YYYY-MM`, `date=YYYY-MM-DD`, `type=INCOME|EXPENSE` and the existing
`sort` values. Invalid, unavailable or incompatible selections are ignored and
are not carried into navigation. Changing type or recurrence clears category;
filter changes reset pagination. With JavaScript, typing/deleting search text,
confirmed choices and dates apply dynamically through the shared live-filter
helper. **Apply filters** remains outside the disclosure as the complete native
GET fallback. Sorting and pagination preserve applied filters. Empty installations invite the
first transaction; empty filtered results offer filter recovery.

Billed month uses `Transaction.amount_for_month`: credit purchases follow their
statement cycle, while fixed and installment records appear in every applicable
month. Fixed includes ended recurrences when no month is selected. Month-based
filtering calculates eligibility once and reuses it for counts, categories and
results; without a month, filtering and aggregation stay in SQL.

The shared month filter retains its canonical `YYYY-MM` input without JavaScript.
Its enhanced panel offers a year and a searchable localized month name; confirming
a unique month match with Enter changes the billed month. Ambiguous names still
require an explicit selection. This month-only shortcut does not change financial
record pickers, and a category-name query does not automatically include that
category's descendants.

Authenticated users may export all their transactions or the active billed
month as UTF-8 CSV. Full exports download as `transactions.csv`; a monthly
export uses `transactions-YYYY-MM.csv`. The header is
`transaction_date,billed_month,title,transaction_type,category,payment_channel,bank,account,credit_card,currency,amount,total_amount,installments,is_fixed,fixed_until,notes,category_splits`.
For monthly exports, `amount` is the amount charged in that month while
`total_amount` retains the original transaction amount.

`category_splits` is empty for unsplit records or contains JSON objects with
`category_id`, `category` and native `amount`. A monthly export includes that
month's allocated cents, not the full source allocations. The ordinary export
preserves text verbatim. The deliberate `format=spreadsheet` variant adds
`-spreadsheet` to the filename and prefixes formula-like text with an apostrophe
while retaining numeric cells. It is a spreadsheet presentation format, not a
lossless interchange format; importers must not automatically strip that prefix.
These transaction reports are not cash statements and are rejected by the
[statement importer](ingestion.md) to avoid occurrence/settlement duplication.

Own transfers are visibly neutral and never receive income/expense colors or
category totals.

Transactions are editable and deletable by their owner. The transaction synchronization
service keeps banking movements and invoices coherent; audit-grade reversals are out
of scope.

## Form keyboard behavior

Categories now wait for the transaction type and use the shared searchable choice. Down/Up visibly navigate; Enter confirms; Escape/Tab cancel unconfirmed search text. Credit-card details wait for a specific card; recurrence dates wait for the checkbox. Advanced options are operable with Enter/Space.

Category splitting begins unchecked and reveals allocation rows only when
selected. Split choices share the same type compatibility, owned selectors,
bound-error recovery and complete native submission as the parent form.

With JavaScript, the allocation editor distributes exact integer cents across
automatic rows. Editing an amount fixes that row; clearing it makes it automatic
again. The remaining total is shared among automatic rows, with indivisible
cents assigned in row order. Adding/removing a category or changing the total
recalculates only automatic amounts. Existing allocations and bound POST values
are preserved until the user deliberately changes them. Limits/errors prevent
over-allocation without silently truncating entered values; each active category
still requires at least one cent. Remove category changes the formset DELETE
control rather than deleting a transaction. Without JavaScript, the labelled
DELETE checkbox and Add category submission retain the complete server path.
Classification still conserves one transaction, one payment and installment
category cents. The automatic/fixed UI state is not a financial source of truth.

Follow the [mandatory shared form contract](../frontend.md#keyboard-and-choice-contract).

## Contextual transaction entry

An explicit owned account/card shortcut selects its compatible funding context.
The originating URL, including its filters, is carried through an encoded local
`next` field and server validation. Save/Cancel return to that origin; the normal
ledger remains the fallback. Generated operations retain their edit locks.

The ordinary create/edit form includes an optional category-split checkbox and
the existing allocation formset. New splits start unchecked. A submitted total,
type and allocations are validated and saved together atomically; errors retain
the bound rows. With allocations selected, the first compatible category is the
structural parent category, while reports continue using the actual allocations.
The standalone split editor and legacy submissions remain available. No extra
bank movement is created by classification.

Save is the first native submit button in the server HTML. Enter from an ordinary
text/amount field therefore validates and saves, even when category splitting
is active or its controls are hidden. The native Add category fallback follows
the primary actions and requires explicit activation; it adds a bound row without saving the parent.
Its wrapper follows the same type/split visibility and error-recovery rules as
the allocation rows. Both actions remain native submissions without JavaScript;
searchable-choice Enter still only confirms the highlighted choice.
With JavaScript, Add category becomes a non-submit action immediately after the
allocation rows, before payment controls, in both visual and keyboard order.
