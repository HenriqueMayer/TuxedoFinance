"""Number formats driven by the configured base currency, not UI language."""

from django.conf import settings

from core.currencies import NUMBER_GROUPING, get_currency  # noqa: F401

_currency = get_currency(settings.DEFAULT_CURRENCY)

DECIMAL_SEPARATOR = _currency.decimal_separator
THOUSAND_SEPARATOR = _currency.thousand_separator
