# `dashboard`

Two screens over the same data: the **index** (six aggregate indicators, a forward-looking outlook table, and a recent-transactions list) and **reports** (charts of how the account evolves over a year). The index is `LOGIN_REDIRECT_URL` — the first screen every user sees after signing up or logging in.

Both are a **forecast**, not a report of the past: the month the index shows can be navigated forward, and fixed transactions and open installment plans recur into those future months automatically.

## Files

| File | Contents |
|---|---|
| `dashboard/services.py` | `get_dashboard_summary(user, year, month)`, `get_account_evolution(user)`, `add_months()`, `OUTLOOK_MONTHS`, `EVOLUTION_MONTHS` |
| `dashboard/charts.py` | `build_line_chart()`, `build_bar_chart()` — SVG geometry only |
| `dashboard/views.py` | `DashboardIndexView`, `DashboardReportsView` |
| `dashboard/urls.py` | `app_name = 'dashboard'`; routes `index`, `reports` |
| `dashboard/models.py` | empty — this app has no data of its own, only aggregates `Transaction` |
| `dashboard/admin.py` | empty |
| `dashboard/tests.py` | 66 tests |
| `templates/dashboard/{index,reports}.html` | the screens |

The projection rules themselves live on the model, not here — see [data-model.md § Recurrence](../data-model.md#recurrence-when-a-transaction-hits-a-month) and [§ Balance formulas](../data-model.md#balance-formulas).

## `get_dashboard_summary(user, year=None, month=None)` (`dashboard/services.py`)

Returns every figure the screen needs for one selected month, defaulting to the current one:

| Key | Meaning |
|---|---|
| `current_balance` | Everything realized through **today's** month — independent of which month is selected. |
| `income_month` / `expense_month` / `investment_month` | The **selected** month alone, including recurrences. |
| `balance_month` | Selected month's net (Income − Expenses − Investments). |
| `projected_balance` | Current Balance rolled forward to the end of the selected month. |
| `outlook` | `OUTLOOK_MONTHS` (6) rows from the selected month, each with its own totals and a running `projected_balance`. |
| `selected_year` / `selected_month` / `selected_month_date` | What the screen is showing. |
| `is_current_month` / `is_future_month` | Drives the "Current month / Projection / Past month" label. |

### Why this is no longer a single SQL aggregate

The original version computed all six totals in one `.aggregate()` call with `Sum('amount', filter=Q(transaction_date__month=...))`. That is impossible now: a fixed transaction dated January contributes to *every* month after it, and an installment plan contributes a fraction of `amount` to each of N months. Neither is a predicate over `transaction_date`, so no `filter=Q(...)` can express it.

The replacement fetches the user's transactions **once** and folds them in Python:

```python
def _projection_queryset(user):
    return Transaction.objects.filter(user=user).only(
        'transaction_type', 'amount', 'installments',
        'is_fixed', 'fixed_until', 'transaction_date',
    )
```

- Still **one database round-trip** per dashboard render, regardless of how many months the outlook spans — the deferred `.only()` keeps it to the columns the arithmetic actually needs.
- **That column list is load-bearing, not an optimization detail.** Anything `amount_for_month` / `amount_through_month` reads must appear in it: a field left out is *deferred*, and touching it later silently costs one extra query **per row**, turning the single round-trip into an N+1 (NFR10). `fixed_until` belongs there for exactly this reason even though no screen displays it. Both query-count tests seed **fixed** rows on purpose — with only one-off fixtures they would pass while the real dashboard N+1s.
- What it gives up versus the old pure-SQL version is that work now scales with the user's transaction count in Python rather than in SQLite. For a personal finance app that is the right trade: correctness of the forecast is the entire feature, and the row counts are in the thousands at most. If a user's history ever made this slow, the fix is to cache the fold or snapshot closed months — not to go back to `Sum(filter=...)`, which cannot express recurrence at all.
- `_totals(...)` folds once per month; the outlook's running balance is accumulated month-to-month rather than recomputing a cumulative fold per row, so the whole outlook costs `OUTLOOK_MONTHS + 2` passes over an in-memory list.

### Other deliberate choices

- **`ZERO = Decimal('0.00')`** everywhere, matching the model's `DecimalField` precision — the fold starts from `ZERO`, so a user with no investments gets `0.00`, never `None`.
- **`transaction_date`**, never `created_at` — see [data-model.md § Date semantics](../data-model.md#date-semantics). `timezone.localdate()` (not `date.today()`) respects `USE_TZ`/`TIME_ZONE`.
- **Every balance subtracts Investment** — the one place in the codebase that encodes the PRD §8.5 decision that Investment is a cash outflow, while keeping it out of the Expenses indicator.
- **`add_months(year, month, offset)`** does month arithmetic through an absolute month index (`year * 12 + month - 1`), so year boundaries and negative offsets fall out for free instead of needing special cases.
- Callers **must** pass the actual logged-in user — there is no "aggregate everyone" mode, by design (PRD R3).

## `get_account_evolution(user)` (`dashboard/services.py`)

The series behind the reports page (FR16): `EVOLUTION_MONTHS` (12) consecutive months anchored on today — `EVOLUTION_PAST_MONTHS` (5) of history, the current month, and six projected ahead.

| Key | Meaning |
|---|---|
| `months` | One row per month: `date`, `is_current_month`, `is_future`, the three type totals, `balance`, and `closing_balance` (the running balance at that month's end). |
| `current_month` | The row for today's month — so templates never index `months` by a hardcoded offset. |
| `opening_balance` / `closing_balance` | Where the account stood entering the window, and where it is projected to end. |
| `net_change` | `closing − opening`: the one number that says whether the account is growing. |
| `best_month` / `worst_month` | Rows with the highest/lowest **net** (`balance`), not the highest income. |
| `expenses_by_category` | Up to `TOP_CATEGORIES` (6) rows: `name`, `total`, `bar_width`, `share`. |

History and forecast share one continuous series on purpose. A hard seam between "real" and "projected" months would only be visual noise — the template marks which is which (dimmer markers, a `(projected)` tooltip suffix) instead of splitting the chart.

Two details worth knowing:

- **The opening balance is one cumulative fold, not one per month.** `_totals(..., cumulative=True)` runs once for the month *before* the window; every rendered month then just adds its own net. Twelve cumulative folds would have been the obvious implementation and twelve times the work.
- **`_expenses_by_category` counts recurrences**, so a fixed R$ 50 rent appears as R$ 600 across the year, not R$ 50. It covers Expense only — Income has no category breakdown worth showing, and Investment is deliberately excluded so the chart answers "where does my *spending* go", consistent with §8.5 keeping the two outflows distinct everywhere else.
- `bar_width` is a percentage of the **largest** category (so the top bar always fills its track), while `share` is a percentage of **all** spending. The two exist because a bar sized by share would leave the chart nearly empty whenever spending is evenly spread.

`_projection_queryset(user, with_category=True)` adds `select_related('category')` and `category__name` to the deferred column list, so the breakdown reads `category.name` per row without an N+1. The whole function is **one query** — pinned by `AccountEvolutionTests.test_the_whole_evolution_costs_a_single_query`, with `get_dashboard_summary` pinned the same way by `DashboardProjectionTests.test_the_whole_summary_costs_a_single_query`.

## `dashboard/charts.py`

Pure geometry: it turns a list of floats into SVG coordinates and knows nothing about money, users, or Django. It exists because the project is zero-JS — there is no charting library to hand data to, so the pixel arithmetic the Django Template Language cannot express has to happen in Python.

```python
def _bounds(values):
    """Value range to plot, always including zero so the axis is honest."""
    lowest = min([*values, 0.0])
    highest = max([*values, 0.0])

    if lowest == highest:
        return -1.0, 1.0

    padding = (highest - lowest) * PADDING_RATIO
    return lowest - padding, highest + padding
```

- **The y-axis always includes zero.** A chart scaled to its own min/max turns a 2% wobble into a cliff; anchoring to zero keeps the slope truthful.
- **The all-zero case returns an arbitrary symmetric range** rather than dividing by zero — a brand-new account renders a flat line on the baseline instead of a `ZeroDivisionError`.
- **Tones, not colors.** `build_bar_chart` takes semantic `tone` values (`'income'`/`'expense'`/`'investment'`) and the template maps them to Tailwind classes, so design tokens stay in the template layer with every other color decision ([frontend.md](../frontend.md)).
- **Labels pass through untouched.** `DashboardReportsView` hands the whole month row in as the label, so the template reads `point.label.date` and `point.label.is_current_month` off each point instead of zipping two lists in the template.

## View (`DashboardReportsView`)

A `TemplateView` that calls `get_account_evolution()` once and feeds the same 12 rows into both chart builders. Everything else it does is composition — the finance math is in `services.py`, the pixel math in `charts.py`, and the view is the only place that knows both exist.

## Template (`templates/dashboard/reports.html`)

Three charts, all server-rendered, no `<script>` anywhere on the page (asserted by `test_reports_renders_both_charts`):

1. **Balance evolution** — an SVG `<polyline>` over a gradient-filled `<polygon>`, with a dashed zero line and one `<circle>` marker per month. Future months get a dimmer stroke.
2. **Monthly cash flow** — grouped `<rect>` bars, three per month (emerald/rose/amber per PRD §9.1), with a legend.
3. **Where the money goes** — plain CSS bars (`style="width: {{ category.bar_width }}%"`), no SVG needed.

Tooltips are native SVG `<title>` elements: browsers show them on hover with no JavaScript. Both SVGs sit in an `overflow-x-auto` wrapper with a `min-w-[44rem]` canvas — on a phone the chart scrolls inside its own card instead of shrinking its axis labels into illegibility (same convention as the outlook table).

## View (`DashboardIndexView`)

```python
def get_selected_month(self):
    """Parse `?month=YYYY-MM`, falling back to the current month."""
    today = timezone.localdate()
    raw = self.request.GET.get('month', '')
    year_part, _, month_part = raw.partition('-')

    if year_part.isdigit() and month_part.isdigit():
        year, month = int(year_part), int(month_part)
        if 1 <= month <= 12 and date.min.year <= year <= date.max.year:
            return year, month

    return today.year, today.month
```

Month selection is a plain `?month=YYYY-MM` GET param — the same zero-JS convention as the transaction list's filter, and the same forgiving behavior: a malformed or out-of-range value silently falls back to the current month rather than raising a `400`. The bounds check matters because `selected_month_date` builds a real `datetime.date`, which would raise `ValueError` on month `13` or year `99999`.

The view also precomputes `previous_month_param` / `next_month_param` (`YYYY-MM` strings) so the template's navigation links stay dumb.

It is a `TemplateView`, not a `ListView` — the "list" here (recent transactions) is a secondary, capped slice (`RECENT_TRANSACTIONS_LIMIT = 5`), not the primary paginated resource (that's `transactions:list`). `select_related` avoids N+1 queries when rendering each recent transaction's category/payment method name.

## Routes

| Path | Name | View |
|---|---|---|
| `/dashboard/` | `dashboard:index` | `DashboardIndexView` (supports `?month=YYYY-MM`) |
| `/dashboard/reports/` | `dashboard:reports` | `DashboardReportsView` (no params — always anchored on today) |

`settings.LOGIN_REDIRECT_URL = 'dashboard:index'` — this is where both `LoginView` and `SignupView` send the user on success.

The reports page takes **no** month parameter, unlike the index. Its window is defined relative to today by construction; a `?month=` there would just be a second, subtly different way to ask the same question.

## Template (`templates/dashboard/index.html`)

- A `New Transaction` button (linking to `transactions:create`), prominent per PRD 7.2.4.
- A **month navigation bar**: `←` / `→` links to the adjacent months, the selected month's name, a "Current month / Projection / Past month" label, and a "Back to this month" link whenever the user has navigated away. All plain `<a href>` — no JS.
- Six `partials/stat_card.html` includes in a `sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6` grid: **Current Balance** (neutral tone — no single semantic color owns a net figure that can be positive or negative), **Income (month)** (emerald), **Expenses (month)** (rose), **Investments (month)** (amber), **Balance (month)** (neutral), **Projected (end of month)** (neutral). Values are pre-formatted with `floatformat:2` and prefixed with `{{ CURRENCY_SYMBOL }}` before being passed into the partial — `stat_card.html` itself has no currency logic (see [frontend.md](../frontend.md)).
- An **Outlook table** — one row per upcoming month with Income / Expenses / Investments / Net / running projected balance. The selected row is tinted, the current month carries a `Now` badge, and negative figures turn rose. It sits in an `overflow-x-auto` wrapper with `min-w-[40rem]` so it scrolls inside its own container on mobile instead of forcing the page to scroll sideways.
- A "Recent transactions" list (up to 5 rows, same color-coded `+`/`−` treatment as `transactions/list.html`), or `partials/empty_state.html` if the user has never recorded one.

## Tests (`dashboard/tests.py`, 66 tests)

- **`DashboardAggregationTests`** — the §8.5 formulas against hand-computed fixtures: an all-zero baseline, a current+prior-month fixture asserting all five figures exactly, `test_investment_is_never_merged_into_expenses_indicator`, and `test_other_users_transactions_never_leak_into_aggregates` (a second user's intentionally huge `9999.00` must not move the first user's totals).
- **`DashboardProjectionTests`** — the forecast rules: a fixed income repeats in every future month but not before its start; a one-off does not repeat; installments spread one per month and stop after the last; a 3× split of `100.00` yields `33.33 / 33.33 / 33.34` and sums back to the total; `current_balance` counts only realized months while `projected_balance` rolls forward; the outlook spans `OUTLOOK_MONTHS` with a correct running balance and starts at the selected month; fixed and installment rows combine correctly across months; and **`test_editing_a_fixed_transaction_changes_every_future_month`**, which pins the behavior the whole feature exists for — edit the salary, and the projection follows. Three more cover `fixed_until` (FR18): **`test_ending_a_fixed_salary_preserves_past_months`** (the 2000-to-3000 raise, asserting every month has exactly one salary at the right amount), the projected balance stopping once an ended transaction has paid out, and an ended row dropping out of the outlook mid-table. **`test_the_whole_summary_costs_a_single_query`** seeds fixed rows specifically to catch a deferred recurrence column reloading per row (NFR10).
- **`DashboardViewTests`** — auth required; the view's context matches what `get_dashboard_summary()` returns directly (guards against view and service drifting apart); month selection defaults to the current month, honors `?month=`, and survives malformed input (`'nonsense'`, `'2026-13'`, `'2026-'`, `'-07'`, `''`); navigation params point at the right neighbours across a year boundary; the outlook actually renders; recent transactions are scoped to the logged-in user only.
- **`AccountEvolutionTests`** — the reports series: the window spans a year around today with exactly one month flagged current and only later ones flagged future; an empty account is all zeros; a fixed income accumulates linearly; history from *before* the window lands in `opening_balance` rather than in any rendered month; `net_change` equals `closing − opening`; best/worst are chosen by net, not by income; installments project into future months and stop; the category breakdown ranks correctly, counts recurrences, caps at `TOP_CATEGORIES`, excludes Income and Investment, and computes `bar_width`/`share` off different denominators; the whole thing is one query; another user's data never leaks in.
- **`ChartGeometryTests`** — the SVG maths, with no database involved: one point per value, x increasing left to right, bigger values sitting *higher* (smaller y, since SVG y grows downward), every point inside the plot area even with negatives, the axis always containing zero, an all-zero series not dividing by zero, the area polygon closed along the baseline with the line untouched between its anchors, bars growing up from the baseline, bars within a group never overlapping, and a zero-valued bar having zero height.
- **`DashboardReportsViewTests`** — auth required; both charts render as real `<polyline>`/`<rect>` markup with **no `<script>` on the page**; context matches the service; the legend carries all three transaction types; a fixed salary appears in every projected month; the category breakdown renders; an empty account renders without `NaN`; another user's category name and amount never appear. Three formatting guards (FR19): SVG coordinates and point lists are never localized (`x="90,83"` would break the chart), the category bar width parses as valid CSS, and money on the page uses the `1.234,56` format.
