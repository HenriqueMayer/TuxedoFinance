[English](README.md) | [Português (Brasil)](README.pt-BR.md)

<p align="center">
  <img src="static/brand/tuxedo-mark-256.png" width="144" alt="Tuxedo Finance logo">
</p>

<h1 align="center">Tuxedo Finance</h1>

<p align="center">
  Personal finance, simplified.<br>
  A local-first application for cash flow, recurring expenses, card bills,
  investments, and monthly planning.
</p>

<p align="center">
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/ci.yml?branch=main&amp;style=for-the-badge&amp;label=CI&amp;labelColor=101E18&amp;color=176B52" alt="CI status"></a>
  <img src="https://img.shields.io/badge/version-0.2.0-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="Version 0.2.0">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-PolyForm%20Noncommercial-7C5C13?style=for-the-badge&amp;labelColor=101E18" alt="PolyForm Noncommercial license"></a>
</p>

Tuxedo Finance organizes personal financial activity into categorized records.
It is built with Django for simple local operation, with an English and
Brazilian Portuguese interface. Each installation keeps its financial records
in an owner-controlled SQLite database.

## Interface preview

[Explore the interface preview](https://henriquemayer.github.io/TuxedoFinance/)
to see Dashboard, Reports, Transactions, Banking, and Investments in both
languages, including light and dark Dashboard views.

The preview is a static tour using synthetic data. It has no login, public
backend, or persistence.

## Quick start

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Run these commands for a new installation:

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance
uv sync --locked
printf 'SECRET_KEY=%s\n' "$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')" > .env
uv run python manage.py migrate
uv run python manage.py runserver
```

Open [the local application](http://127.0.0.1:8000/), create an account, then
add a bank and one of its accounts before recording your first transaction.
Node.js is needed only for development tools; the application serves compiled
frontend assets included in the repository.

The generated `.env` and `db.sqlite3` are private runtime files ignored by Git.
Follow the [operations guide](docs/operations.md) for backup and restore. For an
existing installation, preserve its key and database and restart with:

```bash
uv run python manage.py runserver
```

## Features

| Area | Capabilities |
|---|---|
| Dashboard | Current cash, monthly income and expenses, investments, open card bills, and projected month-end balance. |
| Transactions | Income and expenses, categories, payment channels, fixed recurrences, installments, filtering, and CSV export. |
| Banking | Banks, currency-specific accounts, PIX, debit and credit cards, invoices, own-account transfers, loyalty programs, and manual exchange rates. |
| Reports | Responsive server-rendered SVG charts, accessible summaries, and progressive HTMX updates. |
| Investments | Manual deposits, withdrawals, yields, products, assets, quantities, unit prices, fees, and historical conversion evidence. |
| Salary Sandbox | Automatic CLT or manually adjusted take-home estimates and a monthly spending plan without retaining scenario data. |
| Localization | English and Brazilian Portuguese, independent reporting currency (BRL, USD, EUR, GBP, JPY, CHF), and date-format preferences. |
| Interface | Light and dark themes, keyboard navigation, conditional fields, server validation, and no-JavaScript form fallbacks. |

**Current Balance** represents realized account cash through today.
**Projected (end of month)** represents the expected closing balance.
Credit-card purchases belong to their statement month; account cash changes on
the invoice due date. Invoice settlement is not a second expense.

## Tutorials

Walkthroughs are planned in both supported languages:

| Language | Tutorial |
|---|---|
| Português (Brasil) | _link_TODO_ |
| English | _link_TODO_ |

## Technology and configuration

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 6.0, native Django authentication |
| Frontend | Django templates, Tailwind CSS, vanilla JavaScript, HTMX, inline SVG charts |
| Database | SQLite in WAL mode |
| Dependencies | uv and a committed Python lockfile; npm lockfile for development tools |

Configuration comes from `.env` or the process environment; process values
take priority. `SECRET_KEY` is required. `ALLOW_SIGNUPS=False` closes new
registration while preserving login. `TUXEDO_DATA_DIR` selects an alternative
directory for the database.

See the [configuration reference](docs/operations.md#configuration) for all
variables and defaults, and the [architecture guide](docs/architecture.md)
for domain responsibilities and data flow.

## Development

The [contribution guide](CONTRIBUTING.md) documents prerequisites, checks,
translations, frontend builds, and browser tests. After installing development
dependencies and Chromium, run:

```bash
npm run test:e2e
npm run test:preview
```

The application browser command creates a temporary database and starts its own
local server. It removes test data and stops its processes when finished. The
preview suite checks the committed static tour separately.

## Documentation

Technical documentation is maintained in English.

- [Documentation index](docs/README.md) — repository layout and per-app references
- [Product requirements](docs/product-requirements.md) — supported behavior and acceptance criteria
- [Data model](docs/data-model.md) — entities, relationships, and accounting rules
- [Frontend](docs/frontend.md) and [design system](docs/design-system.html) — interface conventions and component catalog
- [Operations](docs/operations.md) — configuration, dependencies, backup, and restore
- [Changelog](CHANGELOG.md) and [release workflow](docs/versioning.md) — changes and versioning
- [Category collections](docs/category-collections/) — import-ready English and Portuguese examples

## Data ownership

Financial records stay in the installation's database and are not included in
the repository. The installation owner manages access, backups, retention,
and restore testing. Before an upgrade, check the release's compatibility
requirements and follow the documented backup procedure.

## Contributing

Contributions, bug reports, and suggestions are welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change. Changes to this
README must also update the [Portuguese version](README.pt-BR.md).

## License

Copyright (c) 2026 Henrique Mayer.

Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE).
See the license for the complete terms governing use and distribution.
