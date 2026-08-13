"""Deterministic number formats for the English locale (FR20).

Currency codes and symbols are rendered explicitly per value. Django's format
module remains process-global, so separators use the code-level default.

Why this file exists at all: Django resolves formats from the locale's format
module *before* falling back to the `DECIMAL_SEPARATOR`/`THOUSAND_SEPARATOR`
settings, so setting those in `settings.py` would be silently ignored —
`django/conf/locale/en/formats.py` would win. Overriding them here (via
`FORMAT_MODULE_PATH`) is the documented way to change number formatting
without touching `LANGUAGE_CODE`, which would also switch Django's own UI
strings out of English.

Only number formats are overridden; date/time formats are inherited from
Django's `en` locale unchanged.

The module is read once because Django caches locale formats.
"""
from django.conf import settings

from core.currencies import NUMBER_GROUPING, get_currency  # noqa: F401

_currency = get_currency(settings.DEFAULT_CURRENCY)

DECIMAL_SEPARATOR = _currency.decimal_separator
THOUSAND_SEPARATOR = _currency.thousand_separator
