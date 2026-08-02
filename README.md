# CashFlow

A personal finance tracker built with Django full stack — record categorized transactions, project your balance forward from recurring and installment payments, and read it all back in a clean light/dark dashboard. Server-rendered, with no JavaScript build step.

![CashFlow demo — recording transactions, then the dashboard and reports updating](docs/media/demo.gif)

## Features

- **Dashboard** with current balance, monthly income/expenses/investments, and a projected end-of-month balance
- **Forward projection** — fixed transactions recur and installment plans spread one payment per month, so future months preview without recording anything in advance
- **Reports** with four server-rendered charts over a rolling 12-month window
- **Categories and subcategories** with a per-user default seed on signup
- **Payment methods** with credit-card billing cycles (statement day and due day) and per-transaction bill overrides
- **Light/dark theme** toggle with a Darcula-inspired dark palette
- **Configurable currency** — pick BRL, USD, EUR, GBP, JPY, or CHF; the symbol and number format always match

## Stack

| | |
|---|---|
| Backend | Python 3.12 · Django 6.0 (CBVs, native auth) |
| Frontend | Django Template Language · TailwindCSS |
| Database | SQLite (native, no separate service) |
| Tooling | [`uv`](https://docs.astral.sh/uv/) |
| Deployment | Docker / Docker Compose · gunicorn · WhiteNoise |

## Quick start

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Sign up from the landing page — your account arrives with the default categories seeded. Add a payment method on the Payments page before recording your first transaction.

### Docker

Requires Docker with the Compose plugin.

```bash
cp .env.example .env        # then set a real SECRET_KEY
docker compose up --build
```

The container applies migrations and serves the app at <http://localhost:8000/>. Data persists in the `db-data` named volume across restarts; `docker compose down -v` resets it.

The image builds the production Tailwind bundle and runs `collectstatic` at build time, so nothing is generated on the fly in production.

## Using this repository as a template

This is a **GitHub template repository**. Click **Use this template** to start your own independent instance — each instance owns its own database and data, and is not meant to be deployed straight from here.

Unlike the usual Django convention, `db.sqlite3` is **tracked in version control** here, shipping with the schema already migrated and no data. A fresh clone is runnable immediately, and any demo data you record is versioned alongside your code. If you would rather follow the standard convention, untrack it before an instance holds real data:

```bash
git rm --cached db.sqlite3
echo 'db.sqlite3' >> .gitignore
```

## Choosing your currency

The app ships in Brazilian Real. Switch it with one setting — `CURRENCY` in `.env`, or an environment variable:

```bash
CURRENCY=USD uv run python manage.py runserver
```

| Code | Renders as | | Code | Renders as |
|---|---|---|---|---|
| `BRL` | `R$ 1.000,00` | | `GBP` | `£ 1,000.00` |
| `USD` | `$ 1,000.00` | | `JPY` | `¥ 1,000.00` |
| `EUR` | `€ 1.000,00` | | `CHF` | `CHF 1'000.00` |

One setting deliberately controls **both** the symbol and the number format — `$ 1.000,00` (dollar sign, Brazilian separators) would be wrong everywhere, so the two are defined together per currency in [`core/currencies.py`](core/currencies.py). An unsupported code raises `ImproperlyConfigured` at startup rather than mislabelling every amount. The interface language stays English whatever you pick.

## Project layout

```
core/          # Project configuration (settings, urls, wsgi, asgi)
pages/         # Public landing page
accounts/      # Sign up, login, logout (native auth)
dashboard/     # Aggregations, projections, and report charts
transactions/  # Transaction model + CRUD
categories/    # Category model + CRUD (self-related)
payments/      # PaymentMethod model + CRUD
templates/     # Project-level Django templates
static/        # Project-level static assets
tailwind/      # Tailwind CSS source for the production build
```

## Configuration reference

Every variable in `.env.example` maps directly to `core/settings.py`:

| Variable | Purpose | Default if unset |
|---|---|---|
| `SECRET_KEY` | Django's cryptographic signing key | insecure development fallback — **required in production** |
| `DEBUG` | `True` / `False` | `True` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `SQLITE_PATH` | Absolute path to the SQLite file | `<project root>/db.sqlite3` |
| `CURRENCY` | Currency shown in the UI | `BRL` |
| `HTTPS` | Secure cookies, HTTPS redirect, HSTS | `False` |
| `LOG_LEVEL` | Log verbosity on stdout | `INFO` |

The app **refuses to start** when `DEBUG=False` and `SECRET_KEY` is unset, blank, still the placeholder from `.env.example`, or still the development fallback committed in `core/settings.py` — anyone holding a published key can forge session cookies. A fresh clone runs with no `.env` at all; the guard only applies once you turn `DEBUG` off.

Set `HTTPS=True` only once the instance is actually served over TLS — it sends session and CSRF cookies as `Secure`, redirects HTTP to HTTPS, emits HSTS, and trusts `X-Forwarded-Proto`. Over plain HTTP it would break login outright.

## Before you deploy

- Set a real `SECRET_KEY` and `DEBUG=False`.
- List your real domains in `ALLOWED_HOSTS`.
- Set `HTTPS=True` if served over TLS; confirm with `manage.py check --deploy`.
- Build the Tailwind bundle and run `python manage.py collectstatic --noinput` (the Docker image does both at build time).
- Keep `.env` out of version control, or use your platform's secret store.
- Start from an empty database if you are keeping `db.sqlite3` tracked.

## Documentation

- [`ProductRequirementsDocument.md`](ProductRequirementsDocument.md) — full product specification, requirements, design system, and sprint history
- [`docs/`](docs/README.md) — technical reference for every app, model, view, and template

## License

Copyright (c) 2026 Henrique Mayer

Licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0). Personal, noncommercial use is permitted — including using this repository as a template for your own personal, local instance; selling this software, or using it for any commercial purpose, is not. See [LICENSE](LICENSE) for the full terms.
