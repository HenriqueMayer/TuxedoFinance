# `core`

The project package: cross-cutting configuration, localization, currency metadata and root routing. It owns no financial domain model.

`SECRET_KEY` is required from the process environment. Settings contains no
committed secret, placeholder or automatic fallback; generate and keep a
private key for each installation.

When the optional Docker image is used, `CASHFLOW_DATA_DIR=/data` moves the
SQLite file into the persistent container volume. The same settings and
automatic migrations are used as in the native workflow; the image never
ships runtime data or credentials.

## Files

| File | Purpose |
|---|---|
| `core/settings.py` | Django settings and supported UI languages; no user-facing currency setting. |
| `core/urls.py` | Root URLconf, including Django's `i18n/` routes and the domain apps. |
| `core/context_processors.py` | The authenticated user's currency context, registered in `TEMPLATES[0]['OPTIONS']['context_processors']`. |
| `core/currencies.py` | The supported-currency registry — symbol **and** number format per entry (FR20). |
| `core/formats/en/formats.py` | Locale number-format override driven by the code-level default (FR19). |
| `core/formats/pt_BR/formats.py` | Portuguese locale counterpart that preserves the same currency-driven number format. |
| `core/tests.py` | Language cookie, navbar, HTMX and language/currency-independence tests. |
| `core/wsgi.py` | Standard Django WSGI entrypoint, retained for future deployment packaging. |
| `core/asgi.py` | Standard ASGI entrypoint; unused in this project (no async views, no channels) but kept as Django scaffolding. |

## Local SQLite database

`DATABASES['default']` uses root `db.sqlite3` in the native workflow. When
`CASHFLOW_DATA_DIR` is set, Django stores `db.sqlite3` there; the optional
Docker package sets it to `/data`. The database file is
installation-owned runtime data and is ignored by Git. A clean clone creates it by running
`manage.py migrate`; the current source tree and future commits distribute
migrations rather than financial records. Older Git objects still contain
database versions pending the coordinated history cleanup. The installation
owner is responsible for file access, protection and backup; see
[`../operations.md`](../operations.md) for the supported procedure.

## Context processors

### `currency(request)`

```python
def currency(request):
    return {'CURRENCY_CODE': code, 'CURRENCY_SYMBOL': symbol}
```

For authenticated requests the context resolves the user's
`UserPreference.base_currency`; anonymous requests use the BRL bootstrap default.
Templates receive both `CURRENCY_CODE` and `CURRENCY_SYMBOL`. This value only
controls presentation and never changes stored native amounts.

## Currency registry (`core/currencies.py`)

```python
@dataclass(frozen=True)
class Currency:
    code: str
    symbol: str
    name: str
    decimal_separator: str
    thousand_separator: str


CURRENCIES = {
    currency.code: currency
    for currency in (
        Currency('BRL', 'R$', 'Brazilian Real', ',', '.'),
        Currency('USD', '$', 'US Dollar', '.', ','),
        ...
    )
}
```

One entry pairs a currency's symbol and separators. The registry is shared by
the user preference form, context processor, and locale number-format modules.

Two deliberate constraints on this module:

- **No `django.conf` import at module level.** `core/settings.py` imports it, so a top-level `from django.conf import settings` would be circular. Even the `ImproperlyConfigured` import inside `get_currency()` is lazy for the same reason.
- **`get_currency()` raises on an unknown code** instead of falling back to the default. A silent fallback would label every amount in a finance app with the wrong symbol — a correctness bug, not a cosmetic one — and the error message lists the supported codes with a formatted example each, so the fix is immediate.

Adding a currency is one line in `CURRENCIES` and nothing else.

## Interface localization

`LANGUAGE_CODE = 'en'`, while `LANGUAGES` exposes `en` and `pt-br` and
`LOCALE_PATHS` points to the project-level `locale/` directory.
`LocaleMiddleware` is immediately after `SessionMiddleware`: on the first
request it can negotiate a supported language from `Accept-Language`; after a
selection it activates the value in Django's native language cookie. Root URLs
use ordinary `path()` entries rather than `i18n_patterns()`, so switching
language never changes or prefixes an application URL.

`core/urls.py` mounts Django's native language view at
`/i18n/set_language/`. The selector sends a CSRF-protected POST containing
`language` and the current path as `next`; Django validates the redirect and
sets the cookie. No custom language preference model or endpoint exists.

The Portuguese source catalog is `locale/pt_BR/LC_MESSAGES/django.po`, with
the runtime catalog in `django.mo`. Regenerate it with GNU gettext installed:

```bash
uv run python manage.py makemessages -l pt_BR
uv run python manage.py compilemessages
```

For new interface strings, use `gettext_lazy` for module-level declarations
such as model/form labels and choices, and `gettext` for messages evaluated at
request/runtime. In templates load `i18n`, use `translate` (the modern name for
the `trans` tag) for short literals, and `blocktranslate` for sentences or copy
containing variables. Then update
the catalog, translate new entries and compile it. Do not mark category names,
notes, titles, bank names or any other user-entered/persisted values for
automatic translation.

`LocaleMiddleware` also activates the language for HTMX fragment requests; no
special client header or translation branch is required. `core/tests.py`
checks English defaults and selector presence, Portuguese cookie persistence,
desktop/mobile authenticated selectors, translated HTMX reports and identical
currency separators under both UI languages.

## Why no models/views here

`core` stays empty of domain logic. `accounts` owns the base-currency
preference; core provides registry and formatting primitives. Historical
Historical conversion evidence belongs to transfers and investments in the
current implementation; `core` only provides currency metadata and formatting
primitives.
