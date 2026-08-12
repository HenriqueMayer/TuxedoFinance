# `transactions`

`transactions` records categorized economic events. It no longer owns or
derives the account balance and no longer references `PaymentMethod`; settlement
is expressed through owned banking accounts, cards, invoices, and movements.

## Responsibilities

- CRUD, search and filtering for `INCOME` and `EXPENSE` events.
- Category assignment for income/expense.
- Native currency, amount, event date, recurrence and historical base conversion.
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

The form captures description, positive native amount, currency, type, category,
event date, settlement path/instrument, recurrence fields, and notes. Choices are
limited to the user's banks, accounts and cards. Validation enforces:

- category required for every transaction;
- PIX only on an account with `pix_enabled=True`;
- debit/credit card currency compatible with the linked account;
- owned instruments that match the selected settlement path;
- installments only for credit cards and assigned across invoices without
  creating account movements for individual installments.

Future recurrences are projections until posted. When an immediate recurrence
becomes effective it creates one transaction occurrence and one movement; a
credit recurrence creates one invoice item. Projection rows never alter the
ledger by themselves.

## Listing and reporting semantics

Search covers description, notes, category, bank, account and card labels.
Filters distinguish event date, settlement date, transaction type, currency,
banking instrument and invoice. Native and base amounts are shown together when
they differ. Own transfers are visibly neutral and never receive income/expense
colors or category totals.

Deletion is allowed only for unposted drafts. Posted events are reversed through
the banking service so ledger, invoice, and transaction history stay coherent.
