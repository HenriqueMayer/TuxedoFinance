# `investments`

A parallel log of money moved to and from the user's investment portfolio, **deliberately isolated from the `Transaction` universe**. `Transaction` already has a `TransactionType.INVESTMENT` choice, but that only marks a cash outflow on the dashboard — it has no idea *which* investment the money went into, what institution holds it, what currency the investment is denominated in, or what the running portfolio balance looks like. This app is where the user records the second half of that story, and the model never references `Transaction`. The two are kept in sync by the user; the `?kind=` and `reason` fields exist to make that explicit.

Two concrete workflows the app supports:

- **Cenário A** — "I have cash in my account and I want to move it into investments." Record a `Transaction` of type `INVESTMENT` (the money leaves the dashboard) and a matching `Investment` of kind `DEPOSIT` (the money arrives in the portfolio). Both are manual, both are independent.
- **Cenário B** — "I want to take money back out of the portfolio." Record an `Investment` of kind `WITHDRAWAL` (with a `reason`, e.g. "emergency", "rebalance"), then a matching `Transaction` of type `INVESTMENT` to bring the money back into the dashboard.

The `Transaction.amount_for_month` and the `Investment.balance` math are completely separate — the only thing tying the two together is the user. The app can be deleted, reseeded, or diverged from the transaction log without breaking either side, which is what "manual for control" means here.

## Files

| File | Contents |
|---|---|
| `investments/models.py` | `Investment`, `ExchangeRate` |
| `investments/services.py` | `get_per_currency_totals`, `get_latest_rates`, `get_simulated_total_in_base`, `get_exchange_rate_choices`, `get_supported_currencies`, `get_cumulative_balance_timeseries`, `get_rate_at`, `_resolve_rate`, `get_total_in_base_timeseries`, `get_monthly_flow_in_base` |
| `investments/forms.py` | `InvestmentForm`, `ExchangeRateForm` |
| `investments/views.py` | `InvestmentListView`, `InvestmentCreateView`, `InvestmentUpdateView`, `InvestmentDeleteView`, `ExchangeRateListView`, `ExchangeRateCreateView`, `ExchangeRateDeleteView` |
| `investments/urls.py` | `app_name = 'investments'`; routes for the 7 names above |
| `investments/admin.py` | `InvestmentAdmin`, `ExchangeRateAdmin` |
| `investments/migrations/0001_initial.py` | `Investment` |
| `investments/migrations/0002_*.py` | `AddField currency` on `Investment`; `CreateModel ExchangeRate` |
| `dashboard/charts.py` | `build_line_chart` (chart 1), `build_bar_chart` (chart 2) |
| `templates/investments/list.html` | the screen — cards, simulated total, filter, list, charts island |
| `templates/investments/_investments_charts.html` | HTMX-swappable partial: the two-chart island (investment evolution + monthly flow) |
| `templates/investments/form.html` | shared create/update form |
| `templates/investments/confirm_delete.html` | delete confirmation |
| `templates/investments/settings/exchange_rates_list.html` | the exchange-rates screen + inline create form |
| `templates/investments/settings/confirm_delete_rate.html` | exchange-rate delete confirmation |

For the `Investment` and `ExchangeRate` model fields, constraints, and the enums, see [data-model.md § Investment](../data-model.md#investment-investmentsmodelspy) and [data-model.md § ExchangeRate](../data-model.md#exchangerate-investmentsmodelspy).

## Why a separate app (and not a flag on `Transaction`)

Three reasons:

1. **The schema doesn't fit.** A `Transaction` is one cash flow with one category and one payment method, and the recurrence machinery (`is_fixed`, `installments`, billing cycle) all assumes that. An `Investment` has no recurrence shape — one row, one move, one date — and no category or payment method. Modeling it as a `Transaction` with a flag would leave a lot of fields nullable and an `isnull` branch in every `Transaction` query.
2. **The semantics differ.** The dashboard's `Transaction.amount_for_month` decides which month a row contributes to; the investments list's `Investment.balance` is a flat running sum. Mixing the two would mean the same row counted under two different aggregations, depending on which screen the user is looking at.
3. **The "parallel universe" rule is the user's.** Their stated requirement: a `Transaction` of type `INVESTMENT` removes money from the dashboard, and the matching `Investment` is a separate manual record. The two are kept in sync by the user. Building a hard link would be a "helpful" feature that contradicts the brief.

`Transaction` therefore keeps its `INVESTMENT` choice exactly as before, untouched. The investments app does not import `Transaction`, and the form's `kind` choice is the only thing they share conceptually (a `DEPOSIT` in investments is not a 1:1 mirror of an `EXPENSE` in transactions — the user can have one without the other).

## Multi-currency

Each `Investment` row carries its own `currency` (ISO 4217, validated against `core.currencies.CURRENCIES`). The list view shows one card per supported currency (BRL, USD, EUR, GBP, JPY, CHF — base first, then alphabetical), each with that currency's deposited / withdrawn / net balance. A `Settings` button on the list page links to the manual exchange-rate management screen.

The base currency is `settings.CURRENCY` (env-driven, project-wide). For an entry in a non-base currency, the user must have a matching `ExchangeRate` row in the settings page for the list page to include that balance in the simulated total; otherwise the entry's card is shown but the simulated total explicitly excludes it (`"{XYZ} excluded — set a rate to include it"`). The user always sees the reason a currency is not in the total, never a silent too-low number.

`ExchangeRate` is append-only. If the rate moves, the user adds a new row with a newer `effective_date`; the old one stays put for history. The list view always uses the most recent rate per pair (`get_latest_rates` reduces one query in Python). An automated feed would write one row per day per pair; the existing schema is shaped to receive that data without a migration when the automation lands.

## Services (`investments/services.py`)

The list view's per-currency cards, simulated total, and missing-rate warning are all computed in `investments.services`. The pattern matches the rest of the project: one query, fold in Python. For a personal app with a small in-memory list, a second `.aggregate()` round-trip would buy nothing measurable and cost a cross-currency join the database has no business doing.

```python
def get_per_currency_totals(user, currencies) -> dict[str, dict]:
    """Fold entries by currency. Always returns one bucket per code in `currencies`,
    even when the user has none in that currency — the grid never has a hole."""

def get_latest_rates(user, to_currency) -> dict[str, Decimal]:
    """Most recent ExchangeRate per (from_currency, to_currency) pair, as
    {from: Decimal}. One query, reduced in Python. Pairs whose target is not
    the base are ignored; self-pairs (BRL→BRL) are never stored."""

def get_simulated_total_in_base(user, base, balances, rates) -> tuple[Decimal, list[str]]:
    """Sum each currency's balance × its rate, in the base. Currencies with a
    non-zero balance but no rate are reported as 'missing' rather than
    silently excluded from the total. Quantizes to cents to match the rest
    of the app's amount precision."""

def get_exchange_rate_choices(base) -> list[(str, str)]:
    """`(value, label)` pairs for the ExchangeRateForm's `from_currency`,
    excluding the base (the form rejects self-pairs)."""

def get_supported_currencies(base) -> list[str]:
    """Every code the UI offers, base first then alphabetical. Drives the
    fixed card grid on the list page."""

def get_cumulative_balance_timeseries(user, currencies, months=12, offset=0) -> list[dict]:
    """One row per month for the last `months` months, with `balances[code]`
    = cumulative signed_amount for that currency at the close of the
    month. `offset` slides the anchor month (0 = today). Seeded with
    pre-window balances so old deposits show up in row 1."""

def get_rate_at(user, from_currency, to_currency, on_date) -> ExchangeRate | None:
    """The most recent ExchangeRate for the pair with
    `effective_date <= on_date`, or None if none exists yet."""

def _resolve_rate(user, code, base, on_date, latest_rates) -> tuple[Decimal|None, bool]:
    """Rate for code→base on/before on_date. Tries historical first,
    falls back to latest. Returns (rate, missing_flag)."""

def get_total_in_base_timeseries(user, base, currencies, months=12, offset=0) -> tuple[list[dict], list[str]]:
    """Cumulative portfolio total in base, one row per month. Folds
    get_cumulative_balance_timeseries through _resolve_rate. Drives
    the 'Investment evolution' line chart."""

def get_monthly_flow_in_base(user, base, currencies, months=12, offset=0) -> tuple[list[dict], list[str]]:
    """Deposits × withdrawals per month in base, per-entry rate lookup.
    Drives the 'Monthly flow' grouped-bar chart."""
```

The list view's `get_context_data` calls the card helpers with the **unfiltered** user queryset, so a filtered table below never makes the cards lie. It also calls the two FX-converted time-series helpers (each with its own `offset`) to build the two charts at the bottom of the page; see "Charts" below.

## Form (`InvestmentForm`)

```python
class InvestmentForm(forms.ModelForm):
    class Meta:
        model = Investment
        fields = ('title', 'kind', 'amount', 'currency', 'date', 'reason', 'notes')
```

`currency` is a `ModelChoiceField`-shaped `CharField` whose choices are built dynamically off `core.currencies.CURRENCIES`, so adding a currency in `core/currencies.py` is the only place the list is defined (matches the project's pattern with `Transaction.transaction_type` and `PaymentMethod.method_type`). Default is `settings.CURRENCY`. The shared `INPUT_CLASSES` styling string is applied in `__init__` like every other form in the project.

## Form (`ExchangeRateForm`)

```python
class ExchangeRateForm(forms.ModelForm):
    class Meta:
        model = ExchangeRate
        fields = ('from_currency', 'to_currency', 'rate', 'effective_date', 'notes')
```

Three rules the form enforces that the model cannot (or that the dropdown cannot):

- `to_currency` is **disabled** in the widget (the project is zero-JS, so the user cannot change it from the dropdown). The form's `clean()` re-pins it to `settings.CURRENCY` regardless of what was POSTed, so a forged request cannot smuggle in a different target.
- `from_currency` is restricted to `CURRENCIES - base` — the base never appears in the dropdown, and the form rejects it again at validation time as a safety net.
- `rate` uses `step="0.00000001"` and `MinValueValidator(Decimal('0.00000001'))` to cover exotic pairs (crypto).

The form is shared between the list page (rendered inline) and the standalone `create` view. The list view reuses the same template as the create view so the user sees the current rates above the form and the form below them in one screen — `get_context_data` on the create view re-publishes the bound form under the `create_form` key on a re-render after an invalid POST, so the field errors stay visible.

## Views

Same shape as `categories` and `payments` — CBVs + `LoginRequiredMixin` + `SuccessMessageMixin`, with a `FormMixin` (for create/update) that owns the `model`, `form_class`, `template_name`, `success_url`, and the user-scoped `get_queryset()`. The investments list view is the only one with custom `get_context_data` beyond the list pagination machinery — it calls the three snapshot helpers that drive the per-currency cards and the simulated-total card at the top, plus the two time-series services (offset-aware) and the two chart builders that drive the bottom-of-page charts island.

`InvestmentListView.get_template_names()` mirrors `DashboardReportsView`: when `HX-Request: true` is set (the header HTMX sends on every swap request) it returns `investments/_investments_charts.html`, the bare `<div id="investments-charts">` island the prev/next arrows target with `hx-target`. A normal GET returns the full `list.html`, which `{% include %}`s the same partial inside the page wrapper. Each chart owns an independent slide param — `?total_offset=N` and `?flow_offset=N` for charts 1 and 2 respectively — so sliding one chart leaves the other anchored (e.g. the user can scroll chart 1 a year back while watching the current month's flow on chart 2). Both are parsed by the same `_parse_charts_offset(request, param_name)` helper with a shared bounds check (`_is_offset_window_safe`) so a query string cannot walk any window off the calendar — `999999` falls back to 0 instead of raising, and a bad value on one chart doesn't drag the other. The kind/search filters (`?kind`, `?q`) ride alongside the two offsets and survive every arrow click via `{% querystring %}` (each chart's arrows update only its own param; the other is preserved implicitly by `{% querystring %}`).

The exchange-rates views follow the same shape, with one difference: there is **no `update` view**. Rates are append-only by design — if the rate moved, the user adds a new row with a newer `effective_date`; the old one stays put for history. When an automated feed lands, it will write one row per day per pair; the existing rows are its history, and a missing update view is what keeps the schema future-proof.

`InvestmentDeleteView` and `ExchangeRateDeleteView` both follow the project's zero-JS POST pattern (delete is never a plain link/GET, always a POST from a confirm screen).

## No recurrence

Unlike `Transaction`, an `Investment` has no recurrence shape. There is no `is_fixed`, no `installments`, no `fixed_until` — a single row is exactly one move on the date the user recorded. The dashboard and reports pages project recurrences forward over months; the investments log is a flat history, and the running balance per currency is a plain sum (`Σ deposits − Σ withdrawals`).

## Charts

Below the paginated list, two server-rendered SVG charts answer the time-dimension questions the per-currency cards (current snapshot in native units) and the simulated-total card (current snapshot in base) do not. Each chart owns an independent 12-month window, slideable through time via its own offset param (`?total_offset=N` and `?flow_offset=N` for charts 1 and 2) so sliding one does not drag the other. The prev/next arrows on every chart carry `hx-target="#investments-charts"` so HTMX patches the whole two-chart island in place rather than reloading the page — `{% querystring <param>=N %}` updates only that chart's param and preserves the other, plus the kind/search filters; a non-JS click still degrades to a plain GET (the symmetric zero-JS contract the Reports page established).

  1. **Investment evolution** — `build_line_chart`-driven area-line of the cumulative portfolio total in the base currency. Built from `get_total_in_base_timeseries` (rate-at-time FX fold). Inherits the Reports chart-1 visual contract: dashed rose zero line, indigo→fuchsia gradient stroke, violet 35%-to-0% area fill, `fill-white`/`fill-slate-950` per-month dots with `stroke-violet-400`. The prev/next arrows and the "Back to today" link anchor on this header.

  2. **Monthly flow** — `build_bar_chart`-driven grouped bars of Deposits × Withdrawals per month, both in base currency. Built from `get_monthly_flow_in_base` (per-entry rate-at-time FX on each entry's own `date`). Same legend swatch convention as the Reports cashflow chart: emerald for `Deposits`, rose for `Withdrawals`; native `<title>` tooltips on each `<rect>` give the month + series + value on hover.

The two charts replace an earlier per-currency sparkline grid (six mini charts, native units, no sliding). Sparklines worked as a small-multiples patch for the multi-scale problem but answered no question the user asked: "how is my portfolio doing" needs a consolidated number (charts 1 and 2).

The whole island is wrapped in `{% if has_investments %}` and hidden when the user has recorded nothing. Six flat-at-zero lines and bars are not informative, and the empty-state CTA above already tells the user to add an entry.

### FX model — rate-at-time, with graceful fallback

`get_total_in_base_timeseries` and `get_monthly_flow_in_base` both fold per-currency balances/flows into the base through `_resolve_rate`, which resolves a rate for `code -> base` on `on_date` as:

  1. **Historical lookup first** — `get_rate_at(user, code, base, on_date)` returns the most recent `ExchangeRate` for the pair with `effective_date <= on_date`. A USD deposit from April 2025 converts at the rate that was current in April 2025, not at today's rate.
  2. **Graceful fallback to `get_latest_rates`** — if no historical row exists for that pair on that date, fall back to the latest-available rate. A currency the user has only ever set one rate for still converts past months at that single rate.
  3. **Missing entirely → excluded** — neither historical nor latest exists for that pair. The currency is dropped from every month's total and reported in `missing_rate_currencies` so the page surfaces one unified warning across the simulated-total card and charts 1 and 2.

### Pre-window seed (cumulative helpers only)

`get_cumulative_balance_timeseries` and the derivation chain in `get_total_in_base_timeseries` seed the running dict with the user's pre-window balances — the sum of every investment dated strictly before the first month of the 12-month window — so a deposit from 14 months ago shows up in the very first row, not only after the month it would land in. Without the seed, the line at the oldest month would silently disagree with the per-currency card at the top (which uses `get_per_currency_totals` over **all** investments, windowless) by exactly the size of the pre-window balance. The seed lives in `_pre_window_balances` and is applied by `get_cumulative_balance_timeseries` at the start of the walk. **The flow helper does not seed** — flow is absolute per month, not a running sum, so pre-window entries are irrelevant.

## Routes

| Path | Name | View |
|---|---|---|
| `/investments/` | `investments:list` | `InvestmentListView` |
| `/investments/create/` | `investments:create` | `InvestmentCreateView` |
| `/investments/<pk>/edit/` | `investments:update` | `InvestmentUpdateView` |
| `/investments/<pk>/delete/` | `investments:delete` | `InvestmentDeleteView` |
| `/investments/settings/exchange-rates/` | `investments:exchange_rates` | `ExchangeRateListView` |
| `/investments/settings/exchange-rates/create/` | `investments:create_exchange_rate` | `ExchangeRateCreateView` |
| `/investments/settings/exchange-rates/<pk>/delete/` | `investments:delete_exchange_rate` | `ExchangeRateDeleteView` |

The `settings/exchange-rates/…` sub-resource has no navbar entry of its own — it is reached from the `Settings` button on the list page. Adding more "settings" sub-pages in the future (preferences, defaults, etc.) would extend this sub-resource rather than introduce a separate top-level route.

## Admin

```python
@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('date', 'title', 'kind', 'amount', 'currency', 'user', 'created_at')
    list_filter = ('user', 'kind', 'currency')
    search_fields = ('title', 'reason', 'notes')
    date_hierarchy = 'date'

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('from_currency', 'to_currency', 'rate', 'effective_date', 'user', 'created_at')
    list_filter = ('user', 'from_currency', 'to_currency')
    search_fields = ('notes',)
    date_hierarchy = 'effective_date'
```

Both registered in `django.contrib.admin` with `list_display` / `list_filter` / `search_fields` tuned per model. The stock Django admin is useful for inspecting data across users during development; there is no custom admin site.

## Currency support and the registry

`Investment.currency` and `ExchangeRate.from_currency` / `to_currency` both pull their choices from `core.currencies.CURRENCIES` (`BRL, USD, EUR, GBP, JPY, CHF`). Adding a currency is a single line in `core/currencies.py`; it then appears automatically in the investment form's currency select, in the exchange-rate form's `from_currency` select, and as a card on the list page. The form's `to_currency` select stays locked to the project base (`settings.CURRENCY`).

See [data-model.md § Currency display](../data-model.md#currency-display) and `core/currencies.py` for the registry itself.
