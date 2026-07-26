# CashFlow — Django Personal Finance Tracker

CashFlow is a web-based personal finance tracker built with Django full stack (Django Template Language + TailwindCSS + SQLite). It records categorized transactions, classifies them by type and payment method, and projects your balance forward from fixed transactions and installment plans — all server-rendered, with no JavaScript.

See [`ProductRequirementsDocument.md`](ProductRequirementsDocument.md) for the full product specification, and [`docs/`](docs/README.md) for technical documentation of every app, model, view, and template.

![CashFlow — recording a fixed income, then the dashboard and reports updating](docs/media/demo.gif)

[▶ Watch the full demo](docs/media/demo-2x.mp4) — one minute, 2× speed, no audio.

## Stack

- Python 3.12
- Django 6.0
- TailwindCSS (Play CDN in development; standalone CLI build + WhiteNoise in production)
- SQLite (native)
- Dependency management via [`uv`](https://docs.astral.sh/uv/)
- `gunicorn` + Docker / Docker Compose for deployment

## Prerequisites

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) on your `PATH`

## Setup

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Apply database migrations:

   ```bash
   uv run python manage.py migrate
   ```

3. (Optional) Create a superuser for the Django admin:

   ```bash
   uv run python manage.py createsuperuser
   ```

4. Run the development server:

   ```bash
   uv run python manage.py runserver
   ```

5. Open `http://127.0.0.1:8000/`.

Sign up from the landing page and your account arrives with the default categories and payment methods already seeded, so you can record a transaction immediately.

## Using this repository as a template

This project is meant to be **forked** and run as your own independent local instance — not deployed straight from this repository. Each fork owns its own database and data.

### 1. Fork and clone

1. Click **Use this template** (or **Fork**) on [github.com/HenriqueMayer/django-finance-template](https://github.com/HenriqueMayer/django-finance-template).
2. Clone your fork:

   ```bash
   git clone git@github.com:<your-username>/django-finance-template.git
   cd django-finance-template
   ```

3. Follow [Setup](#setup) above.

### 2. The local database (`db.sqlite3`)

`db.sqlite3` is a single file — there is no separate database server to install or configure.

Unlike the usual Django convention, this file is **tracked in version control** here, and ships with the schema already migrated and no data in it. A fresh clone is therefore runnable straight away, and any test or demo data you record is versioned alongside your code instead of being lost on the next clone.

If you would rather follow the standard convention, where every environment generates its own database and data is never committed, stop tracking it:

```bash
git rm --cached db.sqlite3
echo 'db.sqlite3' >> .gitignore
```

Do this before deploying a fork that will hold real data. The Docker setup points production at a separate volume-mounted file regardless, but a stale development database should not ship in the image either.

### 3. Syncing your fork with future template updates

To pull in changes made to the original template after you forked it:

```bash
git remote add upstream git@github.com:HenriqueMayer/django-finance-template.git
git fetch upstream
git merge upstream/main   # or: git rebase upstream/main
```

Because `db.sqlite3` is a tracked binary file, a merge or rebase from `upstream` conflicts on it whenever both sides have changed. Keep your own copy:

```bash
git checkout --ours db.sqlite3
git add db.sqlite3
```

Untracking it as described above avoids the conflict entirely.

## Project layout

```
core/          # Project configuration (settings, urls, wsgi, asgi)
pages/         # Public presentation site (landing)
accounts/      # Sign up, login, logout (native auth)
dashboard/     # Aggregations, projections, and report charts
transactions/  # Transaction model + CRUD
categories/    # Category model + CRUD (self-related)
payments/      # PaymentMethod model + CRUD
templates/     # Project-level Django templates
static/        # Project-level static assets
tailwind/      # Tailwind CSS source for the production build
```

## Choosing your currency

The app ships in Brazilian Real. Switch it with a single setting — `CURRENCY` in `.env`, or an environment variable for a local run:

```bash
CURRENCY=USD uv run python manage.py runserver
```

| Code | Renders as | | Code | Renders as |
|---|---|---|---|---|
| `BRL` | `R$ 1.000,00` | | `GBP` | `£ 1,000.00` |
| `USD` | `$ 1,000.00` | | `JPY` | `¥ 1,000.00` |
| `EUR` | `€ 1.000,00` | | `CHF` | `CHF 1'000.00` |

One setting deliberately controls **both** the symbol and the number format: `$ 1.000,00` (dollar sign, Brazilian separators) would be wrong in every locale, so the two are defined together per currency in [`core/currencies.py`](core/currencies.py). Adding a currency is one line in that file.

An unsupported code raises `ImproperlyConfigured` at startup and lists the valid ones, rather than silently labelling every amount with the wrong symbol.

Two things stay unchanged whatever you pick: the interface language (English — the currency does not switch `LANGUAGE_CODE`), and amount **inputs**, which stay dot-decimal because `<input type="number">` accepts nothing else.

## Docker

CashFlow ships as a single lean container: the Django app served by `gunicorn`, plus a named volume that persists `db.sqlite3` across restarts and container recreation. There is no separate database service and no reverse proxy — static files are served in-process by [WhiteNoise](https://whitenoise.readthedocs.io/).

Requires Docker and the Docker Compose plugin (`docker compose version`).

### First run

1. Copy the environment template and fill in real values:

   ```bash
   cp .env.example .env
   ```

   At minimum, set a real `SECRET_KEY` (never commit `.env` — it is already gitignored):

   ```bash
   uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

2. Build and start:

   ```bash
   docker compose up --build
   ```

   The container runs `manage.py migrate` before starting `gunicorn`, so the schema is created inside the `db-data` volume on first start.

3. Open `http://localhost:8000/`.

4. (Optional) Create a superuser inside the running container:

   ```bash
   docker compose exec app python manage.py createsuperuser
   ```

### What the image does at build time

- Installs dependencies with `uv sync --locked`, matching the committed `uv.lock`.
- Downloads the standalone Tailwind CSS CLI (a plain binary — no Node.js or npm) and compiles `tailwind/input.css` into `static/css/output.css`.
- Runs `collectstatic`, so WhiteNoise serves pre-built, hashed, compressed files at runtime. Nothing is generated on the fly in production.

### Persisting data

The `db-data` named volume is mounted at `/app/data`, and `SQLITE_PATH` points Django's `DATABASES` at `/app/data/db.sqlite3`:

- `docker compose down && docker compose up` keeps your data.
- `docker compose down -v` **deletes** the volume and all data. Use only when you intend to reset.

### Configuration reference

Every setting in `.env.example` maps directly to `core/settings.py`:

| Variable | Purpose | Default if unset |
|---|---|---|
| `SECRET_KEY` | Django's cryptographic signing key | insecure development fallback — **required in production** |
| `DEBUG` | `True` / `False` | `True` |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hostnames | `localhost,127.0.0.1` |
| `SQLITE_PATH` | Absolute path to the SQLite file | `<project root>/db.sqlite3` |
| `CURRENCY` | Currency shown in the UI — sets symbol **and** number format | `BRL` |
| `HTTPS` | Enables secure cookies, HTTPS redirect, and HSTS | `False` |

### `SECRET_KEY` is enforced, not just recommended

The development fallback in `core/settings.py` is committed to this public repository, so anyone holding it can forge session cookies and password-reset tokens against an instance still running on it. The app therefore **refuses to start** when `DEBUG=False` and the key is unset, blank, or still that fallback:

```
django.core.exceptions.ImproperlyConfigured: SECRET_KEY is still the insecure
development fallback, which is published in this repository, while DEBUG is False.
```

A fresh clone still runs with no `.env` at all — the guard only applies once you turn `DEBUG` off.

### `HTTPS` — turn on once you actually have TLS

Set `HTTPS=True` and Django sends session and CSRF cookies as `Secure`, redirects HTTP to HTTPS, emits HSTS, and trusts your proxy's `X-Forwarded-Proto` header. `manage.py check --deploy` then returns clean.

Leave it `False` for the default `docker compose up`, which publishes plain HTTP on `:8000`. This is deliberately separate from `DEBUG`, because "not in development" and "served over TLS" are different questions: enabled over plain HTTP, a browser would never send the session cookie back (login appears to succeed, then bounces to the form) and the redirect would loop to an HTTPS port serving nothing.

## Production static files

- **Development** (`DEBUG=True`): Tailwind loads from the Play CDN. No build step.
- **Production** (`DEBUG=False`): `templates/base.html` links the compiled `static/css/output.css`, built from `tailwind/input.css` with the [standalone Tailwind CLI](https://tailwindcss.com/docs/installation/tailwind-cli) and served by WhiteNoise's `CompressedManifestStaticFilesStorage` (gzip plus hashed filenames for long-lived caching).

To rebuild the CSS locally without Docker — for instance to sanity-check a `DEBUG=False` run before deploying:

```bash
curl -sLo tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
chmod +x tailwindcss
./tailwindcss -i tailwind/input.css -o static/css/output.css --minify
uv run python manage.py collectstatic --noinput
```

## Before you deploy

A short pass to run through before putting an instance in front of real data:

- **Set a real `SECRET_KEY`** — long, random, and unique to this instance. This one is enforced: the app will not start without it once `DEBUG=False`.
- **Turn `DEBUG` off.** `DEBUG=False`.
- **List your real domains** in `ALLOWED_HOSTS`.
- **Set `HTTPS=True` if the instance is served over TLS.** Confirm with `manage.py check --deploy`, which should report no issues.
- **Apply migrations** — `python manage.py migrate`. The Docker image does this on container start; run it yourself otherwise.
- **Build the CSS and collect static files** — `python manage.py collectstatic --noinput`, after building `static/css/output.css`. The Docker image does both at build time. Make sure the bundle reflects your current templates.
- **Run the tests** — `uv run python manage.py test`.
- **Keep `.env` out of version control**, or use your platform's secret store.
- **Start from an empty database.** If you are keeping `db.sqlite3` tracked, make sure the committed file holds no real data; otherwise untrack it as described above.

## License

Copyright &copy; 2026 [Henrique Mayer](https://github.com/HenriqueMayer). All rights reserved.

See [LICENSE](LICENSE) for the full terms. Forking this repository for your own personal, local use is expected and welcome; any other use, redistribution, or reuse of the code beyond that requires the copyright holder's permission.
