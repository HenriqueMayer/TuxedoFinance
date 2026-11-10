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
- A transfer in one currency has equal amounts on both sides.

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

## Preferences

`accounts.UserPreference` holds the currency of totals, the date order and
the Home blocks. Preferences change how values are shown. They never change
the currency or the date of a record.
