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
| `investments/services.py` | `get_per_currency_totals`, `get_latest_rates`, `get_simulated_total_in_base`, `get_exchange_rate_choices`, `get_supported_currencies`, `get_cumulative_balance_timeseries`, `get_rate_at` |
| `investments/forms.py` | `InvestmentForm`, `ExchangeRateForm` |
| `investments/views.py` | `InvestmentListView`, `InvestmentCreateView`, `InvestmentUpdateView`, `InvestmentDeleteView`, `ExchangeRateListView`, `ExchangeRateCreateView`, `ExchangeRateDeleteView` |
| `investments/urls.py` | `app_name = 'investments'`; routes for the 7 names above |
| `investments/admin.py` | `InvestmentAdmin`, `ExchangeRateAdmin` |
| `investments/migrations/0001_initial.py` | `Investment` |
| `investments/migrations/0002_*.py` | `AddField currency` on `Investment`; `CreateModel ExchangeRate` |
| `dashboard/charts.py` | `build_sparkline` (the per-currency sparkline geometry) |
| `templates/investments/list.html` | the screen — cards, simulated total, filter, list, per-currency sparklines |
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

def get_cumulative_balance_timeseries(user, currencies, months=12) -> list[dict]:
    """One row per month for the last `months` months, with `balances[code]`
    = cumulative signed_amount for that currency at the close of the
    month. Currencies with no entries stay at `ZERO` for every month, so
    the caller can render a fixed card per code without holes. Single
    query + a forward walk — same pattern as
    `dashboard.services.get_account_evolution`."""

def get_rate_at(user, from_currency, to_currency, on_date) -> ExchangeRate | None:
    """The most recent `ExchangeRate` for the pair with
    `effective_date <= on_date`, or `None` if none exists yet. Public
    API for any future feature that needs to convert a past balance
    at the rate that was current at the time."""
```

The list view's `get_context_data` calls the first three with the **unfiltered** user queryset, so a filtered table below never makes the cards lie. The same view also calls the time-series helper to build the per-currency sparkline grid at the bottom of the page; see "Time-series chart" below.

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

Same shape as `categories` and `payments` — CBVs + `LoginRequiredMixin` + `SuccessMessageMixin`, with a `FormMixin` (for create/update) that owns the `model`, `form_class`, `template_name`, `success_url`, and the user-scoped `get_queryset()`. The investments list view is the only one that has any custom `get_context_data` beyond the list pagination machinery (it has to call the services above: the three snapshot helpers that drive the per-currency cards and the simulated-total card at the top, plus the time-series helper that drives the sparkline grid at the bottom).

The exchange-rates views follow the same shape, with one difference: there is **no `update` view**. Rates are append-only by design — if the rate moved, the user adds a new row with a newer `effective_date`; the old one stays put for history. When an automated feed lands, it will write one row per day per pair; the existing rows are its history, and a missing update view is what keeps the schema future-proof.

`InvestmentDeleteView` and `ExchangeRateDeleteView` both follow the project's zero-JS POST pattern (delete is never a plain link/GET, always a POST from a confirm screen).

## No recurrence

Unlike `Transaction`, an `Investment` has no recurrence shape. There is no `is_fixed`, no `installments`, no `fixed_until` — a single row is exactly one move on the date the user recorded. The dashboard and reports pages project recurrences forward over months; the investments log is a flat history, and the running balance per currency is a plain sum (`Σ deposits − Σ withdrawals`).

## Time-series chart

Below the paginated list, one chart section answers the time-dimension question the per-currency cards (current snapshot) and the simulated-total card (current snapshot in base) do not:

  1. **Per-currency sparklines** — one mini chart per supported code, each on its **own** y-axis scale. Plotting every currency on a single axis would collapse the smaller balances into a flat line at the bottom (a USD balance of 100 next to a BRL balance of 50 000 would render as nothing); small multiples sidestep that. The card shows the code, the current balance in that currency, and a 12-month line. Native SVG `<title>` on the polyline surfaces the code and current balance on hover.

The section is wrapped in `{% if has_investments %}` and hidden when the user has recorded nothing. Six flat-at-zero sparklines are not informative, and the empty-state CTA above already tells the user to add an entry.

Static render: no HTMX, no prev/next arrows, no drill-downs. The user refreshes the page after adding a row. The window is `TIMESERIES_MONTHS = 12`, a local copy of `dashboard.services.EVOLUTION_MONTHS` (the investments app does not import from `dashboard.services` just to read the same number).

The sparkline series is **seeded with the user's pre-window balances** — the sum of every investment dated strictly before the first month of the 12-month window — so a deposit from 14 months ago shows up in the very first row, not only after the month it would land in. Without the seed, the sparkline at the oldest month would silently disagree with the per-currency card at the top (which uses `get_per_currency_totals` over **all** investments, no window) by exactly the size of the pre-window balance. The seed lives in `_pre_window_balances` in `investments.services` and is applied by `get_cumulative_balance_timeseries` at the start of the walk.

### Historical rate resolution (for any future feature)

`get_rate_at(user, from_currency, to_currency, on_date)` returns the most recent `ExchangeRate` with `effective_date <= on_date`, or `None` if the user has not set any rate for that pair yet. The current list page does not need it (the per-currency sparklines are intentionally not converted to base — see "Why no simulated total over time" below) but the helper is a useful primitive for any future feature that needs to convert a past balance at the rate that was current at the time, and it documents the historical-rate convention the `ExchangeRate` schema supports by design.

### Why no simulated total over time

The "Simulated total in {base} over time" chart that was in this section briefly is gone. Two reasons it would not work as a single time-series line:

  - **Multi-scale problem.** Plotting every currency on a shared axis collapses the smaller balances into a flat line at the bottom — the BRL would dominate and the USD contribution would be invisible. The stacked-area variant solved the visual problem but doubled the chart's complexity and added a second rate-resolution walk for marginal value (the user already sees the per-currency breakdown in the sparklines and the total in the card).
  - **Historical-rate dependency.** To convert a past balance, the chart would have to pick the `ExchangeRate` effective at the time. That logic is in `get_rate_at` (above) but the investments app does not store an automated rate history, so the conversion is a manually-curated approximation at best. The card at the top of the page — which uses the latest rate — is honest about the same caveat; a line chart stretching the same approximation over 12 months would only dress it up.

If a future feature needs the trend (e.g. an automated FX feed lands), the helpers to add it are the same ones this section used to call out: `get_simulated_breakdown_timeseries` for the per-month contribution and `build_stacked_area_chart` for the visual. They were removed along with the chart to keep the codebase honest about what is currently rendered.

### Per-currency sparkline color palette

A stable six-color palette, base currency in the primary indigo so it visually leads the row:

| Code | Stroke color | Notes |
|---|---|---|
| `base` (BRL or whatever `settings.CURRENCY` is) | `stroke-indigo-500` (dark: `indigo-400`) | primary, "your main portfolio" |
| `USD` | `stroke-emerald-500` | matches the Income semantic color from the Reports page |
| `EUR` | `stroke-sky-500` | |
| `GBP` | `stroke-violet-500` | |
| `JPY` | `stroke-rose-500` | matches the Expense semantic color, which is a coincidence |
| `CHF` | `stroke-amber-500` | matches the Investment semantic color |
| anything else | `stroke-slate-500` | a future currency added to `core/currencies.py` falls back to neutral gray until a color is picked for it |

The colors are spelled out directly in `templates/investments/list.html` (one per `elif` on the code) rather than mapped through a `tone` field, because each currency has a fixed color — the chart never re-tints a series based on what kind of value it is. A single fill class is also applied to the right-most "now" dot per series for emphasis.

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
