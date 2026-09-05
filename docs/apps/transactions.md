# `transactions`

`transactions` records categorized economic events. It no longer owns or
derives the account balance; settlement
is expressed through owned banking accounts, cards, invoices, and movements.

## Responsibilities

- CRUD, search and filtering for `INCOME` and `EXPENSE` events.
- Category assignment for income/expense.
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
type. Its native select remains the no-JavaScript fallback. Unclassified legacy
categories intentionally remain available for both types. Choices are limited to
the user's banks, accounts, cards and categories. Validation enforces:

- category required for every transaction;
- an income-only or expense-only category can only classify its matching type;
- PIX only on an account with `pix_enabled=True`;
- owned instruments that match the selected settlement path;
- installments only for credit cards and assigned across invoices without
  creating account movements for individual installments.

Synchronization derives recurrence and installment amounts from the original
transaction without inserting new `Transaction` rows. It creates or updates
movements and invoices through a projection horizon, normally twelve months
beyond today. Future-effective rows may exist in the database, but balance
queries exclude them until their effective date. See
[request-time synchronization](../architecture.md#request-time-synchronization).

## Listing and reporting semantics

Search covers title, notes, category, bank, account and card labels. Filters
distinguish exact event date, billed month, transaction type and banking
instrument. The billed-month filter follows the month in which money is charged:
it shifts credit-card purchases according to the card cycle and includes each
applicable occurrence of fixed and installment transactions.

Authenticated users may export all their transactions or the active billed
month as UTF-8 CSV. Full exports download as `transactions.csv`; a monthly
export uses `transactions-YYYY-MM.csv`. The header is
`transaction_date,billed_month,title,transaction_type,category,payment_channel,bank,account,credit_card,currency,amount,total_amount,installments,is_fixed,fixed_until,notes`.
For monthly exports, `amount` is the amount charged in that month while
`total_amount` retains the original transaction amount.

Own transfers are visibly neutral and never receive income/expense colors or
category totals.

Transactions are editable and deletable by their owner. The transaction synchronization
service keeps banking movements and invoices coherent; audit-grade reversals are out
of scope.
