# `banking`

This app owns banks, currency-specific accounts, the account ledger, PIX, debit
and credit cards, card invoices, and loyalty programs. Per-user base reporting
currency preferences are configured per user in Settings.

## Domain

```text
Bank
├── BankAccount (one currency, opening balance)
│   ├── BankMovement (authoritative ledger)
│   ├── PIX capability (enabled by default)
│   ├── DebitCard
│   └── CreditCard
│       └── CardInvoice
└── LoyaltyProgram (optional)
    ├── LoyaltyEntry
    └── RewardRedemption
```

A `Bank` may have any number of `BankAccount` rows, including multiple accounts
in the same currency. Each account has exactly one currency. Its available
balance is its applicable opening balance plus
`sum(BankMovement.signed_amount)`; transaction rows
are never added to that formula independently.

New nonzero openings require `BankAccount.opening_date`. Cutoff reads include a
dated opening only on or after that date, and the date cannot follow an existing
movement. Older openings keep a null date through migration rather than an
invented historical baseline. Current balances retain them, while dated wealth
discloses that their baseline is unknown. Statement confirmation requires the
owner to resolve a nonzero unknown account baseline first.

Bank list and account detail views synchronize derived transactions and invoices
before reading balances. These requests may write to the ledger; the balance
helpers themselves only query it. The synchronization service lives in
`transactions`, while `banking` owns the resulting models.

## Immediate and deferred settlement

- **PIX** is a standard account capability and is enabled by default. The user
  may disable it for an account that does not support PIX.
- **Debit card** and **PIX** settlements create a `BankMovement` on the event
  date and affect the account balance immediately.
- A **credit-card purchase** becomes an invoice item. It affects spending
  reports in the statement month, including the appropriate installment or
  recurrence amount, and does not create a purchase-date account debit.
- By default a `CardInvoice` is projected as paid on its `due_date` by one debit
  movement against the linked account. Optional manual settlement replaces
  that projection with explicitly confirmed payments. Invoice items are not
  debited again, preventing double count.
- An external PIX is an ordinary categorized `INCOME` or `EXPENSE` transaction,
  with its immediate ledger movement. PIX is not synonymous with transfer.

## Transfers

A transfer between the user's own accounts produces two linked movements: an
outflow in the source account and an inflow in the destination account. The pair
may carry different native amounts for a cross-currency transfer. The transfer
persists its source and target currencies, applied rate, effective date,
optional source-rate reference, and conversion status. That snapshot preserves
the historical conversion even if the current rate later changes. The transfer
is classified as `TRANSFER`, never as income or expense, and is excluded from
cash-flow KPIs.

## Cards and invoices

Both `DebitCard` and `CreditCard` belong to one `BankAccount`. A credit card also
stores its statement-closing rule and due day. Each invoice stores a reference month, due date, status, and amount; its
native currency comes from the linked card account. Synchronization derives the
total from source records. Automatic mode creates one due-date movement,
including for future invoices; cash includes it only once effective. Automatic
paid status describes the local projection, not bank confirmation.

### Optional manual settlement

`CreditCard.manual_settlement_from` is an owner-selected due-date boundary.
Its default is null, preserving automatic behavior for existing and new cards.
Invoices due before the boundary retain their prior behavior. An invoice that
has entered manual mode keeps `CardInvoice.manual_settlement=True`, preserving
confirmed evidence even if the card setting subsequently changes.

Manual invoices have no synthetic due-date debit. `InvoicePayment` records a
positive native amount, actual date, owned funding account, notes and unique
confirmation UUID. The account must have the invoice currency; the payment
cannot be in the future or before its known account opening. Each confirmation
posts exactly one linked debit `BankMovement` on the actual payment date.
Repeating the same UUID with the same payload returns the existing payment;
reuse with different values is rejected. Payments, movements and invoice status
are saved atomically by `banking.settlements.save_invoice_payment`.

Partial payments are supported, and new or edited confirmations cannot exceed
the current invoice total after other payments. Status is scheduled, partial,
overdue or paid according to confirmed payments through the cutoff. Editing or
deleting a confirmation updates or removes its own cash movement without
altering purchases. A source purchase correction/deletion does not erase real
payments: excess confirmed payment becomes visible card credit in wealth.
Payment-bearing invoices survive source/horizon reconciliation.

`manual_invoice_obligations(user, as_of)` exposes outstanding manual amounts
for due-date forecasts. These planned obligations do not post cash or count as
another expense. Historical readers filter confirmations by their actual date
and must not use today's paid flag as evidence of an earlier payment.

## Loyalty

`LoyaltyProgram` belongs to the user and may be independent, linked to a `Bank`,
linked to one or more cards, or use both links. Its `LoyaltyEntry`
ledger supports:

| Kind | Meaning |
|---|---|
| `INVOICE_AWARD` | Points awarded from an eligible card invoice. |
| `PURCHASE` | Points acquired for money. |
| `ADJUSTMENT` | Manual positive or negative correction. |
| `EXPIRATION` | Points removed on expiry. |
| `REDEMPTION` | Points spent for a benefit or monetary target. |

The entry form follows the project-wide progressive-disclosure contract. An
invoice award reveals only its invoice selector; a points purchase reveals only
the account/card funding selectors and cash amount; adjustment, expiration and
redemption entries reveal neither conditional branch. Changing the entry kind
clears values from the branch that became inactive, while server validation
remains authoritative and the no-JavaScript form remains complete.

`RewardRedemption` coordinates a redemption rather than replacing the points
ledger. It records the points used, target account and monetary amount, IOF, and
an optional IOF funding instrument. The service links it to a debit
`LoyaltyEntry`, a credit `BankMovement` for the reward, and an IOF movement when
IOF is paid from an account. Credit-card IOF is included in the card's aggregate
invoice by ledger synchronization and settles through the card's automatic or
manual invoice mode. Positive
IOF requires exactly one owned bank account or credit card; zero IOF permits
neither.

After saving, the redemption form opens the receiving bank's **Reward
redemptions** history. Each bank shows its twenty most recent redemptions where
one of its accounts receives the reward or funds the IOF, including via a credit
card. This also exposes existing records and independent-program redemptions.
Each row identifies points, date, native reward currency/account and IOF
currency/instrument. Card-funded IOF identifies its statement month and due
date, including when the card belongs to a different bank. Account-funded IOF
identifies the immediate debit; zero IOF is explicit. **Edit redemption** opens
an inline, bound form in this section; validation errors remain there. The edit
updates its original points debit and reward movement, then reconciles IOF and
invoices atomically. Changing the program checks its available points; editing
the same program restores the old debit before checking the replacement.

Every positive IOF owns one expense `Transaction.reward_redemption` (a nullable,
unique source link), categorized as IOF in its funding currency. The migration
backfills existing positive IOF without changing bank movements. A compatible
IOF category is reused; an income-only name collision uses a numeric suffix.
Transaction amounts support the same 16 digits as redemption amounts. The
expense appears in transaction lists, CSV and instrument/category reports, but
its edit/delete endpoints and admin actions are blocked; its source points entry
is also protected against independent edits/deletion. Manage it from the
redemption section. Account IOF keeps its original immediate movement; card IOF
settles through the aggregate invoice. Ledger, reports and commitment snapshots
count each charge once, preserving existing `iof:<id>` scenario identities.
Setting IOF to zero removes the derived expense and previous IOF funding.
An explicitly selected older redemption remains visible for editing beyond the
usual twenty-row history limit.

## Multicurrency

Bank accounts, invoices and investment assets retain their configured native
currency. Consolidated reporting uses the authenticated user's
`UserPreference.base_currency`, which defaults to BRL and is editable in
Settings. Historical transfer reports use each transfer's persisted FX
snapshot and effective evidence date; read-time rates serve explicitly labeled
current or cutoff-date valuations.
Missing rates preserve native amounts and mark the conversion incomplete.
Changing the preference never mutates native amounts. Other banking entities
use read-time conversion rather than captured operation snapshots. Dated wealth
requests cutoff-date rates; current screens request their stated valuation date.

The exchange-rate list provides create, edit and confirmed delete actions for
the signed-in user's rates. Forms and cancellation return to that list. Editing
or deleting a rate can change current valuations or leave a currency without a
rate. Persisted transfer and investment FX snapshots retain their recorded
amounts, currencies, rate and date; deletion clears only the optional source-rate
reference. Currency pairs must differ, rates must be positive, and each pair/date
must be unique per user.

## Integrity

- Every queryset and relationship is scoped to the authenticated user.
- Referenced banks, accounts, cards, invoices, movements, rates, and loyalty
  ledgers are protected from destructive cascade.
- Account currency cannot change while any goal reservation references it,
  including an archived goal, even if no cash movement has yet been recorded.
- Personal ledger and loyalty entries remain editable; audit-grade reversal
  workflows are out of scope.
- Exactly one settlement path applies to an event: immediate account movement or
  deferred invoice settlement, never both.

## Supported upgrades

The schema replacement described in early development notes predates supported
releases. Released installations use the existing migration chain; never delete
or regenerate migrations to upgrade. Follow the [Docker upgrade guide](../docker.md)
for backups, version selection and restoration.

## Form keyboard behavior

Banks, accounts, cards, programs and invoices use shared searchable choices. Multiple eligible cards use searchable checkboxes with Tab/Space and retain selection when filtered. Purchased-points amounts wait for a funding source; IOF sources wait for a positive amount. A deliberate source change clears the incompatible alternative.

Follow the [mandatory shared form contract](../frontend.md#keyboard-and-choice-contract).

## Monthly planning availability

`BankAccount.planning_enabled` defaults to true and `reserved_amount` defaults
to zero. Reservations use the account's native currency and persist until the
owner changes them; they do not create movements or reset each month. An included
account sets aside the greater of its manual reserve and active goal allocations,
capped at its positive balance. An excluded account
sets aside its positive balance. Negative balances remain visible in planning,
and excluded funding never removes an invoice or other obligation.

`banking.services.get_planning_availability(user, as_of=None)` returns bank
balances, monetary cash pots, set-aside amounts, availability, reserve shortfall
and missing currencies. Positions are calculated by product and asset, with
opening positions counted once. The date cutoff excludes future movements and
operations and openings dated after the cutoff. Active goal allocations also
reserve monetary cash pots; archived goals release availability while retaining
their source references. Shrinking balances show a shortfall instead of
manufacturing backing. This is a funding snapshot before upcoming bills, not a second
ledger or an amount that can be spent without redeeming a cash pot.

The helper accepts an optional request-owned `ConversionContext` for shared FX
lookups. Reservations are earmarks of existing cash, not withdrawals, expenses
or new assets. They do not reduce net worth. See [planning](planning.md).

Bank lists and detail tables consume grouped balances instead of calling an
aggregate for each account. The planning toggle uses an owned, CSRF-protected
POST; the same change works with a normal form submission without JavaScript.

## Contextual daily actions

Accounts remain grouped by institution, but the workspace is named Accounts.
Each row has an activation-only Update account disclosure for a new transaction,
statement import or owned transfer. Validated account shortcuts and local `next`
origins preserve the search and return destination through Save/Cancel and errors.
Credit cards expose a purchase shortcut and a card-scoped invoice list alongside
their dated settlement mode. Invoice filters validate card ownership and keep
the selection during pagination.

Home and bank details link directly to an invoice. Its due date, status, native
total, confirmed amount and remaining amount precede payment entry and sources.
Payment entry explicitly records an already completed bank payment. Successful
entry stays beside the invoice result; Cancel returns to the supplied local
origin. Source editors and payment editors return to the same invoice section.


## Compact accounts and dynamic consultation

Banks use native details/summary with stable IDs: a closed group shows only its
name, color bookmark and expansion affordance. Participation-excluded accounts
and cash positions appear inside a separate Reserves disclosure, with explicit
include/exclude POST actions. Same-record refreshes preserve disclosure state,
focus and position. Available cash differs from balances and must remain labelled.

An open bank separates accounts, cash pots, reserves, credit cards and loyalty
with section titles and thin dividers. Add account and Bank details remain
visible; bank editing and marker color use a deliberate options menu. Bank detail
shows each credit card once: invoice and purchase shortcuts share the card row
with its type, closing/due days, settlement mode and administrative options.
Account instruments retain opening balances, debit cards, card creation and
account actions. This organization changes neither balances nor invoice policy.

Invoices and local exchange rates use the shared dynamic search/filter contract,
owner-scoped choices and native fallback. Invoice rows keep reference month, due
amount, paid/remaining amounts and settlement mode visible. Rate forms use the
shared form renderer, deliberate Save/Cancel and contextual origins; local
reference rates do not rewrite evidence saved in financial operations.

Accounts, invoices and exchange rates share a compact consultation bar. Search
stays visible, and optional invoice/rate criteria use a native Filters disclosure
with an active-criteria count; search text does not increase this count. Clear
remains beside the bar. Criteria stay in the stable GET form while the live
helper replaces results and status only. Invalid initial responses open the
criteria and retain bound values and field errors. Complete native submissions
remain available without JavaScript. Invoice month uses the shared searchable
month-name/year enhancement over its original ISO month field; malformed native
month text retains a plain, recoverable field rather than becoming an empty date.
