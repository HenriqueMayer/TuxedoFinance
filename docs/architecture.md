# Architecture

How CashFlow is put together: the stack, the settings that wire it up, URL routing, and the request/response path. For *what* each app does, see [`apps/`](apps/); for *why* the business rules are what they are, see [data-model.md](data-model.md).

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 6.0.7 (full stack — no separate API/frontend) |
| Frontend | Django Template Language + TailwindCSS |
| Database | SQLite (native, single file) |
| Authentication | `django.contrib.auth` (native — no custom user model) |
| Dependency management | [`uv`](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`) |
| Views | Class-Based Views (CBVs) exclusively |
| Production server | `gunicorn` behind [WhiteNoise](https://whitenoise.readthedocs.io/) (no nginx) |

Source: `pyproject.toml`.

## Project layout

```
core/          # Project configuration: settings, root urls, wsgi/asgi, context processors
core/currencies.py  # Supported currencies: symbol + number format, one entry each
core/formats/  # Locale number-format override driven by CURRENCY — see FORMAT_MODULE_PATH
pages/         # Public landing page
accounts/      # Sign up, login, logout (native auth)
dashboard/     # Aggregation + projection services, consolidated view, SVG report charts
transactions/  # Transaction model + CRUD (the core domain entity)
categories/    # Category model + CRUD (self-referencing) + default-data signal
payments/      # PaymentMethod model + CRUD + default-data signal
templates/     # Project-level Django templates (base.html, partials/, per-app screens)
static/        # Project-level static assets (static/css/output.css is a generated
               # Tailwind build artifact — see frontend.md)
tailwind/      # Tailwind CSS source (input.css) for the production build
docs/          # This documentation
```

Each domain app owns its own `models.py`, `views.py`, `urls.py`, `admin.py`, and (where needed) `forms.py`/`signals.py` — nothing is shared across apps except through explicit imports (e.g. `transactions/models.py` imports `Category` and `PaymentMethod`).

## Settings (`core/settings.py`)

### Apps

`INSTALLED_APPS` registers the six domain apps after Django's own apps, in dependency order: `pages`, `accounts`, `dashboard`, `transactions`, `categories`, `payments`.

### Environment-driven configuration (production readiness)

Every deployment-specific setting reads from the environment so the same code runs unmodified in dev and in Docker (see [deployment.md](deployment.md)):

| Setting | Env var | Dev fallback |
|---|---|---|
| `SECRET_KEY` | `SECRET_KEY` | insecure `django-insecure-...` placeholder |
| `DEBUG` | `DEBUG` | `'True'` |
| `ALLOWED_HOSTS` | `ALLOWED_HOSTS` (comma-separated) | `localhost,127.0.0.1` |
| `DATABASES['default']['NAME']` | `SQLITE_PATH` | `<project root>/db.sqlite3` |
| `CURRENCY` / `CURRENCY_SYMBOL` | `CURRENCY` | `'BRL'` — see § Currency |
| The HTTPS block (5 settings) | `HTTPS` | `'False'` — see § HTTPS hardening |

`DEBUG` is read into a **module-level variable** at process startup (not just `django.conf.settings.DEBUG`) because Django's test runner force-overrides `settings.DEBUG` to `False` for every test run — see "Static files" below for why that distinction matters.

#### The secret key guard

The dev fallback is committed to a public template repository, so it is public knowledge: anyone holding it can forge session cookies and password-reset tokens against a fork still running on it. Settings therefore **refuse to import** when `DEBUG=False` and the key is still the fallback:

```python
INSECURE_SECRET_KEY = 'django-insecure-...'
SECRET_KEY = os.environ.get('SECRET_KEY', '').strip() or INSECURE_SECRET_KEY

if not DEBUG and SECRET_KEY == INSECURE_SECRET_KEY:
    raise ImproperlyConfigured(...)
```

Two details that are easy to get wrong:

- **Blank counts as unset.** `SECRET_KEY=` left empty in `.env` is the likeliest way to misconfigure this, and Django boots happily on an empty string — so the value falls through to the fallback and trips the guard rather than sailing past it.
- **It raises, rather than warning.** `check --deploy` already flags a weak key (`security.W009`), but nothing forces anyone to run it, and a fork deployed on the default key looks perfectly healthy while being trivially forgeable. Failing at import turns a silent compromise into a five-second fix.

`SecretKeyGuardTests` pins all four paths (unset, blank, real, and dev-on-the-fallback) by running `manage.py check` in a subprocess — the guard fires at settings *import* time, so `override_settings` cannot reach it.

#### HTTPS hardening

`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, the `SECURE_HSTS_*` trio, and `SECURE_PROXY_SSL_HEADER` are all driven by a single `HTTPS` env flag, **not** by `DEBUG`:

```python
HTTPS = os.environ.get('HTTPS', 'False') == 'True'
```

"Not in development" and "served over TLS" are different questions, and only the operator knows the second one. The shipped `docker-compose.yml` publishes plain HTTP on `:8000`, so tying these to `DEBUG=False` would break that documented first run outright — a browser never sends a `Secure` cookie over HTTP (login would appear to succeed, then bounce straight back to the form), and `SECURE_SSL_REDIRECT` would send `http://localhost:8000` into a redirect loop to an HTTPS port nothing is listening on.

With `HTTPS=True`, `manage.py check --deploy` returns clean. Without it, the four remaining warnings are accurate — the site genuinely is not over TLS. `SECURE_PROXY_SSL_HEADER` is set **only** when the flag is on, because a client can forge `X-Forwarded-Proto` when no proxy is there to strip it.

### Middleware

```
SecurityMiddleware
WhiteNoiseMiddleware        # right after SecurityMiddleware — serves static files in-process
SessionMiddleware
CommonMiddleware
CsrfViewMiddleware
AuthenticationMiddleware
MessageMiddleware
XFrameOptionsMiddleware
```

### Templates

`TEMPLATES[0]['DIRS']` points at the project-level `templates/` directory (in addition to each app's own `templates/<app>/` via `APP_DIRS=True`, though in practice every template in this project lives under the project-level directory — see [frontend.md](frontend.md)).

Custom context processors registered alongside Django's built-ins (`request`, `auth`, `messages`):

- `core.context_processors.currency` — injects `CURRENCY_SYMBOL` into every template.
- `core.context_processors.debug_flag` — injects `DEBUG` into every template (used by `base.html` to pick the Tailwind CDN vs. the compiled bundle).

### Static files

```python
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'   # collectstatic target, Docker build time only
```

`STORAGES['staticfiles']['BACKEND']` switches between `django.contrib.staticfiles.storage.StaticFilesStorage` (plain, when `DEBUG` is `True`) and `whitenoise.storage.CompressedManifestStaticFilesStorage` (hashed + gzip/brotli, when `DEBUG` is `False`) — selected from the **module-level** `DEBUG` computed once from the environment, not from `django.conf.settings.DEBUG`. This is what lets `manage.py test` run locally (where `DEBUG=True` at process start) without needing a real `collectstatic`-produced manifest, while a real `DEBUG=False` deployment always gets the WhiteNoise backend regardless of what the test runner does at request time.

`WHITENOISE_MANIFEST_STRICT = False` — a missing file in the manifest falls back to the plain path instead of a 500.

### Auth & redirects

```python
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:index'
LOGOUT_REDIRECT_URL = 'pages:landing'
```

### Currency

```python
CURRENCY = os.environ.get('CURRENCY', DEFAULT_CURRENCY)   # 'BRL'
CURRENCY_SYMBOL = get_currency(CURRENCY).symbol           # 'R$'
```

One environment-driven setting picks the currency project-wide. `CURRENCY_SYMBOL` is **derived**, not configured, and remains what every template reads via `core.context_processors.currency` — no screen hardcodes a symbol.

The registry lives in `core/currencies.py`, and each entry carries its number format alongside its symbol:

```python
Currency('BRL', 'R$', 'Brazilian Real', ',', '.'),
Currency('USD', '$',  'US Dollar',      '.', ','),
```

Both `CURRENCY_SYMBOL` and `core/formats/en/formats.py` read that same entry, so symbol and separators can never drift into a nonsense pairing like `$ 1.000,00`. An unknown code raises `ImproperlyConfigured` at startup listing the supported ones — silently defaulting would mislabel every amount in a finance app, which is a correctness bug rather than a cosmetic one.

`core/currencies.py` is imported *by* `core/settings.py`, so it deliberately holds no `django.conf` import at module level (the `ImproperlyConfigured` import inside `get_currency` is lazy for the same reason).

### Number formatting

```python
FORMAT_MODULE_PATH = 'core.formats'
USE_THOUSAND_SEPARATOR = True
```

Money renders in the configured currency's format — `R$ 1.000,00` for BRL, `$ 1,000.00` for USD — while `LANGUAGE_CODE` stays `en-us`. The separators live in `core/formats/en/formats.py` (read from `core/currencies.py`), **not** in `settings.py`, because Django reads the active locale's format module before falling back to the settings — see [data-model.md § Number format](data-model.md#number-format) for the full rationale and the two places localization is deliberately switched back off.

## URL routing (`core/urls.py`)

```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('pages.urls')),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('transactions/', include('transactions.urls')),
    path('categories/', include('categories.urls')),
    path('payments/', include('payments.urls')),
]
```

Every app namespaces its own URLs with `app_name = '<app>'`, so every reversed URL in a template or view is fully qualified, e.g. `{% url 'transactions:update' transaction.pk %}`. Full route table:

| Prefix | App | Routes (`name`) |
|---|---|---|
| `/` | `pages` | `landing` |
| `/accounts/` | `accounts` | `login`, `signup`, `logout` |
| `/dashboard/` | `dashboard` | `index` |
| `/transactions/` | `transactions` | `list`, `create`, `update`, `delete` |
| `/categories/` | `categories` | `list`, `create`, `update`, `delete` |
| `/payments/` | `payments` | `list`, `create`, `update`, `delete` |
| `/admin/` | Django admin | — |

## Request flow (a typical authenticated screen)

1. Request hits `core/urls.py`, dispatched to the matching app's `urls.py`.
2. The view is always a CBV mixing in `LoginRequiredMixin` (redirects to `LOGIN_URL` with a `?next=` param if the session is anonymous).
3. `get_queryset()` filters by `self.request.user` — every list/detail/update/delete view in the project does this; there is no view that returns another user's rows (see [data-model.md § Per-user isolation](data-model.md#per-user-isolation)).
4. For create/update views, `get_form_kwargs()` passes `user=self.request.user` into the form so FK dropdowns (`category`, `payment_method`, `parent_category`) only list that user's own records; `form_valid()` stamps `form.instance.user = self.request.user` before saving.
5. The template extends `templates/base.html`, which injects the right navbar (`navbar_app.html` vs. `navbar_public.html`) based on `request.user.is_authenticated`, renders `partials/messages.html`, then the page's `{% block content %}`.
6. `SuccessMessageMixin` (where used) queues a Django message consumed by `partials/messages.html` on the next page.

## Signals

Two apps wire a `post_save` signal on `User` via `AppConfig.ready()` to seed default data on signup (FR14) — see [apps/categories.md](apps/categories.md) and [apps/payments.md](apps/payments.md) for the exact payloads. Both signals live in `<app>/signals.py`, imported (never called directly) from `<app>/apps.py`.

## Admin

Every domain model except `Transaction`'s neighbors is registered in Django admin with `list_display`/`list_filter`/`search_fields` tuned per model (see each app doc). There is no custom admin site — `/admin/` is the stock Django admin, useful for inspecting data across users during development.
