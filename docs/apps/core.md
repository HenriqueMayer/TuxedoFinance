# `core`

The project package: cross-cutting configuration, localization, currency metadata and root routing. It owns no financial domain model.

## Files

| File | Purpose |
|---|---|
| `core/settings.py` | Django settings, supported UI languages and the default base currency for new users. |
| `core/urls.py` | Root URLconf, including Django's `i18n/` routes, `banking`, and excluding removed `payments`. |
| `core/context_processors.py` | Two custom context processors, registered in `TEMPLATES[0]['OPTIONS']['context_processors']`. |
| `core/currencies.py` | The supported-currency registry — symbol **and** number format per entry (FR20). |
| `core/formats/en/formats.py` | Locale number-format override driven by `settings.CURRENCY` (FR19). |
| `core/formats/pt_BR/formats.py` | Portuguese locale counterpart that preserves the same currency-driven number format. |
| `core/tests.py` | Language cookie, navbar, HTMX and language/currency-independence tests. |
| `core/wsgi.py` | Standard `django-admin startproject` WSGI entrypoint; used by `gunicorn` in production (`core.wsgi:application`, see the `Dockerfile` `CMD`). |
| `core/asgi.py` | Standard ASGI entrypoint; unused in this project (no async views, no channels) but kept as Django scaffolding. |

## Context processors

### `currency(request)`

```python
def currency(request):
    return {'CURRENCY_SYMBOL': settings.CURRENCY_SYMBOL}
```

The single-symbol context value is retained only for legacy/public examples during
the breaking implementation. Authenticated money rendering must resolve metadata
from each value's native currency; the user's `BankingProfile.base_currency`
drives consolidation. No banking template may assume `CURRENCY_SYMBOL` describes
every amount.

### `debug_flag(request)`

```python
def debug_flag(request):
    return {'DEBUG': settings.DEBUG}
```

Exposes `settings.DEBUG` to every template as `{{ DEBUG }}`. `templates/base.html` uses it to choose between the Tailwind Play CDN (`DEBUG=True`) and the compiled, WhiteNoise-served `css/output.css` bundle (`DEBUG=False`) — see [frontend.md § Tailwind strategy](../frontend.md#tailwind-strategy-devprod). Deliberately separate from Django's built-in `django.template.context_processors.debug` processor, which only activates for requests from `INTERNAL_IPS` — unsuitable for an always-on template switch that must work identically for every visitor in production.

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

One entry pairs a currency's symbol and separators. Money renderers select the
entry by each amount's currency; `settings.CURRENCY` supplies only the default
base currency for a new `BankingProfile` and public examples.

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

`core` stays empty of domain logic. Banking owns base-currency preference and
historical conversion; core only provides registry/configuration primitives.
