[English](README.md) · [Português (Brasil)](README.pt-BR.md)

<h1><img src="docs/assets/readme-cover.svg" alt="Tuxedo Finance" width="1240"></h1>

Personal finance that you run yourself. You type what happened, in a few
seconds, and Home answers the questions of the month: how much is left, where
the money went and what is due. No bank connection, no account with anyone:
your records stay on your installation.

<p align="center">
  <a href="https://henriquemayer.github.io/TuxedoFinance/"><img src="docs/assets/preview-link.svg" width="200" height="40" alt="Open the live preview of Tuxedo Finance"></a>
</p>

<p>
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/backend.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/backend.yml?branch=main&amp;style=flat&amp;label=backend&amp;labelColor=1A2E26&amp;color=176B52" alt="Backend checks"></a>
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/web.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/web.yml?branch=main&amp;style=flat&amp;label=web&amp;labelColor=1A2E26&amp;color=176B52" alt="Client checks and browser journeys"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-B88A59?style=flat&amp;labelColor=1A2E26" alt="PolyForm Noncommercial license"></a>
</p>

[Quick start](#quick-start) · [What's in the app](#whats-in-the-app) · [Documentation](docs/README.md) · [Changes](CHANGELOG.md)

<a href="https://henriquemayer.github.io/TuxedoFinance/"><img src="docs/images/en/home.png" alt="Home: what is left to spend, where the money went, what is due, net worth and goals" width="1240"></a>

The preview is the application itself, running in your browser with the
records of a fictional owner. The images on this page come from it.

## What's in the app

Four destinations, one question each. Every object opens in a window above
the page, and the page keeps its place.

| Destination | Answers | What you do there |
|---|---|---|
| **Home** | How is this month? | Read what is left to spend, where the money went, what is due, your net worth and your goals. You choose the blocks and their order. |
| **Transactions** | What did I record? | Add an entry in a few seconds, with installments or a monthly repetition. Import a bank statement (OFX or CSV) and review it row by row. |
| **Wallet** | What do I have and what do I owe? | Keep accounts, cards and invoices, transfers, investments, points and miles, and accounts in other currencies. |
| **Plan** | What do I intend? | Set a limit for the month and budgets by category, reserve real balances for goals, look at the months ahead, and close each month. |

| Plan | A window |
|---|---|
| <img src="docs/images/en/plan.png" alt="Plan: the limit of the month, category budgets and goals" width="610"> | <img src="docs/images/en/window.png" alt="The month window, opened from Home" width="610"> |

English and Brazilian Portuguese, light and dark themes, desktop and phone.

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/) and Node.js 22.

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance/web && npm ci && npx vite build
cd ../backend && cp .env.example .env    # set SECRET_KEY in .env
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Open http://127.0.0.1:8000.

With Docker: see [Operations](docs/operations.md#docker).

## Your data

All records are in one SQLite file on the computer that runs the
application. Backup and restore are two commands: see
[Operations](docs/operations.md#data).

## Documentation

| Subject | File |
|---|---|
| What the product is and what each area does | [Product](docs/product.md) |
| Repository layout, the API, the client and the tests | [Architecture](docs/architecture.md) |
| Records and financial rules | [Data model](docs/data-model.md) |
| Setup, commands and checks | [Development](docs/development.md) |
| Settings, data, Docker and a release | [Operations](docs/operations.md) |
| The public page and its demonstration | [Site](site/README.md) |

## State

Version 2.0 is a new application on the 1.x financial rules: a Django API
and a React client. It is not released yet. It has a new database, and there
is no upgrade from 1.x. The last 1.x release is the tag
[`v1.0.0`](https://github.com/HenriqueMayer/TuxedoFinance/tree/v1.0.0).

## License

[PolyForm Noncommercial 1.0.0](LICENSE): free for personal, noncommercial use.
