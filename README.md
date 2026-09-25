[English](README.md) | [Português (Brasil)](README.pt-BR.md)

<p align="center">
  <img src="static/brand/tuxedo-mark-256.png" width="144" alt="Tuxedo Finance logo">
</p>

<h1 align="center">Tuxedo Finance</h1>

<p align="center">
  <strong>Personal finance, simplified.</strong><br>
  A local-first application for cash flow, recurring expenses, card bills,
  investments, and monthly planning.
</p>

<p align="center">
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/ci.yml?branch=main&amp;style=for-the-badge&amp;label=CI&amp;labelColor=101E18&amp;color=176B52" alt="CI status"></a>
  <img src="https://img.shields.io/badge/version-0.6.0-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="Version 0.6.0">
  <img src="https://img.shields.io/badge/Python-3.12-176B52?style=for-the-badge&amp;labelColor=101E18" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Django-6.0-1A2E26?style=for-the-badge&amp;labelColor=101E18" alt="Django 6.0">
  <img src="https://img.shields.io/badge/UI-EN%20%7C%20PT--BR-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="English and Brazilian Portuguese interface">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-PolyForm%20Noncommercial-7C5C13?style=for-the-badge&amp;labelColor=101E18" alt="PolyForm Noncommercial license"></a>
</p>

Tuxedo Finance organizes personal financial activity into categorized records.
It is built with Django for simple local operation, with an English and
Brazilian Portuguese interface. Each installation keeps its financial records
in an owner-controlled SQLite database.

## Interface preview

<table>
  <tr>
    <td width="96" align="center">
      <a href="https://henriquemayer.github.io/TuxedoFinance/">
        <img src="static/brand/tuxedo-mark-256.png" width="72" alt="Open the Tuxedo Finance interface preview">
      </a>
    </td>
    <td>
      <strong>See Tuxedo Finance before installing it.</strong><br>
      Explore the bilingual tour across Overview, Reports, Activity,
      Banks, Investments, and Planning, with light and dark Overview views.<br><br>
      <a href="https://henriquemayer.github.io/TuxedoFinance/"><strong>Open the interface preview →</strong></a>
    </td>
  </tr>
</table>

> The preview uses synthetic data and runs as a static tour. There is no login,
> public backend, or persistence, and nothing is saved.


## 🚀 Quick start

### Docker

Requires Docker Engine 28+ (or a current Docker Desktop) and Compose v2+.
Download [compose.yaml](https://github.com/HenriqueMayer/TuxedoFinance/releases/download/v0.5.0/compose.yaml)
and [docker.env.example](https://github.com/HenriqueMayer/TuxedoFinance/releases/download/v0.5.0/docker.env.example)
from the [v0.5.0 release](https://github.com/HenriqueMayer/TuxedoFinance/releases/tag/v0.5.0)
into a new installation directory. Open a terminal there and run these commands.
No repository clone, host Python, uv or Node.js is required:

```bash
image=ghcr.io/henriquemayer/tuxedofinance:v0.5.0
docker pull "$image"
(
  umask 077
  set -o noclobber
  docker run --rm --entrypoint python -e TUXEDO_IMAGE="$image" "$image" -c \
    'import os,secrets; print("TUXEDO_IMAGE="+os.environ["TUXEDO_IMAGE"]); print("SECRET_KEY="+secrets.token_urlsafe(64))' > .env.docker
)
docker compose --env-file .env.docker up -d --wait
```

Open [Tuxedo Finance](http://127.0.0.1:8000/). Docker keeps SQLite in a named
volume and uses a persistent signing key. The setup command refuses to replace
an existing `.env.docker`. Keep the directory name and configuration across
updates. Follow the [Docker guide](docs/docker.md) for source builds,
configuration and backup/restore. For an existing Docker installation, follow the
[update procedure](docs/docker.md#update): back up, select the new image version,
pull it and recreate the service while retaining the same key and volume.

### Python and uv

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Run these commands for a new installation:

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance
uv sync --locked
uv run python scripts/init_local.py
uv run python manage.py migrate
uv run python manage.py runserver
```

Open [the local application](http://127.0.0.1:8000/), create an account, then
add a bank and one of its accounts before recording your first transaction.
Node.js is needed only for development tools; the application serves compiled
frontend assets included in the repository.

The setup helper creates `.env` with owner-only permissions and preserves any
existing file and signing key. Native migration and server commands create new database
files with owner-only permissions. `.env` and `db.sqlite3` are ignored by Git.
Follow the [operations guide](docs/operations.md) for backup and restore. For an
existing installation, preserve its key and database and restart with:

```bash
uv run python manage.py runserver
```

## ✨ Features

These features are included in [v0.5.0](CHANGELOG.md#050---2026-09-21).
This release adds an investment Operations tab, direct chart selection and composition inspection, customizable bank markers, and contextual previous-screen recovery.
Existing Docker installations must select the new image version and follow the
[update procedure](docs/docker.md#update) to receive them.

| Area | Capabilities |
|---|---|
| 📊 **Dashboard** | Current cash, monthly income and expenses, investments, open card bills, and projected month-end balance. |
| 🧾 **Transactions** | Income and expenses, categories, payment channels, fixed recurrences, installments, type counts, category/recurrence filters, and raw or spreadsheet CSV export. |
| 🏦 **Banking** | Currency-specific accounts, cards, invoices, transfers and loyalty, with account exclusions and partial reserves for monthly planning. |
| 📈 **Reports** | Responsive server-rendered SVG charts, accessible summaries, and progressive HTMX updates. |
| 💼 **Investments** | Separate investment and monthly-cash purposes, manual deposits/withdrawals/yields, opening positions, unit pricing and historical FX evidence. |
| 🧮 **Planning** | Salary and monthly-budget sandbox, explicitly saved drafts, snapshots of future commitments, and editable contribution/yield simulations. |
| 🌍 **Localization** | English and Brazilian Portuguese, independent reporting currency (BRL, USD, EUR, GBP, JPY, CHF), and date-format preferences. |
| 🌗 **Interface** | Light and dark themes, keyboard navigation, conditional fields, server validation, and no-JavaScript form fallbacks. |

> **Current Balance** represents realized account cash through today.
> **Projected (end of month)** represents the expected closing balance.
> Credit-card purchases belong to their statement month; account cash changes on
> the invoice due date. Invoice settlement is not a second expense.

<details>
<summary><strong>🎨 Visual language</strong></summary>

<br>

The interface follows the Tuxedo Finance design system: calm foundations,
high-contrast typography, caramel actions, and semantic financial colors.

The dark theme uses neutral black and graphite foundations with the lighter
semantic companions documented in the canonical catalog, preserving contrast
without changing financial meaning. The public homepage presents factual
capabilities and access links beside a horizontal cat photograph in a translucent double frame.

The canonical component catalog lives in
[`docs/design-system.html`](docs/design-system.html),
with implementation guidance in [`docs/frontend.md`](docs/frontend.md).

</details>

## 🧭 Technology

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 6.0, native Django authentication |
| Frontend | Django templates, Tailwind CSS, vanilla JavaScript, HTMX, inline SVG charts |
| Database | SQLite in WAL mode |
| Dependencies | uv and a committed Python lockfile; npm lockfile for development tools |

## ⚙️ Configuration

Configuration comes from `.env` or the process environment; process values
take priority. `SECRET_KEY` is required. `ALLOW_SIGNUPS=False` closes new
registration while preserving login. `TUXEDO_DATA_DIR` selects an alternative
directory for the database.

See the [configuration reference](docs/operations.md#configuration) for all
variables and defaults, and the [architecture guide](docs/architecture.md)
for domain responsibilities and data flow.

## ✅ Development

The [contribution guide](CONTRIBUTING.md) documents prerequisites, checks,
translations, frontend builds, and browser tests. After installing development
dependencies and Chromium, run:

```bash
npm run test:e2e
docker build -t tuxedo-finance:local .
npm run test:e2e -- --docker-image tuxedo-finance:local
npm run test:preview
```

The application browser command creates a temporary database and starts its own
local server. It removes test data and stops its processes when finished. The
preview suite checks the committed static tour separately.

## 📚 Documentation

Technical documentation is maintained in English.

- [Documentation index](docs/README.md) — repository layout and per-app references
- [Product requirements](docs/product-requirements.md) — supported behavior and acceptance criteria
- [Data model](docs/data-model.md) — entities, relationships, and accounting rules
- [Frontend](docs/frontend.md) and [design system](docs/design-system.html) — interface conventions and component catalog
- [Operations](docs/operations.md) — configuration, dependencies, backup, and restore
- [Changelog](CHANGELOG.md) and [release workflow](docs/versioning.md) — changes and versioning
- [Security](SECURITY.md) — supported access model and private vulnerability reporting
- [Category collections](docs/category-collections/) — import-ready English and Portuguese examples

## 🔐 Data ownership

Financial records stay in the installation's database and are not included in
the repository. The installation owner manages access, backups, retention,
and restore testing. Before an upgrade, check the release's compatibility
requirements and follow the documented backup procedure.

## 🤝 Contributing

Contributions, bug reports, and suggestions are welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change. Changes to this
README must also update the [Portuguese version](README.pt-BR.md).

## 📄 License

Copyright (c) 2026 Henrique Mayer.

Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE).
See the license for the complete terms governing use and distribution.
