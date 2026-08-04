"""Aggregations and conversions for the investments app.

Three helpers the list view and (eventually) the simulated-total card use:

  - `get_per_currency_totals`  folds the user's entries by `currency` and
    returns a dict keyed by code, with the per-currency deposited/withdrawn/
    balance totals. The card grid on the list page renders one card per code
    in the supplied `currencies` argument, in a stable order (base first,
    then alphabetical).

  - `get_latest_rates` returns the most recent `ExchangeRate` per
    `(from_currency, to_currency)` pair, as `{from: Decimal}`. The user
    keeps history (older rates stay in the table), but every conversion
    uses the latest.

  - `get_simulated_total_in_base` multiplies each currency's balance by its
    latest rate, sums the results, and reports which currencies had to be
    excluded because no rate was set. Currencies in the base are added at
    face value (rate 1.0 implicit).

All three are deliberately Python folds over a small in-memory list — the
project's "one query, fold in Python" pattern from `dashboard.services`,
adapted to a different domain. The single queryset the user owns is
always small enough that a second `.aggregate()` round-trip would buy
nothing measurable and cost a cross-currency join the database has no
business doing.
"""
from decimal import Decimal

from core.currencies import CURRENCIES
from investments.models import ExchangeRate, Investment

ZERO = Decimal('0.00')


def _currency_meta(code):
    """Return `(symbol, name)` for a known currency code, with safe defaults.

    Used by the list view to render a card label like `"USD — US Dollar"`.
    A code not in the registry is a programming error (the model's
    `choices` constraint would have rejected it on save), so the fallback
    is only for defensive rendering — never reached in practice.
    """
    currency = CURRENCIES.get(code)
    if currency is None:
        return code, code
    return currency.symbol, currency.name


def get_per_currency_totals(user, currencies):
    """Fold the user's investments by currency.

    `currencies` is the full list of codes the page wants to show
    (typically every supported currency in `CURRENCIES`, ordered by the
    caller). The returned dict always has one entry per supplied code,
    even when the user has no entries in that currency — so the template
    can render a fixed card grid that never has a hole.

    Totals are computed from the **unfiltered** user queryset, on the same
    reasoning as `InvestmentListView`: the cards on top of the page should
    not change shape when the user filters the list below them.
    """
    entries = list(Investment.objects.filter(user=user))

    totals = {
        code: {
            'code': code,
            'symbol': symbol,
            'name': name,
            'deposits': ZERO,
            'withdrawals': ZERO,
            'balance': ZERO,
        }
        for code, (symbol, name) in ((code, _currency_meta(code)) for code in currencies)
    }

    for entry in entries:
        bucket = totals.get(entry.currency)
        if bucket is None:
            # Defensive: a row whose currency is not in the supplied list
            # (the form's `choices` constraint should prevent this, but
            # if a future currency is added to the registry, old rows
            # could end up here until the user re-edits them).
            symbol, name = _currency_meta(entry.currency)
            bucket = {
                'code': entry.currency,
                'symbol': symbol,
                'name': name,
                'deposits': ZERO,
                'withdrawals': ZERO,
                'balance': ZERO,
            }
            totals[entry.currency] = bucket
        if entry.kind == Investment.Kind.DEPOSIT:
            bucket['deposits'] += entry.amount
        else:
            bucket['withdrawals'] += entry.amount
        bucket['balance'] += entry.signed_amount

    return totals


def get_latest_rates(user, to_currency):
    """Most recent `ExchangeRate` per `from_currency`, for the given base.

    Returns `{from_currency: rate}` with the latest effective row per pair.
    One query (all the user's rates), reduced in Python. The DB does not
    have a "group by with most recent" that survives ordering cleanly, and
    pulling every rate is cheap for a personal app.

    Pairs whose `to_currency` does not match `to_currency` are ignored —
    only rates aimed at the base are usable. Pairs in the base itself
    (`from == to`) are never stored (the form rejects them), so they do
    not appear here either; the caller handles base-currency conversion
    with a 1.0 implicit rate.
    """
    rates = (
        ExchangeRate.objects.filter(user=user, to_currency=to_currency)
        .order_by('from_currency', '-effective_date', '-created_at')
    )

    latest = {}
    for rate in rates:
        latest.setdefault(rate.from_currency, rate.rate)
    return latest


def get_simulated_total_in_base(user, base_currency, balances_by_code, rates):
    """Sum each currency's balance × its rate, in the base currency.

    `balances_by_code` is a `{code: Decimal}` mapping — typically the
    `balance` field of each row returned by `get_per_currency_totals`.
    `rates` is the `{from: Decimal}` mapping from `get_latest_rates`.

    Returns `(total, missing_currencies)`:

      - `total` is the simulated balance in the base currency, rounded to
        cents (the same precision the rest of the app uses for amounts).
        The base currency itself always contributes its balance at face
        value — no rate lookup needed.
      - `missing_currencies` is the list of currency codes that had a
        non-zero balance but no rate, so the caller can warn the user
        instead of silently showing a too-low total.

    A currency with zero balance is never reported as "missing" — there
    is nothing to convert, so the absence of a rate is harmless.
    """
    total = ZERO
    missing = []

    for code, balance in balances_by_code.items():
        if balance == ZERO:
            continue
        if code == base_currency:
            total += balance
            continue
        rate = rates.get(code)
        if rate is None:
            missing.append(code)
            continue
        total += balance * rate

    # Quantize to cents: balances are stored at 2dp, but `rate` is 8dp and
    # the multiplication can drift. `Investment` totals on the rest of the
    # page round to 2dp, so the simulated total matches what the user sees
    # elsewhere.
    quantized = total.quantize(Decimal('0.01'))
    return quantized, sorted(missing)


def get_exchange_rate_choices(base_currency):
    """`(value, label)` pairs for the `from_currency` field on the form.

    Excludes the base currency — the form rejects self-pairs, so the
    dropdown should not offer them in the first place. Used by
    `ExchangeRateForm` and by the rate list page to label the cards.
    """
    return [
        (code, f'{code} — {currency.name}')
        for code, currency in CURRENCIES.items()
        if code != base_currency
    ]


def get_supported_currencies(base_currency):
    """Every code the UI offers, base first then alphabetical.

    The investments list page renders a fixed card per code, in this
    order, so the base currency always leads. `get_per_currency_totals`
    consumes this list and returns one bucket per code.
    """
    others = sorted(code for code in CURRENCIES if code != base_currency)
    return [base_currency] + others
