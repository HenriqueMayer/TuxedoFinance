# Tuxedo Finance Documentation

Technical and product documentation for the current code, including unreleased
changes listed in the changelog. Technical guides are maintained in English;
the root README is available in [English](../README.md) and
[Português (Brasil)](../README.pt-BR.md).

## Where to start

| Doc | Covers |
|---|---|
| [Contributing](../CONTRIBUTING.md) | Canonical developer setup, checks, translations, browser isolation, and documentation conventions. |
| [Interface preview](https://henriquemayer.github.io/TuxedoFinance/) | Bilingual static tour of the application using synthetic financial data. |
| [Preview maintenance](../.github/preview/README.md) | Capture isolation, synthetic data generation, static tests and publication layout. |
| [product-requirements.md](product-requirements.md) | Approved scope, requirements, acceptance criteria and clean-reset delivery. |
| [architecture.md](architecture.md) | Domain boundaries, posting workflows and sources of truth. |
| [data-model.md](data-model.md) | Models, relationships, accounting rules, FX and reset contract. |
| [frontend.md](frontend.md) | Server-rendered design system, viewport/focus preservation, progressive disclosure and banking UI structure. |
| [design-system.html](design-system.html) | Canonical visual tokens and component catalog. |
| [operations.md](operations.md) | Dependency updates and owner-managed SQLite backup, restore, retention and rehearsal procedures. |
| [versioning.md](versioning.md) | Semantic versioning policy, automated consistency checks and release workflow. |
| [coverage-baseline.md](coverage-baseline.md) | Dated measurements, 70% combined line/branch floor, and report artifacts. |

## Per-app reference

- [apps/core.md](apps/core.md) — project settings, currency registry and formatting.
- [apps/pages.md](apps/pages.md) — public landing page.
- [apps/accounts.md](apps/accounts.md) — native Django authentication and presentation preferences.
- [apps/categories.md](apps/categories.md) — income/expense categories.
- [apps/banking.md](apps/banking.md) — banks, accounts, movements, PIX, cards,
  invoices, loyalty and historical FX.
- [apps/transactions.md](apps/transactions.md) — categorized economic events, progressive list
  filters and settlement behavior.
- [apps/dashboard.md](apps/dashboard.md) — cash, cash-flow, liabilities,
  investments and net-worth read models.
- [apps/investments.md](apps/investments.md) — separate position ledger using
  banks/accounts for provider and cash endpoints.
- [apps/sandbox.md](apps/sandbox.md) — authenticated, non-persistent salary and
  monthly-budget planning.

## Repository layout

The repository follows Django conventions, with frontend tooling shared by the
application and static preview:

| Path | Responsibility |
|---|---|
| Django app directories | Domain code, migrations and focused unit tests kept beside each app. |
| `assets/` | Tailwind source input; files here are compiled rather than served directly. |
| `static/` | Versioned assets served by Django, including compiled CSS, JavaScript and brand files. |
| `tests/` | Application and preview browser tests plus standard-library repository-tool tests; Django tests stay in their apps. |
| `preview/` | Self-contained bilingual static tour published by GitHub Pages. |
| `.github/preview/` | Isolated tooling that generates and tests the public preview. |
| `scripts/` | Small repository-wide maintenance and validation commands. |
| `docs/` | Product, architecture, data, operations and frontend documentation. |

Root configuration files remain at the repository root because Django, `uv`,
npm, Tailwind, Playwright and CI discover or share them there. The application
and preview use the same locked frontend toolchain.

## Documentation status

These documents describe the current `0.2.x` code and relevant unreleased
changes. Its schema has no automatic upgrade path from pre-release legacy databases; those installations
must start with a newly migrated SQLite database and recreate or manually import
their records.

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
