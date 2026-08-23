<p align="center">
  <img src="static/brand/tuxedo-mark-256.png" width="144" alt="Tuxedo Finance logo">
</p>

<h1 align="center">Tuxedo Finance</h1>

<p align="center">
  <strong>Personal finance, simplified.</strong><br>
  A local-first Django application for understanding cash flow, recurring expenses,
  card bills, investments, and where your money goes each month.
</p>

<p align="center">
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/ci.yml?branch=main&amp;style=for-the-badge&amp;label=CI&amp;labelColor=101E18&amp;color=176B52" alt="CI status"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="Version 0.1.0">
  <img src="https://img.shields.io/badge/Python-3.12-176B52?style=for-the-badge&amp;labelColor=101E18" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Django-6.0-1A2E26?style=for-the-badge&amp;labelColor=101E18" alt="Django 6.0">
  <img src="https://img.shields.io/badge/UI-EN%20%7C%20PT--BR-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="English and Brazilian Portuguese interface">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-PolyForm%20Noncommercial-7C5C13?style=for-the-badge&amp;labelColor=101E18" alt="PolyForm Noncommercial license"></a>
</p>

Tuxedo Finance replaces an improvised spreadsheet with a normalized, categorized
record of financial activity. It is designed for personal use and simple local
operation—not as a SaaS platform—and keeps the database under the installation
owner's control.

## 🏙️ Interface preview

Explore the real Tuxedo Finance interface before installing it. The bilingual
tour walks through the Dashboard, Reports, Transactions, Banking, and
Investments in both light and dark themes.

<p align="left">
  <strong>
    <a href="https://henriquemayer.github.io/TuxedoFinance/"> 🟢 Open the tour</a>
  </strong>
</p>

> The preview uses synthetic data and runs as a static tour. There is no login,
> public backend, or persistence, and nothing is saved.

## 🚀 Quick start

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance
uv sync
printf 'SECRET_KEY=%s\n' "$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')" > .env
uv run python manage.py migrate
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/>, create an account, then add a bank and one of
its accounts before recording the first transaction.

The generated `.env` and `db.sqlite3` files are ignored by Git. Keep both
private and include the database in a protected backup routine. To start the
application again later, run only:

```bash
uv run python manage.py runserver
```

## 🎥 Tutorials

Updated walkthroughs will be available in both supported languages:

| Language | Tutorial |
|---|---|
| 🇧🇷 Português (Brasil) | _Add the updated PT-BR tutorial link here_ |
| 🇺🇸 English | _Add the English tutorial link here_ |

## ✨ Highlights

| | What it does |
|---|---|
| 📊 **Dashboard & outlook** | Separates current cash, monthly income, expenses, investments, open card bills, and projected month-end balance. |
| 🧾 **Transactions** | Records income and expenses with categories, payment channels, fixed recurrences, installments, search, ordering, and CSV export. |
| 🏦 **Banking** | Organizes banks, currency-specific accounts, PIX, debit and credit cards, invoice cycles, own-account transfers, loyalty programs, and exchange rates. |
| 📈 **Reports** | Uses responsive, server-rendered SVG charts with accessible summaries and progressive HTMX updates—no client-side chart library. |
| 💼 **Investments** | Tracks manual deposits, withdrawals, yields, products, assets, quantities, unit prices, fees, and historical conversion evidence. |
| 🌍 **Localization** | Offers English and Brazilian Portuguese independently from BRL, USD, EUR, GBP, JPY, or CHF reporting currency. |
| 🌗 **Accessible themes** | Uses a readable Inter-based light/dark interface with distinct colors for income, expenses, investments, installments, fixed, and one-off activity. |

> **Financial meaning matters:** Current Balance is realized account cash through
> today. Projected (end of month) is the forward-looking close. Credit-card
> purchases belong to their statement month, while cash moves on the invoice due
> date.

<details>
<summary><strong>🎨 Visual language</strong></summary>

<br>

The interface follows the Tuxedo Finance design system: calm foundations,
high-contrast typography, caramel actions, and semantic financial colors.

| Token | Color | Purpose |
|---|---:|---|
| `cream` | `#FAF8F3` | Light background |
| `forest` | `#1A2E26` | Primary text and dark surfaces |
| `forest-deep` | `#101E18` | Dark background |
| `caramel` | `#B88A59` | Brand and primary actions |
| `income` | `#176B52` | Income and positive account movement |
| `expense` | `#B42318` | Expenses, negatives, and destructive actions |
| `investment` | `#7C5C13` | Investment activity |
| `installment` | `#6B4E8A` | Installment plans |
| `fixed` | `#A65300` | Fixed recurrences |
| `oneoff` | `#52605A` | One-off activity |

The dark theme uses the corresponding lighter semantic companions documented in
the canonical catalog, preserving contrast without changing financial meaning.

The canonical component catalog lives in
[`design-system/tuxedo-final-design-system.html`](design-system/tuxedo-final-design-system.html),
with implementation guidance in [`docs/frontend.md`](docs/frontend.md).

</details>

## 🧭 How the pieces fit together

```text
Accounts ──► Banking ──► Transactions ──► Dashboard & Reports
                 │              │
                 └──────────────┴──────► Investments
```

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · Django 6.0 · native authentication |
| Frontend | Django Template Language · Tailwind CSS · small vanilla-JS/HTMX enhancement layer |
| Charts | Inline server-rendered SVG |
| Database | SQLite in WAL mode |
| Dependency management | `uv` with a committed lockfile |

## ⚙️ Configuration

Configuration is read from the local `.env` file or process environment.
Process variables take priority.

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Django signing key | Required |
| `DEBUG` | Development debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `HTTPS` | Secure cookies, HTTPS redirect, and HSTS | `False` |
| `ALLOW_SIGNUPS` | Allow new public accounts | `True` |
| `CASHFLOW_DATA_DIR` | Directory containing `db.sqlite3` | Project root |
| `TUXEDO_ENV_FILE` | Alternate environment file | Project-root `.env` |
| `LOG_LEVEL` | Application log level | `INFO` |

Set `ALLOW_SIGNUPS=False` after creating your account if the installation
should accept only existing users. Set `HTTPS=True` only when the application
is actually served over TLS.

## ✅ Development checks

```bash
uv sync --locked
uv run python manage.py check
uv run python manage.py test
npm ci
npm run build:css
```

For browser smoke tests, start the app on port 8765 in one terminal and run the
suite from another.

Terminal 1:

```bash
uv run python manage.py runserver 127.0.0.1:8765
```

Terminal 2:

```bash
npx playwright install chromium
npm run test:e2e
npm run test:preview
```

The browser suite expects the application at `http://127.0.0.1:8765` by default;
set `E2E_BASE_URL` to use another local address. The CI workflow also verifies
the compiled CSS and vendored HTMX against their pinned sources, checks migrations
and translations, enforces the documented coverage floor, runs Ruff, and audits
the locked runtime dependencies. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the complete development workflow.

To regenerate the committed interface-tour images from disposable synthetic
data, run `npm run preview:capture`. The command uses a guarded temporary
database and never writes to the installation owner's `db.sqlite3`.

## 📚 Documentation

- [Documentation index](docs/README.md) — architecture, data model, frontend, and per-app references
- [Changelog](CHANGELOG.md) — notable changes grouped by release
- [Versioning and releases](docs/versioning.md) — SemVer policy, validation and release workflow
- [Product requirements](docs/ProductRequirementsDocument.md) — approved behavior and acceptance criteria
- [Operations guide](docs/operations.md) — dependency updates and SQLite backup/restore procedures
- [Coverage baseline](docs/coverage-baseline.md) — test coverage policy and commands
- [Category collections](docs/categories-collection/) — import-ready English and Brazilian Portuguese examples

## 🔐 Data ownership

Each clone is an independent installation. Financial records remain in its
local SQLite database; they are not included in the repository. The installation
owner is responsible for access permissions, backups, retention, and restore
testing. Before upgrades or risky maintenance, stop writes and follow the
documented backup procedure.

## 🤝 Contributing

Contributions, bug reports, and suggestions are welcome. Please read
[`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a change.

## 📄 License

Copyright (c) 2026 Henrique Mayer.

Licensed under the
[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).
Personal and other noncommercial use is permitted. Commercial use and resale
are not permitted; see [`LICENSE`](LICENSE) for the complete terms.
