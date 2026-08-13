# `transactions`

`transactions` records categorized economic events. It no longer owns or
derives the account balance; settlement
is expressed through owned banking accounts, cards, invoices, and movements.

## Responsibilities

- CRUD, search and filtering for `INCOME` and `EXPENSE` events.
- Category assignment for income/expense.
- Amount, event date, recurrence and notes; reporting uses the current project
  currency setting.
- Selection of PIX, debit card, credit card, or direct account as the settlement
  path. Own transfers are recorded separately in Banking.
- Atomic delegation to `banking` posting services.

`INVESTMENT` is removed from `TransactionType`. Investment deposits and
withdrawals belong to the investments workflow and create banking movements
without becoming income or expense.

## Settlement behavior

| Path | Transaction classification | Cash effect |
|---|---|---|
| External PIX received | `INCOME` | Immediate account credit. |
| External PIX sent | `EXPENSE` | Immediate account debit. |
| Debit card/direct account | `INCOME` or `EXPENSE` | Immediate movement. |
| Credit card | Usually `EXPENSE` | Added to `CardInvoice`; no purchase-date account movement. |
| Own-account transfer | Banking transfer | Paired debit/credit movements; excluded from income/expense. |

PIX is therefore a settlement capability, not a transaction type. A PIX to or
from another person remains a normal categorized transaction.

## Form and validation

The form captures title, positive amount, type, category, event date, settlement
path/instrument, recurrence fields, and notes. Choices are limited to the user's
banks, accounts and cards. Validation enforces:

- category required for every transaction;
- PIX only on an account with `pix_enabled=True`;
- owned instruments that match the selected settlement path;
- installments only for credit cards and assigned across invoices without
  creating account movements for individual installments.

Future recurrences are projections until posted. When an immediate recurrence
becomes effective it creates one transaction occurrence and one movement; a
credit recurrence creates one invoice item. Projection rows never alter the
ledger by themselves.

## Listing and reporting semantics

Search covers title, notes, category, bank, account and card labels. Filters
distinguish event date, transaction type and banking instrument. Own transfers
are visibly neutral and never receive income/expense colors or category totals.

Transactions are editable and deletable by their owner. The related banking
service keeps ledger and invoice data coherent; audit-grade reversals are out
of scope.
