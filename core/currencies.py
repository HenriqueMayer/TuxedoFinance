"""Supported currencies and their number formats (PRD §8.5, FR20).

A currency is not just a symbol: `R$ 1.000,00` and `$ 1,000.00` differ in
their separators too, so picking one has to set both. This registry is the
single place that pairing is defined — `settings.CURRENCY` selects an entry,
`settings.CURRENCY_SYMBOL` is derived from it for templates, and
`core/formats/en/formats.py` reads the separators off the same entry.

Adding a currency is one line here and nothing else.

This module is imported by `core/settings.py`, so it must **not** import
`django.conf.settings` at module level — it stays pure data and lookups.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Currency:
    """A currency and the way its amounts are written."""

    code: str
    symbol: str
    name: str
    decimal_separator: str
    thousand_separator: str

    def example(self):
        """A formatted sample amount — used in docs and error messages."""
        return f'{self.symbol} 1{self.thousand_separator}000{self.decimal_separator}00'


CURRENCIES = {
    currency.code: currency
    for currency in (
        Currency('BRL', 'R$', 'Brazilian Real', ',', '.'),
        Currency('USD', '$', 'US Dollar', '.', ','),
        Currency('EUR', '€', 'Euro', ',', '.'),
        Currency('GBP', '£', 'British Pound', '.', ','),
        Currency('JPY', '¥', 'Japanese Yen', '.', ','),
        Currency('CHF', 'CHF', 'Swiss Franc', '.', "'"),
    )
}

DEFAULT_CURRENCY = 'BRL'

# Every supported currency groups digits in threes. Kept as a module constant
# rather than a per-currency field because nothing in the registry differs on
# it — add it to `Currency` on the day a lakh/crore currency shows up.
NUMBER_GROUPING = 3


def get_currency(code):
    """Return the `Currency` for `code`, raising on an unknown one.

    Raises rather than falling back to the default on purpose: a typo in
    `CURRENCY` would otherwise silently label every amount in the app with
    the wrong symbol, which is a correctness bug in a finance tool, not a
    cosmetic one. Failing at startup makes it a five-second fix instead.
    """
    try:
        return CURRENCIES[code]
    except KeyError:
        # Imported lazily: this module is loaded from `settings.py`, before
        # Django's own machinery is necessarily importable.
        from django.core.exceptions import ImproperlyConfigured

        supported = ', '.join(
            f'{currency.code} ({currency.example()})'
            for currency in CURRENCIES.values()
        )
        raise ImproperlyConfigured(
            f'CURRENCY={code!r} is not a supported currency. '
            f'Supported: {supported}.'
        ) from None
