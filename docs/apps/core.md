# `core`

The project package — no models, no views, no URLs of its own beyond the root `urls.py`. Everything here is cross-cutting configuration consumed by the six domain apps.

## Files

| File | Purpose |
|---|---|
| `core/settings.py` | All Django settings — see [architecture.md § Settings](../architecture.md#settings-coresettingspy) for the full breakdown. |
| `core/urls.py` | Root URLconf; `include()`s every domain app's `urls.py` under its own prefix — see [architecture.md § URL routing](../architecture.md#url-routing-coreurlspy). |
| `core/context_processors.py` | Two custom context processors, registered in `TEMPLATES[0]['OPTIONS']['context_processors']`. |
| `core/currencies.py` | The supported-currency registry — symbol **and** number format per entry (FR20). |
| `core/formats/en/formats.py` | Locale number-format override driven by `settings.CURRENCY` (FR19). |
| `core/tests.py` | 21 tests — the currency registry, the active number format, and the `SECRET_KEY` / HTTPS settings guards. |
| `core/wsgi.py` | Standard `django-admin startproject` WSGI entrypoint; used by `gunicorn` in production (`core.wsgi:application`, see the `Dockerfile` `CMD`). |
| `core/asgi.py` | Standard ASGI entrypoint; unused in this project (no async views, no channels) but kept as Django scaffolding. |

## Context processors

### `currency(request)`

```python
def currency(request):
    return {'CURRENCY_SYMBOL': settings.CURRENCY_SYMBOL}
```

Exposes `settings.CURRENCY_SYMBOL` to every template as `{{ CURRENCY_SYMBOL }}`, so no screen ever hardcodes a currency symbol (PRD §8.5). Used throughout `templates/dashboard/index.html`, `templates/dashboard/reports.html`, `templates/transactions/list.html`, and `templates/pages/landing.html`'s sample preview.

`CURRENCY_SYMBOL` is **derived**, not configured directly: `settings.CURRENCY` (default `'BRL'`) selects an entry from `core/currencies.py`, and the symbol comes off that entry. See § Currency registry below.

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

One entry pairs a symbol with the separators that currency is written with, because those are not independent choices — `$ 1.000,00` is wrong everywhere. Two consumers read the same entry:

- `core/settings.py` → `CURRENCY_SYMBOL = get_currency(CURRENCY).symbol`
- `core/formats/en/formats.py` → `DECIMAL_SEPARATOR` / `THOUSAND_SEPARATOR`

so they cannot drift apart. `ActiveCurrencyTests` asserts that agreement holds for whatever `CURRENCY` is configured.

Two deliberate constraints on this module:

- **No `django.conf` import at module level.** `core/settings.py` imports it, so a top-level `from django.conf import settings` would be circular. Even the `ImproperlyConfigured` import inside `get_currency()` is lazy for the same reason.
- **`get_currency()` raises on an unknown code** instead of falling back to the default. A silent fallback would label every amount in a finance app with the wrong symbol — a correctness bug, not a cosmetic one — and the error message lists the supported codes with a formatted example each, so the fix is immediate.

Adding a currency is one line in `CURRENCIES` and nothing else.

## Why no models/views here

`core` is intentionally empty of domain logic, per the "no over-engineering" house rule — it exists purely to wire the six domain apps together (settings, root routing, the two context processors, and the currency/format configuration above). Business logic always lives in the owning domain app. `core` is not in `INSTALLED_APPS` and has no migrations; `core/tests.py` is still collected, because Django's test runner discovers tests by walking packages rather than by reading `INSTALLED_APPS`.
