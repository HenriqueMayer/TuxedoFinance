[English](README.md) · [Português (Brasil)](README.pt-BR.md)

<h1><img src="docs/assets/readme-cover.svg" alt="Tuxedo Finance" width="1240"></h1>

<a id="-data-ownership"></a>

**Your finances, made clear.**

A local application for income, expenses, accounts, cards, investments and monthly
planning. Your records stay in your own SQLite database. English and Brazilian
Portuguese, light and dark themes.

<a id="interface-preview"></a>

<p align="center">
  <a href="https://henriquemayer.github.io/TuxedoFinance/"><img src="docs/assets/preview-link.svg" width="320" height="64" alt="Open the Tuxedo Finance interface preview"></a>
</p>

<p>
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/ci.yml?branch=main&amp;style=flat&amp;label=CI&amp;labelColor=1A2E26&amp;color=176B52" alt="CI status"></a>
  <img src="https://img.shields.io/badge/version-0.10.0-B88A59?style=flat&amp;labelColor=1A2E26" alt="Version 0.10.0">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-B88A59?style=flat&amp;labelColor=1A2E26" alt="PolyForm Noncommercial license"></a>
</p>

[Quick start](#quick-start) · [Documentation](docs/README.md) · [Changes](CHANGELOG.md)

<a href="https://henriquemayer.github.io/TuxedoFinance/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="preview/images/en/dashboard-dark.png">
    <img src="preview/images/en/dashboard-light.png" width="1440" height="1000" alt="Tuxedo Finance Home with sidebar navigation, monthly balances and financial charts using synthetic data">
  </picture>
</a>

<a id="unreleased-source-branch"></a>

The [local tour](preview/index.html) and images in this checkout use synthetic
data. The tour is static: no login, public backend or saved financial records.
This branch contains unreleased work; the published tour and **v0.10.0** image
may differ. See the [branch walkthrough](docs/branch-testing.md) and [changelog](CHANGELOG.md#unreleased).

<a id="-features"></a>

## Five workspaces

| Workspace | What you can do |
|---|---|
| **Home** | Review balances, upcoming commitments and financial reports. |
| **Transactions** | Record income and expenses, split categories, manage recurrences and installments, export CSV. |
| **Accounts** | Organize bank accounts, PIX, cards, invoices, transfers and loyalty. |
| **Investments** | Track holdings, movements, cash pots and dated prices. |
| **Plan** | Set category limits, reserve existing balances for goals and compare simulations. |

<a id="-quick-start"></a>

## Quick start

### Docker

Requires Docker Engine 28+ (or a current Docker Desktop), Compose v2+ and a
POSIX shell (WSL on Windows). No clone, host Python or Node.js is needed.
Download [compose.yaml](https://github.com/HenriqueMayer/TuxedoFinance/releases/download/v0.10.0/compose.yaml)
and [docker.env.example](https://github.com/HenriqueMayer/TuxedoFinance/releases/download/v0.10.0/docker.env.example)
from the **v0.10.0** release into a new installation directory. Open a terminal
there and run:

```bash
image=ghcr.io/henriquemayer/tuxedofinance:v0.10.0
docker pull "$image"
(
  umask 077
  set -o noclobber
  docker run --rm --entrypoint python -e TUXEDO_IMAGE="$image" "$image" -c \
    'import os,secrets; print("TUXEDO_IMAGE="+os.environ["TUXEDO_IMAGE"]); print("SECRET_KEY="+secrets.token_urlsafe(64))' > .env.docker
)
docker compose --env-file .env.docker up -d --wait
```

Open [127.0.0.1:8000](http://127.0.0.1:8000/). The setup preserves an existing
`.env.docker`; keep its signing key, installation directory and data volume
across updates. See the [Docker guide](docs/docker.md) for configuration,
updates and backups. This installs the published release; checkout changes
require a [local image build](docs/docker.md#build-from-a-checkout).

<a id="python-and-uv"></a>

**Python 3.12 + [uv](https://docs.astral.sh/uv/getting-started/installation/):**
for a new source installation:

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance
uv sync --locked
uv run python scripts/init_local.py
uv run python manage.py migrate
uv run python manage.py runserver
```

Open [127.0.0.1:8000](http://127.0.0.1:8000/), create an account, then add a bank
and bank account. Node.js is only needed for development tools.
Before updating an existing installation, follow the
[backup and migration procedure](docs/operations.md#updating-a-native-installation).
Preserve its database and signing key.

<a id="optional-demo-data"></a><a id="-configuration"></a><a id="-development"></a><a id="-documentation"></a><a id="-contributing"></a>

## Guides

[Setup and operations](docs/operations.md) · [Demo data](docs/demo-data.md) ·
[Design system](docs/design-system.html) · [Contributing](CONTRIBUTING.md) ·
[Roadmap](docs/roadmap.md) · [Security](SECURITY.md)

<a id="-technology"></a>

Built with **Django, SQLite, HTMX and locally served assets**.
The [documentation index](docs/README.md) owns the technical and financial details.
Statement imports and the net-worth interface remain paused.

---

<a id="-license"></a>

Copyright © 2026 Henrique Mayer. [PolyForm Noncommercial 1.0.0](LICENSE).
