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
may carry different native amounts for a cross-currency transfer. The transfer
persists its source and target currencies, applied rate, effective date,
optional source-rate reference, and conversion status. That snapshot preserves
the historical conversion even if the current rate later changes. The transfer
is classified as `TRANSFER`, never as income or expense, and is excluded from
cash-flow KPIs.

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

Bank accounts, invoices and investment assets retain their configured native
currency. Consolidated reporting uses the authenticated user's
`UserPreference.base_currency`, which defaults to BRL and is editable in
Settings. Historical transfer reports use each transfer's persisted FX
snapshot and effective evidence date; current rates are reserved for explicitly
labeled current valuations.
Missing rates preserve native amounts and mark the conversion incomplete.
Changing the preference never mutates native amounts. Other banking entities
remain on live/current conversion until a future roadmap item extends coverage.

## Integrity

- Every queryset and relationship is scoped to the authenticated user.
- Referenced banks, accounts, cards, invoices, movements, rates, and loyalty
  ledgers are protected from destructive cascade.
- Personal ledger and loyalty entries remain editable; audit-grade reversal
  workflows are out of scope.
- Exactly one settlement path applies to an event: immediate account movement or
  deferred invoice settlement, never both.

## Breaking replacement

This schema has no compatibility adapter, automatic conversion, or dual-write
period for legacy financial data. Refer to the data model's breaking-release
section before attempting an upgrade.
