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

Bank overviews and account cards consume grouped balances instead of calling an
aggregate for each account. The planning toggle uses an owned, CSRF-protected
POST; the same change works with a normal form submission without JavaScript.

## Contextual daily actions

The workspace is named Accounts. Its overview lists owned institutions as links;
opening one gives each account a card with a visible New transaction shortcut.
The deliberate account menu retains Edit / reserve, own transfer, card creation
and deletion. Validated account shortcuts and explicit local `next` origins
preserve the return destination through Save/Cancel, errors and planning POST
fragments. Credit cards expose a purchase shortcut and scoped invoice list beside
their dated settlement mode. Invoice filters validate ownership and keep the
selection during pagination. Paused imports have no account shortcut.

Home and bank details link directly to an invoice. Its due date, status, native
total, confirmed amount and remaining amount precede payment entry and sources.
Payment entry explicitly records an already completed bank payment. Successful
entry stays beside the invoice result; Cancel returns to the supplied local
origin. Source editors and payment editors return to the same invoice section.


## Bank overview, details and dynamic consultation

The overview shows all owned banks, using one link per institution with its name,
color marker and account/card counts. It has no text filter or inline account
rows. Retired overview `q` parameters are ignored. The all-bank available-money
summary stays on this overview; its native Balance details disclosure contains
bank totals, monetary cash pots and set-aside amounts. Missing-rate and reserve
shortfall warnings remain visible without opening that disclosure.

Each bank page contains the institution's accounts, monetary cash pots, reserves
and loyalty programs. An account card has three distinct layers: its name and
daily actions, a labelled Balance / Set aside / Available grid, then its cards.
The planning participation POST stays outside the amount grid. Account details
contains opening-balance evidence and debit-card administration. Its ellipsis
menu retains editing/reserving, own transfer, both card creation actions and
account deletion. Each credit card appears once, with invoice/purchase links,
closing/due days, settlement mode and deliberate Edit/Delete options.

Participation-excluded accounts and cash positions appear inside Reserves with
explicit include/exclude POST actions. Same-record updates preserve disclosure
state, focus and position. Available money differs from real balances; exclusion
never hides debts or removes financial history. Both full pages and planning
fragments prefetch only the user's cards, including legacy cross-owner links.
Fragment shortcuts retain the submitted validated page origin, never the POST
endpoint. Complete native POSTs remain supported.

Recent activity is a native secondary disclosure containing redemptions,
invoices and ledger movements. Redemption edit/error responses open it; stable
record anchors reveal the appropriate native disclosure after full and boosted
page navigation. Unrelated background updates do not reopen it. The bank header keeps Add account and Invoices
visible, with bank editing, color, loyalty creation and deletion in its menu.

Cash pots use a responsive grid of compact record cards. Asset name, product
and native currency precede Balance and Available; the participation POST stays
below those amounts. A single redemption hint belongs to the group, rather than
every row. Set balance aside explicitly names the action, while Use in planning
restores participation. Reserves, actual balances and existing goals keep the
same calculation and ownership rules.

Invoices opens a paginated card overview. Every owned card remains discoverable
without invoices; the block shows its institution, account, currency and matching
invoice count. Month/status filters require matching invoice evidence, while
search/bank filters can find empty cards. The count excludes foreign-user legacy
invoice references. A deliberate card link opens its own paginated invoice
history at `/banking/credit-cards/<id>/invoices/`, preserving criteria. Months,
due dates, settlement status, total, remaining amount and payment links stay
available there. Clear retains the owning card and any validated return origin.
Legacy `?card=<id>` links redirect after ownership/canonical-ID validation; invalid
or foreign IDs remain 404s. Card and invoice pagination are independent.

Invoices and local exchange rates retain one primary live search and native
Filters criteria, with fixed trigger/Clear slots. Opening criteria adds fields
below the rail without moving the trigger. Active counts exclude text search.
Controls remain mounted while results/status update; initial errors reopen
criteria and retain bound values. Card selection is page navigation through the overview, rather than another
record picker in the filter panel. Invoice month uses the shared named-month/year
enhancement over the native ISO field; malformed month text stays recoverable.
Every filter retains native GET submission without JavaScript.

Banking density is scoped to `.banking-workspace`, including invoice
consultation/payment, exchange rates and form containers/actions. Headings,
separators and record surfaces clarify hierarchy without changing financial
values, native fields or shared searchable-choice behavior. Row menus use
record-specific accessible names and deliberate activation. Touch targets stay
at least 44px; fine-pointer desktops may use 36px actions. Rate forms retain
Save/Cancel and explicit origins. Local reference rates never rewrite evidence
already stored in financial operations.
