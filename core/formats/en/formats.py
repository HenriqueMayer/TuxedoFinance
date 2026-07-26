"""Number formats for the `en` locale, driven by `settings.CURRENCY` (FR20).

The UI language stays English, but amounts are written the way the configured
currency writes them: `R$ 1.000,00` for BRL, `$ 1,000.00` for USD. Both the
symbol and these separators come from the same entry in `core/currencies.py`,
so the two can never disagree.

Why this file exists at all: Django resolves formats from the locale's format
module *before* falling back to the `DECIMAL_SEPARATOR`/`THOUSAND_SEPARATOR`
settings, so setting those in `settings.py` would be silently ignored —
`django/conf/locale/en/formats.py` would win. Overriding them here (via
`FORMAT_MODULE_PATH`) is the documented way to change number formatting
without touching `LANGUAGE_CODE`, which would also switch Django's own UI
strings out of English.

Only number formats are overridden; date/time formats are inherited from
Django's `en` locale unchanged.

Read once at import, because Django caches format modules — changing
`CURRENCY` needs a restart, like every other setting in this project.
"""
from django.conf import settings

from core.currencies import NUMBER_GROUPING, get_currency  # noqa: F401

_currency = get_currency(settings.CURRENCY)

DECIMAL_SEPARATOR = _currency.decimal_separator
THOUSAND_SEPARATOR = _currency.thousand_separator
