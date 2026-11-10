# Tuxedo Finance

A self-hosted personal finance application for one person who enters data by
hand. No bank connection. An entry takes a few seconds, and Home answers the
questions of the month: how much is left, where the money went, what is due.

[Português](README.pt-BR.md)

## State

Version 2.0 is in development on this branch. It is a new application on the
1.x financial rules: a Django API and a React client.

| Area | State |
|---|---|
| Entries, categories, installments, repeating entries | Built |
| Wallet: accounts, cards, invoices, payments, transfers | Built |
| Home: month result, spending by category, due soon, net worth | Built |
| Investments: balances and units, deposits, withdrawals, value today | Built |
| Plan: limit of the month, category budgets, goals | Built |
| Plan: months ahead, sheet and calculators; loyalty, other currencies, statement import, the public site | Not built yet |

2.0 has a new database. There is no upgrade from 1.x. The last 1.x release is
the tag [`v1.0.0`](https://github.com/HenriqueMayer/TuxedoFinance/tree/v1.0.0).

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/) and Node.js 22.

```bash
cd web && npm ci && npx vite build
cd ../backend && cp .env.example .env    # set SECRET_KEY in .env
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Open http://127.0.0.1:8000.

With Docker: see [Operations](docs/operations.md#docker).

## Documentation

[Product](docs/product.md) · [Architecture](docs/architecture.md) ·
[Data model](docs/data-model.md) · [Development](docs/development.md) ·
[Operations](docs/operations.md)

## License

[PolyForm Noncommercial 1.0.0](LICENSE).
