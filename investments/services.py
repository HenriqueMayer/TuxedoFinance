"""Aggregations and conversions for the investments app.

Seven helpers, in three layers:

  Card layer — current snapshot, one number per currency:
    - `get_per_currency_totals` folds the user's entries by `currency` and
      returns a dict keyed by code, with the per-currency deposited/withdrawn/
      balance totals. The card grid on the list page renders one card per
      code in the supplied `currencies` argument, in a stable order (base
      first, then alphabetical).
    - `get_latest_rates` returns the most recent `ExchangeRate` per
      `(from_currency, to_currency)` pair, as `{from: Decimal}`. The user
      keeps history (older rates stay in the table), but every conversion
      uses the latest.
    - `get_simulated_total_in_base` multiplies each currency's balance by
      its latest rate, sums the results, and reports which currencies had
      to be excluded because no rate was set. Currencies in the base are
      added at face value (rate 1.0 implicit).

  Time-series layer — native units per currency per month:
    - `get_cumulative_balance_timeseries` returns the running balance
      per currency for each of the last `months` months anchored on
      today. The balances are cumulative — each row is the sum of every
      entry whose date is in that month or earlier. Seeded with the
      user's pre-window balances (see `_pre_window_balances`) so an old
      deposit shows up in the very first row, not only after the month
      it would land in. Drives the per-currency indexed multi-line chart
      (no FX) on the list page; the cumulative-chart helper below also
      consumes its rows.

  FX-converted time-series layer — base-currency numbers per month, so
  the page can plot one consolidated trend instead of six native-unit
  lines whose scales are not comparable:
    - `get_total_in_base_timeseries` folds each month's per-currency
      balances into a single base-currency cumulative total, via
      `_resolve_rate` (rate-at-time, fallback to latest). Drives the
      "Investment evolution" line chart.
    - `get_monthly_flow_in_base` produces per-month deposit and
      withdrawal totals in base, via the same rate resolution. Drives
      the "Monthly flow" grouped-bar chart.
    - `get_rate_at` is the rate-effective-on-or-before-a-date primitive
      both helpers rely on.

  UI helpers (used by the list view and the settings page):
    - `get_exchange_rate_choices` and `get_supported_currencies` for
      form/picker options.

All seven are deliberately Python folds over small in-memory lists —
the project's "one query, fold in Python" pattern from
`dashboard.services`, adapted to a different domain. The single queryset
the user owns is always small enough that a second `.aggregate()`
round-trip would buy nothing measurable and cost a cross-currency join
the database has no business doing.
"""
from datetime import date
from decimal import Decimal

from django.utils import timezone

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
    entries = list(
        Investment.objects.filter(
            user=user, product__isnull=False, asset__isnull=False
        ).select_related('asset')
    )

    totals = {
        code: {
            'code': code,
            'symbol': symbol,
            'name': name,
            'deposits': ZERO,
            'withdrawals': ZERO,
            'yields': ZERO,
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
                'yields': ZERO,
                'balance': ZERO,
            }
            totals[entry.currency] = bucket
        if entry.kind == Investment.Kind.DEPOSIT:
            bucket['deposits'] += entry.amount
        elif entry.kind == Investment.Kind.WITHDRAWAL:
            bucket['withdrawals'] += entry.amount
        else:
            bucket['yields'] += entry.amount
        bucket['balance'] += entry.signed_amount

    return totals


def get_portfolio_groups(user):
    """Return balances grouped by institution, product, and asset."""
    entries = Investment.objects.filter(
        user=user, product__isnull=False, asset__isnull=False
    ).select_related('product__institution', 'asset')
    institutions = {}
    for entry in entries:
        institution = entry.product.institution
        institution_bucket = institutions.setdefault(
            institution.id,
            {
                'id': institution.id,
                'name': institution.name,
                'balance': ZERO,
                'deposits': ZERO,
                'withdrawals': ZERO,
                'yields': ZERO,
                'products': {},
            },
        )
        product_bucket = institution_bucket['products'].setdefault(
            entry.product.id,
            {
                'id': entry.product.id,
                'name': entry.product.name,
                'yield_mode': entry.product.yield_mode,
                'balance': ZERO,
                'deposits': ZERO,
                'withdrawals': ZERO,
                'yields': ZERO,
                'assets': {},
            },
        )
        asset_bucket = product_bucket['assets'].setdefault(
            entry.asset.id,
            {
                'id': entry.asset.id,
                'name': entry.asset.name,
                'code': entry.asset.code,
                'currency': entry.asset.currency,
                'balance': ZERO,
                'deposits': ZERO,
                'withdrawals': ZERO,
                'yields': ZERO,
            },
        )
        buckets = (institution_bucket, product_bucket, asset_bucket)
        for bucket in buckets:
            bucket['balance'] += entry.signed_amount
            bucket_key = {
                Investment.Kind.DEPOSIT: 'deposits',
                Investment.Kind.WITHDRAWAL: 'withdrawals',
                Investment.Kind.YIELD: 'yields',
            }[entry.kind]
            bucket[bucket_key] += entry.amount

    result = []
    for institution in institutions.values():
        institution['products'] = list(institution['products'].values())
        for product in institution['products']:
            product['assets'] = list(product['assets'].values())
        result.append(institution)
    return result


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


# ---------------------------------------------------------------------------
# Time-series helpers — used by the per-currency sparklines and the
# simulated-total chart at the bottom of the list page.
# ---------------------------------------------------------------------------

# Mirror of `dashboard.services.EVOLUTION_MONTHS`. Kept as a local
# constant so the investments app does not need to import from `dashboard`
# just to read the same window size.
TIMESERIES_MONTHS = 12


def _add_months(year, month, offset):
    """Return the (year, month) pair `offset` whole months from (year, month).

    Local copy of `dashboard.services.add_months` so this module does not
    need to reach into another app. The two implementations are bit-for-bit
    identical and should stay so — the dashboard and the investments list
    page show the same 12 months anchored on the same today.
    """
    index = (year * 12 + month - 1) + offset
    return index // 12, index % 12 + 1


def _group_investments_by_month(investments):
    """Bucket an investments list by `(year, month)` of the entry's date.

    The result is a `{ (year, month): [Investment, ...] }` dict, in
    insertion order so a caller that walks a month window in order sees
    the months in chronological order too. The caller still has to
    pre-sort `investments` by date if it cares about per-row order
    within a month — the meta ordering on the model (`-date, -created_at`)
    is the opposite of what a forward walk wants, so we explicitly
    re-sort here.
    """
    bucketed = {}
    for entry in sorted(investments, key=lambda entry: (entry.date, entry.created_at)):
        key = (entry.date.year, entry.date.month)
        bucketed.setdefault(key, []).append(entry)
    return bucketed


def _pre_window_balances(investments, currencies, before_year, before_month):
    """Sum of `signed_amount` for investments dated strictly before `(before_year, before_month)`.

    Used to seed the time-series helpers' `running` dict so the
    sparkline grid and the simulated-total chart at the bottom of
    the list page are consistent with the per-currency cards at the
    top. The cards use `get_per_currency_totals` over **all** the
    user's investments (no window); without this seed, a deposit
    from 14 months ago would silently disappear from every chart on
    the page while still showing up on the cards.

    `currencies` is the set of codes the caller wants to track — the
    same set the caller would pass to `get_cumulative_balance_timeseries`
    or build from `running` for the simulated-total chart. Codes
    present in `investments` but not in `currencies` are silently
    dropped (defensive: matches the policy of the other helpers).
    """
    balances = {code: ZERO for code in currencies}
    for entry in investments:
        is_pre_window = entry.date.year < before_year or (
            entry.date.year == before_year and entry.date.month < before_month
        )
        if is_pre_window and entry.currency in balances:
            balances[entry.currency] += entry.signed_amount
    return balances


def get_cumulative_balance_timeseries(user, currencies, months=TIMESERIES_MONTHS, offset=0):
    """Cumulative balance per currency, one row per month, for `months` back.

    The window is anchored `offset` months from today (oldest month
    first). For each month in the window the function returns a
    `{'date', 'year', 'month', 'balances': {code: Decimal}}` row whose
    `balances[code]` is the sum of every `signed_amount` for `code` whose
    date is in that month or earlier — i.e. the running balance at the
    close of the month.

    The running dict is **seeded with the user's pre-window balances**
    (sum of every entry dated strictly before the first month of the
    window), so a deposit from 14 months ago shows up in the very
    first row, not only after the month it would land in. Without the
    seed, the sparkline grid at the bottom of the page would silently
    disagree with the per-currency cards at the top — the cards use
    `get_per_currency_totals` (all investments, no window), so they
    include pre-window balances; the chart would not.

    Currencies in `currencies` that the user has no entries for stay
    at `ZERO` for every month, so the caller can render a fixed card
    per code without holes (same shape `get_per_currency_totals`
    enforces for the snapshot).

    Single query (the user's investments) + a Python walk. The dashboard
    uses the same pattern; see `dashboard.services.get_account_evolution`
    for the same argument from the other domain.
    """
    investments = list(
        Investment.objects.filter(
            user=user, product__isnull=False, asset__isnull=False
        ).select_related('asset')
    )
    bucketed = _group_investments_by_month(investments)

    today = timezone.localdate()
    # Anchor `offset` months from today, then walk back `months-1` to
    # build the window oldest-first. `offset=0` reproduces the old
    # "anchored on today" behaviour; the charts page slides the anchor
    # via `?charts_offset=N`.
    anchor_year, anchor_month = _add_months(today.year, today.month, offset)
    months_window = [
        _add_months(anchor_year, anchor_month, -(months - 1) + step)
        for step in range(months)
    ]
    window_start_year, window_start_month = months_window[0]

    # Seed `running` with everything the user invested before the
    # window — see `_pre_window_balances` for the why.
    running = _pre_window_balances(
        investments, currencies, window_start_year, window_start_month
    )

    rows = []
    for year, month in months_window:
        for entry in bucketed.get((year, month), []):
            if entry.currency in running:
                running[entry.currency] += entry.signed_amount
            # else: defensive — a row whose currency is not in the
            # supplied list (the form's `choices` should prevent it,
            # but a future currency added to the registry could leave
            # a stale row here until the user re-edits it). Silently
            # dropped from the running total — same policy as
            # `get_per_currency_totals`.

        rows.append(
            {
                'date': date(year, month, 1),
                'year': year,
                'month': month,
                # Snapshot, not the running dict — the caller must not
                # accidentally mutate the row's balances by holding a
                # reference to the running state.
                'balances': dict(running),
            }
        )
    return rows


def get_rate_at(user, from_currency, to_currency, on_date):
    """The `ExchangeRate` effective on or before `on_date` for the pair.

    Rates are append-only over time: when a rate moves the user adds a
    new row with a newer `effective_date`. To convert a balance from
    "back then" the conversion needs the rate that was *current* back
    then, which is the most recent row with `effective_date <= on_date`.

    Returns the matching `ExchangeRate` instance, or `None` if the
    pair has no rate yet on or before `on_date`. Same-currency pairs
    (`from_currency == to_currency`) are never stored (the form
    rejects them) and never returned here; the caller handles them
    with an implicit 1.0 rate.

    Used by `get_total_in_base_timeseries` and `get_monthly_flow_in_base`
    to fold past per-currency balances/flows into a single base-currency
    number at the rate that was current at the time.
    """
    if from_currency == to_currency:
        return None
    return (
        ExchangeRate.objects.filter(
            user=user,
            from_currency=from_currency,
            to_currency=to_currency,
            effective_date__lte=on_date,
        )
        .order_by('-effective_date', '-created_at')
        .first()
    )


CENTS = Decimal('0.01')


def _resolve_rate(user, code, base_currency, on_date, latest_rates):
    """Rate for `code -> base_currency` effective on/before `on_date`.

    Same FX contract the time-series helpers share: try the historical
    lookup first (the rate that was *current* on `on_date`), fall back to
    the latest-available rate so a recently-added currency that the user
    has only ever set one rate for still converts past months. Returns
    ``(rate_or_None, missing_flag)`` — when both the historical and the
    latest lookups miss, the caller adds `code` to its `missing` report.
    Helper kept local so `get_total_in_base_timeseries` and
    `get_monthly_flow_in_base` shared one resolution path rather than
    drifting.
    """
    if code == base_currency:
        return Decimal('1.0'), False
    rate_row = get_rate_at(user, code, base_currency, on_date)
    if rate_row is not None:
        return rate_row.rate, False
    rate_value = latest_rates.get(code)
    if rate_value is None:
        return None, True
    return rate_value, False


def get_total_in_base_timeseries(
    user, base_currency, currencies, months=TIMESERIES_MONTHS, offset=0
):
    """Cumulative portfolio total in the base currency, one row per month.

    Builds on `get_cumulative_balance_timeseries` (per-currency running
    balances in native units, seeded with pre-window balances), then folds
    each month's balances into a single base-currency number through
    `_resolve_rate` — the rate effective on/before that month's date, with
    a graceful fallback to the latest-available rate so a currency the
    user has only ever set one rate for still converts past months. The
    base currency contributes at face value (rate 1.0 implicit).

    A currency that has no rate at all (neither historical nor latest) is
    excluded from the total of every row and reported in
    `missing_rate_currencies`, so the caller can warn the user instead of
    silently showing a too-low line — same contract as
    `get_simulated_total_in_base` on the snapshot card.

    Returns ``(rows, missing_rate_currencies)``:

      - `rows` is a list of `{'date', 'year', 'month', 'total'}` dicts in
        chronological order (oldest first). `total` is a `Decimal`
        quantized to cents.
      - `missing_rate_currencies` is the sorted list of codes excluded
        because no rate was set for them.
    """
    cumulative = get_cumulative_balance_timeseries(
        user, currencies, months=months, offset=offset
    )
    latest_rates = get_latest_rates(user, base_currency)

    missing = []
    rows = []
    for row in cumulative:
        row_total = ZERO
        row_date = row['date']
        for code in currencies:
            balance = row['balances'].get(code, ZERO)
            if balance == ZERO:
                continue
            rate_value, is_missing = _resolve_rate(
                user, code, base_currency, row_date, latest_rates
            )
            if rate_value is None:
                if code not in missing:
                    missing.append(code)
                continue
            row_total += balance * rate_value
        rows.append(
            {
                'date': row_date,
                'year': row['year'],
                'month': row['month'],
                'total': row_total.quantize(CENTS),
            }
        )
    return rows, sorted(missing)


def get_monthly_flow_in_base(
    user, base_currency, currencies, months=TIMESERIES_MONTHS, offset=0
):
    """Deposits, withdrawals, and yields per month in the base currency.

    Unlike `get_total_in_base_timeseries` (cumulative), this is per-month
    flow: each row holds a single month's DEPOSIT, WITHDRAWAL, and YIELD totals
    in base. Per-entry rate lookup via `_resolve_rate`
    on `entry.date` so the FX used is the rate that was current when the
    entry was recorded, not the latest one. Pre-window balances are NOT
    seeded here — flow is absolute per month, not a running sum.

    Same `missing_rate_currencies` contract as the cumulative helper:
    a currency with no rate at all is excluded from every month's totals
    and reported so the caller can warn.

    Returns ``(rows, missing_rate_currencies)``:

      - `rows` is a list of
        `{'date', 'year', 'month', 'deposits', 'withdrawals'}` in
        chronological order (oldest first). Both `deposits` and
        `withdrawals` are positive `Decimal`s (the sign is conveyed by
        which bucket they landed in), quantized to cents.
      - `missing_rate_currencies` is the sorted list of codes excluded.
    """
    investments = list(
        Investment.objects.filter(
            user=user, product__isnull=False, asset__isnull=False
        ).select_related('asset')
    )
    bucketed = _group_investments_by_month(investments)
    latest_rates = get_latest_rates(user, base_currency)

    today = timezone.localdate()
    anchor_year, anchor_month = _add_months(today.year, today.month, offset)
    months_window = [
        _add_months(anchor_year, anchor_month, -(months - 1) + step)
        for step in range(months)
    ]

    currency_set = set(currencies)
    missing = []
    rows = []
    for year, month in months_window:
        deposits = ZERO
        withdrawals = ZERO
        yields = ZERO
        for entry in bucketed.get((year, month), []):
            if entry.currency not in currency_set:
                continue
            amount = entry.amount
            rate_value, _ = _resolve_rate(
                user, entry.currency, base_currency, entry.date, latest_rates
            )
            if rate_value is None:
                if entry.currency not in missing:
                    missing.append(entry.currency)
                continue
            converted = amount * rate_value if entry.currency != base_currency else amount
            if entry.kind == Investment.Kind.DEPOSIT:
                deposits += converted
            elif entry.kind == Investment.Kind.WITHDRAWAL:
                withdrawals += converted
            else:
                yields += converted
        rows.append(
            {
                'date': date(year, month, 1),
                'year': year,
                'month': month,
                'deposits': deposits.quantize(CENTS),
                'withdrawals': withdrawals.quantize(CENTS),
                'yields': yields.quantize(CENTS),
            }
        )
    return rows, sorted(missing)
