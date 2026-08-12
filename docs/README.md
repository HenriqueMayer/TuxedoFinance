# CashFlow Documentation

Technical and product documentation for the approved banking/multicurrency
breaking release.

## Where to start

| Doc | Covers |
|---|---|
| [ProductRequirementsDocument.md](ProductRequirementsDocument.md) | Approved scope, requirements, acceptance criteria and clean-reset delivery. |
| [architecture.md](architecture.md) | Domain boundaries, posting workflows and sources of truth. |
| [data-model.md](data-model.md) | Models, relationships, accounting rules, FX and reset contract. |
| [frontend.md](frontend.md) | Server-rendered design system and updated banking UI structure. |
| [deployment.md](deployment.md) | Existing Docker/static delivery; domain reset details remain in the PRD/data model. |

## Per-app reference

- [apps/core.md](apps/core.md) — project settings, currency registry and formatting.
- [apps/pages.md](apps/pages.md) — public landing page.
- [apps/accounts.md](apps/accounts.md) — native Django authentication.
- [apps/categories.md](apps/categories.md) — income/expense categories.
- [apps/banking.md](apps/banking.md) — banks, accounts, movements, PIX, cards,
  invoices, loyalty and historical FX.
- [apps/transactions.md](apps/transactions.md) — categorized economic events and
  settlement behavior.
- [apps/dashboard.md](apps/dashboard.md) — cash, cash-flow, liabilities,
  investments and net-worth read models.
- [apps/investments.md](apps/investments.md) — separate position ledger using
  banks/accounts for provider and cash endpoints.

`apps/payments.md` was removed because the `payments` app is replaced by
`banking`; there is no compatibility layer.

## Documentation status

These documents describe the approved target release, not the legacy schema
currently present in older databases. The release requires fresh migrations and
a new SQLite database. Existing data is not automatically migrated.
