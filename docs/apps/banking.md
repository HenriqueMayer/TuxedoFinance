# `banking`

The approved replacement for `payments`. This app owns banks, currency-specific
accounts, the account ledger, PIX, debit and credit cards, card invoices, and
loyalty programs. It starts from a clean schema; `PaymentMethod` is not retained.
It also owns the user's banking profile and base reporting currency.

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
    └── LoyaltyEntry
```

A `Bank` may have any number of `BankAccount` rows, including multiple accounts
in the same currency. Each account has exactly one currency. Its available
balance is `opening_balance + sum(BankMovement.signed_amount)`; transaction rows
are never added to that formula independently.

## Immediate and deferred settlement

- **PIX** is a standard account capability and is enabled by default. The user
  may disable it for an account that does not support PIX.
- **Debit card** and **PIX** settlements create a `BankMovement` on the event
  date and affect the account balance immediately.
- A **credit-card purchase** becomes an invoice item. It affects spending
  reports on the purchase date but does not create an account debit then.
- A `CardInvoice` is paid on its `due_date` by one debit movement against the
  linked account. Invoice items are not debited again, preventing double count.
- An external PIX is an ordinary categorized `INCOME` or `EXPENSE` transaction,
  with its immediate ledger movement. PIX is not synonymous with transfer.

## Transfers

A transfer between the user's own accounts produces two linked movements: an
outflow in the source account and an inflow in the destination account. The pair
may carry different native amounts for a cross-currency transfer. Those amounts
preserve the effective conversion; no separate quoted-rate field is stored. It
is classified as `TRANSFER`, never as income or
expense, and is excluded from cash-flow KPIs.

## Cards and invoices

Both `DebitCard` and `CreditCard` belong to one `BankAccount`. A credit card also
stores its statement-closing rule and due day. Each invoice has a statement
period, due date, status, native currency, item total, and the single settlement
movement when paid. Partial payments, if introduced, must be represented as
explicit invoice payments; they must not mutate purchase amounts.

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

A redemption records the points used, target monetary amount and currency, IOF
amount, and the funding instrument used to pay IOF. When IOF is positive, its
funding instrument is required and must be one owned account, debit card, or
credit card. Debit/account funding settles immediately; credit funding enters
the corresponding card invoice under the same no-double-counting rule.

## Multicurrency

Accounts, transactions, invoices, loyalty monetary targets, and investment
assets retain native currency and amount. Reports also show historical values in
the user's base currency. Conversion uses the rate effective on the event date
and stores/references that rate; later exchange-rate updates never rewrite a
closed period. Missing rates are surfaced explicitly instead of treating unlike
currencies as equal or silently omitting them.

## Integrity

- Every queryset and relationship is scoped to the authenticated user.
- Referenced banks, accounts, cards, invoices, movements, rates, and loyalty
  ledgers are protected from destructive cascade.
- Posted ledger and loyalty entries are corrected by reversing entries, not by
  rewriting history.
- Exactly one settlement path applies to an event: immediate account movement or
  deferred invoice settlement, never both.

## Breaking replacement

The `banking` app replaces `payments`, its routes, templates, navigation item,
and `PaymentMethod` foreign keys. This is a clean migration reset: development
and deployed SQLite databases must be recreated for the release. No compatibility
adapter, data conversion, or dual-write period is part of the approved scope.
