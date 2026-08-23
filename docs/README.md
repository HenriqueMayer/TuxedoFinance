# Tuxedo Finance Documentation

Technical and product documentation for the approved banking/multicurrency
breaking release.

## Where to start

| Doc | Covers |
|---|---|
| [Interface preview](https://henriquemayer.github.io/TuxedoFinance/) | Bilingual static tour of the application using synthetic financial data. |
| [ProductRequirementsDocument.md](ProductRequirementsDocument.md) | Approved scope, requirements, acceptance criteria and clean-reset delivery. |
| [architecture.md](architecture.md) | Domain boundaries, posting workflows and sources of truth. |
| [data-model.md](data-model.md) | Models, relationships, accounting rules, FX and reset contract. |
| [frontend.md](frontend.md) | Server-rendered design system and updated banking UI structure. |
| [operations.md](operations.md) | Dependency updates and owner-managed SQLite backup, restore, retention and rehearsal procedures. |
| [versioning.md](versioning.md) | Semantic versioning policy, automated consistency checks and release workflow. |
| [coverage-baseline.md](coverage-baseline.md) | Coverage report, 70% line floor, branch-reporting policy and local commands. |

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

## Documentation status

These documents describe the approved target release, not the legacy schema
currently present in older databases. The release requires fresh migrations and
a new SQLite database. Existing data is not automatically migrated.

The repository does not include a runtime demo database, shared account, fixed
credential, or data-population management command. The developer-only preview
capture command creates disposable synthetic records in a guarded temporary
database, deletes that database after capture, and commits only screenshots.
Normal new accounts receive only the approved default categories; all financial
records are created by their owner.

Dependency maintenance and local database operations are documented in
[operations.md](operations.md). The database owner is responsible for choosing
backup storage, permissions, encryption and retention, and for rehearsing a
restore before relying on a backup.

The root `db.sqlite3` and `.env` are local runtime files and are ignored by Git.
A clean clone creates its database with `manage.py migrate`; each installation
owner is responsible for protecting and backing up these files.
