# CashFlow

[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blueviolet)](LICENSE)

A personal finance tracker built with Django full stack — record categorized transactions, project your balance forward from recurring and installment payments, and read it all back in a clean light/dark dashboard. Server-rendered, with no JavaScript build step.

## Why CashFlow exists

CashFlow was created by Henrique Mayer after struggling to manage personal
finances in generic spreadsheets. Those tools required too much adaptation and
still made it difficult to understand day-to-day cash flow, recurring expenses,
bank accounts, cards, and investments in one place.

The project turns that experience into a practical tool for other people facing
the same problem. Its focus is personal use, simple self-hosting, clear financial
information, and community collaboration — not becoming a SaaS platform or
optimizing prematurely for large-scale operation.

The source is publicly available so people can study it, adapt it, contribute to
it, and run their own noncommercial instance. Commercial use and resale are not
permitted by the project's license; see [License](#license).

## Features

- **Dashboard** with current balance, monthly income/expenses/investments, and a projected end-of-month balance
- **Forward projection** — fixed transactions recur and installment plans spread one payment per month, so future months preview without recording anything in advance
- **Filtered transaction history** — general search, separate billed-month and exact transaction-date filters, type filtering, and date/update/amount ordering
- **Reports** with server-rendered, zero-JS SVG charts for balance evolution, monthly cash flow, installments, cards and accounts, and expense categories
- **Categories and subcategories** with a per-user default seed on signup
- **Payment methods** with credit-card billing cycles (statement day and due day) and per-transaction bill overrides
- **Investments log** — a parallel universe to `Transaction` for tracking manual deposits, withdrawals, and yields, with settings to manage banks, brokers, investment products, free-form assets, and exchange rates. Automatic monthly and annual yield calculations are marked `Coming soon` (see [docs/apps/investments.md](docs/apps/investments.md))
- **Light/dark theme** toggle with a Darcula-inspired dark palette
- **Configurable currency** — pick BRL, USD, EUR, GBP, JPY, or CHF; the symbol and number format always match
- **English and Brazilian Portuguese UI** — selected from the public or authenticated navbar without changing URLs
- **Optional public signup control** — keep registration open for a community instance or close it while existing accounts continue to log in

## Stack

| | |
|---|---|
| Backend | Python 3.12 · Django 6.0 (CBVs, native auth) |
| Frontend | Django Template Language · TailwindCSS |
| Database | SQLite (native, no separate service) |
| Tooling | [`uv`](https://docs.astral.sh/uv/) |
| Runtime | Django development server (`runserver`), optionally packaged with Docker |

## Quick start

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
export SECRET_KEY="$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

The migration command creates a new local `db.sqlite3` and applies the complete
schema on a clean clone. Keep `SECRET_KEY` private and stable for the lifetime
of an installation; replacing it invalidates sessions. Open
<http://127.0.0.1:8000/> and, when public signup is enabled, sign up from the landing page; your account
arrives with the default categories seeded. Add a bank and a currency-specific
account before recording your first transaction.

### Optional Docker packaging

Docker is an optional local packaging path; the native `uv` workflow above is
the primary development and support path. The image runs one CashFlow process
as the unprivileged `cashflow` user, executes migrations on startup, and stores
SQLite runtime data in the named `cashflow_data` volume. It does not contain a
database, demo account, or personal data.

```bash
export SECRET_KEY="$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
docker compose up --build
```

Open <http://127.0.0.1:8000/> after the container reports healthy. The compose
healthcheck is only a local operational signal; it is not production
orchestration or a readiness contract for replicas. The supplied image targets
Linux `amd64` and `arm64` hosts through the upstream Python base image; other
architectures must be validated locally. Keep the named volume and back it up
with the same SQLite procedure used by native installs; see
[`docs/operations.md`](docs/operations.md#optional-docker-packaging).

Do not expose this single-instance SQLite container directly to the public
internet. Set `DEBUG=False`, configure real `ALLOWED_HOSTS`, and terminate TLS
outside the container before any non-local use. Docker support does not add
horizontal scaling, a separate database, or automated backup.

### Validation and CI

Run the same checks used by the repository's GitHub Actions workflow from a
local checkout:

```bash
uv sync --locked
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py compilemessages
uv run coverage run --branch manage.py test
uv run coverage report --show-missing
uvx --from 'ruff>=0.9,<1' ruff check .
```

CI also audits the locked runtime requirements with `pip-audit` and publishes
branch-coverage XML and HTML artifacts. CI enforces the documented 70% line
coverage floor while financial-service branches continue to be expanded.

## Choosing the interface language

The interface supports English (`en`) and Brazilian Portuguese (`pt-br`). Use
the language selector in the public navbar or, after login, in either the
desktop navbar or mobile menu. Django posts the choice to
`/i18n/set_language/` and stores it in its native language cookie; application
URLs remain stable and never gain a language prefix. On a first visit without
that cookie, `LocaleMiddleware` selects a supported language from the browser's
`Accept-Language` header and otherwise falls back to English.

Language selection also applies to HTMX responses because they pass through the
same middleware. It translates interface copy, validation and system messages,
not user-entered names or financial data: category names and other user data
remain exactly as entered.

## Local database ownership

This is a **GitHub template repository**. Click **Use this template** to start
your own independent instance. The current tree and future commits do not
include a database: `db.sqlite3` is created by `manage.py migrate` and ignored
by Git. Older Git objects still contain database versions until the coordinated
history cleanup described below is completed.

Each installation owner controls the contents of that local database and is
responsible for its access permissions, protection and backups. Never add the
database to version control or publish it with application source. Before an
upgrade or other risky operation, stop application writes and make a protected
copy of the database. See the complete backup, restore, retention and rehearsal
procedure in [`docs/operations.md`](docs/operations.md).

The repository-owner operation `git rm --cached db.sqlite3` changes only the
index and preserves that working-tree file; it does not alter its schema or
financial records. The resulting commit is different for existing clones: Git
may remove their formerly tracked working-tree copy when they pull it. Rollback
may restore the previous Git entry, but publishing database contents in source
history is not recommended.

If you cloned the repository before this change, back up your local database
outside the checkout before pulling the commit that removes the tracked file.
Git may remove a previously tracked working-tree copy while applying that
change. After updating, restore the protected copy to the project root if
needed; it will remain ignored.

An audit found personal data and authentication material in older Git versions
of `db.sqlite3`. Removing the current index entry does not erase those blobs.
History cleanup and credential containment are tracked in
[`docs/sqlite-history-response.md`](docs/sqlite-history-response.md).

## Choosing your currency

Choose a reporting currency from the authenticated **Settings** screen. The
selection belongs to the current user, so two users in the same database may
use different reporting currencies. It changes consolidated presentation only;
account, transaction, investment, and other financial records retain their
native currencies and amounts. Missing exchange rates remain explicit.

| Code | Renders as | | Code | Renders as |
|---|---|---|---|---|
| `BRL` | `R$ 1.000,00` | | `GBP` | `£ 1,000.00` |
| `USD` | `$ 1,000.00` | | `JPY` | `¥ 1,000.00` |
| `EUR` | `€ 1.000,00` | | `CHF` | `CHF 1'000.00` |

The supported registry pairs each code with its symbol and number format in
[`core/currencies.py`](core/currencies.py). New users and existing users
without a preference start with BRL. Interface language and currency are
independent; matching `core/formats/en/` and `core/formats/pt_BR/` overrides
preserve the selected currency's separators in either language.

## Project layout

```
core/          # Project configuration (settings, urls, wsgi, asgi)
pages/         # Public landing page
accounts/      # Sign up, login, logout (native auth)
dashboard/     # Aggregations, projections, and report charts
transactions/  # Transaction model + CRUD
categories/    # Category model + CRUD (self-related)
banking/       # Banks, accounts, cards, balances, invoices, points, and FX
investments/   # Investment log + manual ExchangeRate (multi-currency)
templates/     # Project-level Django templates
static/        # Project-level static assets
```

## Tests and continuous integration

The supported development path is Python 3.12 with `uv`, Django's native test
runner and SQLite. CI reproduces that setup from `uv.lock` and runs system
checks, missing-migration checks, translation validation, the full test suite,
Ruff, and a locked-runtime dependency audit. It reports branch coverage and
requires at least 70% line coverage; the XML and HTML reports are retained as
build artifacts. No alternate database or SaaS-scale matrix is maintained.

Run the coverage gate locally with `uv run coverage run --branch manage.py test`
followed by `uv run coverage report --show-missing --fail-under=70`. The full
policy and affected-tests guidance live in
[`docs/coverage-baseline.md`](docs/coverage-baseline.md) and
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Configuration reference

Set configuration through the environment of the process that runs Django:

| Variable | Purpose | Default if unset |
|---|---|---|
| `SECRET_KEY` | Django's cryptographic signing key | **required** |
| `DEBUG` | `True` / `False` | `True` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `HTTPS` | Secure cookies, HTTPS redirect, HSTS | `False` |
| `LOG_LEVEL` | Log verbosity on stdout | `INFO` |
| `ALLOW_SIGNUPS` | Allow creation of new accounts from the public signup route | `True` |

The app refuses to start without `SECRET_KEY`. Generate one with Django's
`get_random_secret_key()` command shown in Quick start; never commit or share
it. Replacing the key invalidates existing sessions and password-reset tokens.

Set `ALLOW_SIGNUPS=False` to close public registration after creating an account
or when running a private instance. The signup route returns a localized
explanation and never creates a user while disabled; login for existing users is
unchanged. Leave it unset (or set it to `True`) for an open community instance.

Set `HTTPS=True` only once the instance is actually served over TLS — it sends session and CSRF cookies as `Secure`, redirects HTTP to HTTPS, emits HSTS, and trusts `X-Forwarded-Proto`. Over plain HTTP it would break login outright.

## Optional Docker packaging

The native `uv` workflow remains primary. Docker Compose is an optional
single-instance package using locked dependencies, automatic migrations, the
non-root `cashflow` user, and a persistent `cashflow_data` SQLite volume:

```bash
export SECRET_KEY="$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
docker compose up --build
```

It includes only a local healthcheck and must not be exposed directly to the
public internet. Back up the named volume using [`docs/operations.md`](docs/operations.md).
The image contains no database, credentials, or demo data.

## Future deployment security

Current support is local `runserver`. If you package the project for deployment
in the future, apply Django's deployment checklist and these safeguards:

- Set a real `SECRET_KEY` and `DEBUG=False`.
- List your real domains in `ALLOWED_HOSTS`.
- Set `HTTPS=True` if served over TLS; confirm with `manage.py check --deploy`.
- Use a private environment or secret store for `SECRET_KEY`.
- Protect and back up the local SQLite database; it is not stored in Git.

## Documentation

- [`docs/ProductRequirementsDocument.md`](docs/ProductRequirementsDocument.md) — full product specification and requirements
- [`docs/`](docs/README.md) — technical reference for every app, model, view, and template
- [`docs/operations.md`](docs/operations.md) — dependency updates and local SQLite backup/restore operations
- [`ROADMAP.md`](ROADMAP.md) — prioritized implementation and UX improvement plan

## License

Copyright (c) 2026 Henrique Mayer

Licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0). Personal, noncommercial use is permitted — including using this repository as a template for your own personal, local instance; selling this software, or using it for any commercial purpose, is not. See [LICENSE](LICENSE) for the full terms.

Copies and modified distributions must preserve the license terms and the
required copyright notice. Public source code cannot be made technically
impossible to copy; the copyright and license define which uses are permitted.

## Contributing

Contributions are welcome under the same PolyForm Noncommercial License. Read
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a change.
