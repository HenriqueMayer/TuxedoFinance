# Tuxedo Finance Documentation

Technical and product documentation for the approved banking/multicurrency
breaking release.

## Where to start

| Doc | Covers |
|---|---|
| [ProductRequirementsDocument.md](ProductRequirementsDocument.md) | Approved scope, requirements, acceptance criteria and clean-reset delivery. |
| [architecture.md](architecture.md) | Domain boundaries, posting workflows and sources of truth. |
| [data-model.md](data-model.md) | Models, relationships, accounting rules, FX and reset contract. |
| [frontend.md](frontend.md) | Server-rendered design system and updated banking UI structure. |
| [operations.md](operations.md) | Dependency updates and owner-managed SQLite backup, restore, retention and rehearsal procedures. |
| [Docker packaging](../docker-compose.yml) | Optional single-instance local package; `runserver` remains primary. |
| [coverage-baseline.md](coverage-baseline.md) | Phase 7 coverage report, 70% line floor, branch-reporting policy and local commands. |
| [sqlite-history-response.md](sqlite-history-response.md) | Personal-data containment and coordinated cleanup plan for the formerly tracked SQLite history. |

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

The repository does not include a synthetic dataset, shared account, fixed
credential, or data-population management command. New accounts receive only
the approved default categories; all financial records are created by their
owner.

Dependency maintenance and local database operations are documented in
[operations.md](operations.md). The database owner is responsible for choosing
backup storage, permissions, encryption and retention, and for rehearsing a
restore before relying on a backup.

Optional Docker packaging and its single-instance limitations are documented
in [operations.md](operations.md#optional-docker-packaging); the native `uv`
workflow remains the supported primary path.

The root `db.sqlite3` is local runtime data and is absent from the current Git
index. A clean clone creates its database with `manage.py migrate`; each
installation owner is responsible for protecting and backing up that file.
Historical Git objects still require the coordinated cleanup documented above.
