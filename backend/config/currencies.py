"""Supported currencies and the way their amounts are written.

A currency sets its symbol and its separators together: ``R$ 1.000,00`` and
``$ 1,000.00`` differ in both. This registry is the single definition. The
API exposes it to the client, which formats amounts.

``config.settings`` may import this module, so it must not import
``django.conf.settings`` at module level.
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
        return f"{self.symbol} 1{self.thousand_separator}000{self.decimal_separator}00"


CURRENCIES = {
    currency.code: currency
    for currency in (
        Currency("BRL", "R$", "Brazilian Real", ",", "."),
        Currency("USD", "$", "US Dollar", ".", ","),
        Currency("EUR", "€", "Euro", ",", "."),
        Currency("GBP", "£", "British Pound", ".", ","),
        Currency("JPY", "¥", "Japanese Yen", ".", ","),
        Currency("CHF", "CHF", "Swiss Franc", ".", "'"),
    )
}

DEFAULT_CURRENCY = "BRL"

# Every supported currency groups digits in threes. Kept as a module constant
# rather than a per-currency field because nothing in the registry differs on
# it — add it to `Currency` on the day a lakh/crore currency shows up.
NUMBER_GROUPING = 3


def get_currency(code):
    """Return the `Currency` for `code`, raising on an unknown one.

    Raises rather than falling back to the default: an invalid stored or
    code-level currency must never silently label an amount with another code.
    """
    try:
        return CURRENCIES[code]
    except KeyError:
        # Imported lazily: settings may load this module before Django is ready.
        from django.core.exceptions import ImproperlyConfigured

        supported = ", ".join(
            f"{currency.code} ({currency.example()})" for currency in CURRENCIES.values()
        )
        raise ImproperlyConfigured(
            f"{code!r} is not a supported currency. Supported: {supported}."
        ) from None
