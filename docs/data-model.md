# Data model

Every record belongs to one user. This file names the records and the rules
that connect them. The detailed rule of a calculation is in the docstring of
its module.

## Sources and derived rows

A **transaction** is a source: what the owner recorded. Account **movements**
and card **invoices** are derived from transactions by the ledger
synchronization (`ledger.services.sync_user_ledger`). Product code does not
write a derived row directly.

- Saving or deleting a source marks the ledger of its owner as stale and
  synchronizes after the commit (`ledger.ledger_state`).
- Sign-in and `migrate` also synchronize. So does a read of the Wallet when
  the ledger is stale, which happens when a new month starts.
- `manage.py reconcile_ledger` synchronizes after a change that sends no
  signal, for example a direct database edit.

## Banking

| Record | Meaning |
|---|---|
| `Bank` | A named group of accounts |
| `BankAccount` | An account with a currency and an opening balance |
| `DebitCard`, `CreditCard` | A card of an account. A credit card has a closing day and a due day |
| `CardInvoice` | The statement of a card for one reference month. Derived |
| `InvoicePayment` | A payment that the owner confirmed for an invoice |
| `CardInvoiceCredit` | A credit on a statement, for example a refund |
| `BankTransfer` | A movement of an amount between two accounts |
| `BankMovement` | One credit or debit of an account. Derived, or written by a service |
| `BalanceCheckpoint` | A balance that the owner read on the bank statement, for reconciliation |
| `LoyaltyProgram`, `LoyaltyEntry`, `RewardRedemption` | Points and miles |
| `ExchangeRate` | A rate that the owner recorded for a date |

Rules:

- The balance of an account is its opening balance plus its movements up to a
  date (`banking.services.account_balance`).
- The statement month of a purchase follows the closing day
  (`banking.card_calendar`).
- An invoice has two settlement modes (`banking.settlements`). Automatic: the
  invoice is paid from the account on its due date. Confirmed: it stays open
  until confirmed payments cover it. The mode of a card applies to invoices
  from the month it was turned on; an invoice that uses confirmed payments
  keeps that mode.
- The state of an invoice (scheduled, partly paid, overdue, paid) depends on
  the date and is calculated when it is read.
- A transfer in one currency has equal amounts on both sides. A transfer
  between currencies has one amount for each side.
- `banking.loyalty` records the points that the owner types and undoes them.
  A redemption (`banking.services.create_reward_redemption`) writes a points
  debit and a credit movement of kind `REWARD` in the account.
- An exchange rate belongs to a pair of currencies and a date. A pair has one
  rate for each date. `banking.services.convert` uses the latest rate on or
  before the date, or the inverse of the opposite pair.

## Ledger

| Record | Meaning |
|---|---|
| `Category` | A name for classifying entries, with an optional type and parent |
| `Transaction` | An income or an expense on an account, a debit card or a credit card |
| `TransactionSplit` | A part of a transaction in another category |
| `ScheduleAmount` | A new amount of a repeating entry from a month |
| `OccurrenceOverride` | A change of one month of a repeating entry: skipped, adjusted or confirmed |
| `LedgerSyncState` | The last synchronization of a user |
| `ImportBatch`, `ImportedRow`, `ExternalStatementIdentity` | Statement import |

Rules:

- The **occurrence engine** (`ledger.schedule`) turns a source into dated
  amounts: one for a single entry, one for each installment, one for each
  month of a repeating entry. Every reader of months uses it.
- An occurrence has a *reference month*: the statement month for a credit
  card, the month of the occurrence otherwise.
- `Transaction.clean` holds the rules of an entry: income is received in an
  account, installments need a credit card, a repeating entry has no
  installments, and every referenced record has the same owner.
- A repeating entry that asks for confirmation changes the account only in
  the months that the owner confirmed (`ledger.commitments`).
- A category with records is not deleted.
- Statement import has four states: `STAGED` (a CSV file that waits for its
  columns), `READY` (in review), `CONFIRMED` and `UNDONE`.
  `ledger.statement_import` validates each decision, creates the records of a
  confirmation in one database transaction and keeps a snapshot of each
  created record; the undo is refused when a snapshot no longer equals its
  record. The confirmation compares a digest of the review, so a review that
  changed in another window is not confirmed. `ledger.import_review` proposes
  the columns and the first decisions; it creates no financial record.

## Investments

| Record | Meaning |
|---|---|
| `InvestmentProduct` | A named product at a bank. It holds positions |
| `Asset` | What is held: its currency, how it is valued, and the opening position |
| `Investment` | One operation: a deposit, a withdrawal or a yield |
| `PriceObservation` | A unit price that the owner recorded for a date |
| `PositionPlanningSetting` | Whether a cash position counts in the plan. Used when Plan is built |

Rules:

- A **position** is one asset in one product. The API creates both together
  (`investments.operations.create_position`), so the asset identifies the
  position and `asset.opening_product` is its product.
- An asset is valued as a *monetary* balance or in *units* with a price.
- The **position replay** (`investments.positions.replay_positions`) reads
  the opening position and the operations in date order and gives the
  quantity, the remaining cost and the realized gain. Every reader of
  positions uses it. A write is refused when the replay finds a withdrawal of
  more than the position holds, on any later date too.
- A deposit from an account and a withdrawal to an account each own one
  account movement (`investments.services.sync_investment_ledger`). A yield
  moves no money.
- The value of units is the quantity times the last price recorded on or
  before the date. Without a price, the value is the remaining cost.
- A monetary yield can be given as the balance after it; the yield is the
  difference from the balance before (`calculate_monetary_yield`).
- An asset with an opening position is not deleted by the ORM
  (`investments.signals`). `delete_position` removes a position that has no
  operation.
- An operation keeps the exchange rate of its date for totals in the base
  currency (`refresh_fx_snapshot`).

## Plan

| Model | Purpose |
|---|---|
| `planning.SpendingLimit` | An amount for each month from `start_month` on. Without a category it is the limit of the month; with one it is the budget of that category |
| `planning.FinancialGoal` | A target amount in one currency, with an optional date |
| `planning.GoalAllocation` | The part of one balance that a goal reserves: of a bank account or of a monetary asset |

Rules:

- A limit row holds until a later row of the same category. A row with an
  empty amount ends the limit. `limits.set_limit` removes the rows from its
  month on and adds one row only when the value changes, so the months before
  keep their value.
- `limits.month_plan` compares the limits with the expenses of the month. It
  reads the occurrences of `reports.home`, in the base currency only. A
  budget adds the allocations of its category and of every descendant.
- `goals.read` is the only reader of goal progress. The backed amount of a
  reservation is limited by the positive balance of its source; reservations
  of one source that ask for more than the balance share it in proportion.
  Reservations of archived goals claim nothing.
- `goals.set_reservation` locks the owner row, so two requests cannot reserve
  the same part of a balance.
- A reserved account keeps its currency (`BankAccount.clean`). A reserved
  asset keeps its currency and its valuation mode (`Asset.clean`). Deleting
  the account or the asset deletes its reservations.
- These records never create a movement.

`planning.SavedSheet` holds a name, a count of months and the changes of a
sheet as JSON: changed cells by row key and month, and the added rows.

`sheet.compose` reads the months ahead from rows that the ledger already
derived: the bank movements dated after today, the invoices that wait for a
confirmed payment, and the expected months of repeating entries. It applies
the changes to a copy in memory and returns the rows and the totals. The API
calls `ensure_ledger_current` first, so the derived rows cover the months.

`planning.tools` holds the calculators. `planning.tax_rules` holds one
payroll table for each year, with its review date and sources.

## Net worth

`reports.worth` reads the net worth on a date: account balances plus the
valuation of the positions, less the incurred card debt. The module docstring
defines incurred and paid amounts. Each amount is converted to the base
currency with the rate of that date; an amount without a rate adds nothing
and its currency is listed.

## Preferences

`accounts.UserPreference` holds the currency of totals, the date order and
the Home blocks. Preferences change how values are shown. They never change
the currency or the date of a record.
