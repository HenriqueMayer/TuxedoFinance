# `dashboard`

Three screens over the same data: the **index** (six aggregate indicators, a forward-looking outlook table, and a recent-transactions list), **reports** (six charts of how the account evolves over a year — the time-series line + cash-flow bars share a 12-month window, two payment-method breakdowns and a category breakdown each have their own scoped filter, and a donut chart splits the month's expenses by recurrence), and the per-method **category breakdown** that opens inline on the reports page when a bar in charts 3 or 4 is clicked. The index is `LOGIN_REDIRECT_URL` — the first screen every user sees after signing up or logging in.

Both the index and reports are a **forecast**, not a report of the past: the month the index shows can be navigated forward, and fixed transactions and open installment plans recur into those future months automatically. The reports page exposes the same `?month=YYYY-MM` mechanic as before, plus `?charts_offset=N` to slide the 12-month time-series window, `?payment_month=ALL|YYYY-MM` to scope both payment-method charts at once, `?expense_method=NAME` / `?income_method=NAME` to open each inline method-categories drill-down (charts 3 and 4 respectively), `?category_month=ALL|YYYY-MM` to scope the "where the money goes" chart, and `?installment_month=ALL|YYYY-MM` to scope the recurrence donut (defaults to the current month, unlike the others which default to `ALL`).

## Files

| File | Contents |
|---|---|
| `dashboard/services.py` | `get_dashboard_summary(user, year, month)`, `get_account_evolution(user, offset=0)`, `get_expenses_by_payment_method(user, year=None, month=None, months=1)`, `get_expenses_by_category_for_method(user, method_name, year, month, months)`, `get_income_by_payment_method(user, year=None, month=None, months=1)`, `get_income_by_category_for_method(user, method_name, year, month, months)`, `get_expenses_by_recurrence(user, year=None, month=None, months=1)`, `add_months()`, `OUTLOOK_MONTHS`, `EVOLUTION_MONTHS`, `ALL_TIME_MONTHS` |
| `dashboard/charts.py` | `build_line_chart()`, `build_bar_chart()`, `build_sparkline()`, `build_donut_chart()` — SVG geometry only |
| `dashboard/views.py` | `DashboardIndexView`, `DashboardReportsView`; helpers `_selected_month`, `_is_representable`, `_is_projectable`, `_is_offset_window_safe`, `_month_choices`, `_parse_month_or_all`, `_parse_charts_offset` |
| `dashboard/urls.py` | `app_name = 'dashboard'`; routes `index`, `reports` |
| `dashboard/models.py` | empty — this app has no data of its own, only aggregates `Transaction` |
| `dashboard/admin.py` | empty |
| `templates/dashboard/{index,reports}.html` | the screens |
| `templates/dashboard/_reports_charts.html` | the HTMX-swapped partial that owns the six report charts; the view returns the full `reports.html` on a plain GET and this partial alone when the request is an HTMX swap so the navbar and outer wrapper are not re-rendered |

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
def _projection_queryset(user, with_category=False, with_payment_method=False):
    fields = [
        'transaction_type', 'amount', 'installments',
        'is_fixed', 'fixed_until', 'transaction_date',
        'payment_method__method_type',
        'payment_method__best_purchase_day', 'payment_method__due_day',
    ]
    queryset = Transaction.objects.filter(user=user).select_related('payment_method')

    if with_category:
        queryset = queryset.select_related('category')
        fields.append('category__name')

    if with_payment_method:
        fields.append('payment_method__name')

    return queryset.only(*fields)
```

- Still **one database round-trip** per dashboard render, regardless of how many months the outlook spans — the deferred `.only()` keeps it to the columns the arithmetic actually needs, and the joins add columns to that single query rather than queries of their own.
- **That column list is load-bearing, not an optimization detail.** Anything `amount_for_month` / `amount_through_month` reads must appear in it: a field left out is *deferred*, and touching it later silently costs one extra query **per row**, turning the single round-trip into an N+1 (NFR10). `fixed_until` belongs there for exactly this reason even though no screen displays it.
- **The `payment_method` join is unconditional** for the same reason. `months_from_start` asks the card which month a purchase is billed in ([billing cycle](../data-model.md#billing-cycle-when-a-card-purchase-actually-leaves-the-account)), so `method_type` and `best_purchase_day` are read for *every* transaction on *every* dashboard page (`due_day` moves no money but rides along for free, and the transaction list renders it). Dropping the join would not change a single number on screen — it would quietly multiply the query count by the size of the transaction list. `with_payment_method` therefore only adds the method's **name**, for the breakdown chart's labels.
- What it gives up versus the old pure-SQL version is that work now scales with the user's transaction count in Python rather than in SQLite. For a personal finance app that is the right trade: correctness of the forecast is the entire feature, and the row counts are in the thousands at most. If a user's history ever made this slow, the fix is to cache the fold or snapshot closed months — not to go back to `Sum(filter=...)`, which cannot express recurrence at all.
- `_totals(...)` folds once per month; the outlook's running balance is accumulated month-to-month rather than recomputing a cumulative fold per row, so the whole outlook costs `OUTLOOK_MONTHS + 2` passes over an in-memory list.

### Other deliberate choices

- **`ZERO = Decimal('0.00')`** everywhere, matching the model's `DecimalField` precision — the fold starts from `ZERO`, so a user with no investments gets `0.00`, never `None`.
- **`transaction_date`**, never `created_at` — see [data-model.md § Date semantics](../data-model.md#date-semantics). `timezone.localdate()` (not `date.today()`) respects `USE_TZ`/`TIME_ZONE`.
- **Every balance subtracts Investment** — the one place in the codebase that encodes the PRD §8.5 decision that Investment is a cash outflow, while keeping it out of the Expenses indicator.
- **`add_months(year, month, offset)`** does month arithmetic through an absolute month index (`year * 12 + month - 1`), so year boundaries and negative offsets fall out for free instead of needing special cases.
- Callers **must** pass the actual logged-in user — there is no "aggregate everyone" mode, by design (PRD R3).

## `get_account_evolution(user, offset=0)` (`dashboard/services.py`)

The series behind the reports page (FR16): `EVOLUTION_MONTHS` (12) consecutive months anchored on `today + offset` whole months — `EVOLUTION_PAST_MONTHS` (5) of history, the (shifted) anchor month, and the rest projected forward. The `offset` parameter is what the prev/next arrows on charts 1 and 2 drive (`?charts_offset=N`): the whole 12-month window slides through time as the user clicks.

| Key | Meaning |
|---|---|
| `months` | One row per month: `date`, `is_current_month` (relative to the shifted anchor), `is_future` (relative to the same anchor), the three type totals, `balance`, and `closing_balance` (the running balance at that month's end). |
| `current_month` | The row for the (shifted) anchor month — so templates never index `months` by a hardcoded offset. |
| `anchor_year` / `anchor_month` / `anchor_date` | The (shifted) "today" of the window — the label the chart titles use. |
| `is_anchored_today` | True iff `offset == 0`. Drives the "Anchored on today / Past window / Future window" badge and the "Back to today" link. |
| `opening_balance` / `closing_balance` | Where the account stood entering the window, and where it is projected to end. |
| `net_change` | `closing − opening`: the one number that says whether the account is growing. |
| `best_month` / `worst_month` | Rows with the highest/lowest **net** (`balance`), not the highest income. |
| `expenses_by_category` | Up to `TOP_CATEGORIES` (6) rows for the same 12-month window: `name`, `total`, `bar_width`, `share`. |

History and forecast share one continuous series on purpose. A hard seam between "real" and "projected" months would only be visual noise — the template marks which is which (dimmer markers, a `(projected)` tooltip suffix) instead of splitting the chart. The `is_current_month` and `is_future` flags follow the shifted anchor, so the same week of 2025 rendered with `offset=-12` still labels its months correctly.

Two details worth knowing:

- **The opening balance is one cumulative fold, not one per month.** `_totals(..., cumulative=True)` runs once for the month *before* the window; every rendered month then just adds its own net. Twelve cumulative folds would have been the obvious implementation and twelve times the work.
- **`_expenses_by_category` counts recurrences**, so a fixed R$ 50 rent appears as R$ 600 across the year, not R$ 50. It covers Expense only — Income has no category breakdown worth showing, and Investment is deliberately excluded so the chart answers "where does my *spending* go", consistent with §8.5 keeping the two outflows distinct everywhere else.
- `bar_width` is a percentage of the **largest** category (so the top bar always fills its track), while `share` is a percentage of **all** spending. The two exist because a bar sized by share would leave the chart nearly empty whenever spending is evenly spread.

`_projection_queryset(user, with_category=True)` adds `select_related('category')` and `category__name` to the deferred column list, so the breakdown reads `category.name` per row without an N+1. The whole function is **one query**, as is `get_dashboard_summary`.

## `get_expenses_by_payment_method(user, year=None, month=None, months=1)` (`dashboard/services.py`)

The fourth chart on the reports page: expenses split across the payment methods that paid for them, over a **window** the caller picks.

| Key | Meaning |
|---|---|
| `methods` | Up to `TOP_PAYMENT_METHODS` (8) rows, biggest first: `name`, `total`, `share`. |
| `total` | Every method's spending in the window, **including** any the cap trimmed. |
| `shown` / `used` | Rows charted vs. methods actually used. `shown < used` means the drawn shares stop short of 100%, and the template says so. |

Two scopes, picked by the caller:

- The default — `(year, month)` set, `months=1` — answers the single-month question "July went on which card?", asked one statement cycle at a time. This is what `?payment_month=2026-07` triggers.
- `(year=None, month=None, months=N)` aggregates the last `N` months anchored on today, so `?payment_month=ALL` (the new default) can answer "where does my spending go, in aggregate?" without losing the per-method resolution.

Recurrences count, on the same `amount_for_month` rules as everything else: a fixed subscription and the current slice of an installment plan both land on every month they actually pay, not on the month they were first recorded. **Expense only**, like `_expenses_by_category` — income arrives independently of how anything is paid, and Investment stays a distinct outflow (PRD §8.5). Grouping by **name** is safe because `unique_payment_method_per_user` makes it unique within a user; the aggregation never crosses users, since the queryset starts from `user=user` (PRD R3). `TOP_PAYMENT_METHODS` (8) is higher than `TOP_CATEGORIES` (6) because these bars are vertical: the ceiling is how many axis labels fit side by side, not how tall the card grows.

`_projection_queryset(user, with_payment_method=True)` joins `payment_method__name` the same way the category breakdown joins its own — **one query**. The reports page therefore costs **two** transaction queries in total (this one plus `get_account_evolution`), because the two cover different windows: folding both from one fetch would couple two independent services to save a query that SQLite answers from the same page cache.

## `get_expenses_by_category_for_method(user, method_name, year, month, months)` (`dashboard/services.py`)

The "you clicked a bar" follow-up: same shape as `_expenses_by_category`, but filtered to a single payment method first. Drives the inline `method-categories` panel that opens on the reports page when `?expense_method=NAME` is set on chart 3 (spending); the income equivalent (`get_income_by_category_for_method` / `?income_method=NAME` on chart 4) reuses the same shape.

Same rules as every other breakdown:

- Expenses only (income / investment are out by §8.5).
- Recurrences count via `amount_for_month`, so a fixed subscription on a credit card shows under every month it charges.
- The window is a single month when `year`/`month` are set, or the last `months` months from today when they are `None` (the `?payment_month=ALL` case).
- `TOP_CATEGORIES` (6) cap, same dual-percent convention as `_expenses_by_category` (`bar_width` relative to the biggest, `share` of all spending on this method).

Returns an empty list when the method had no expenses in the window, or when `method_name` is not one of the user's methods — the view treats both as "no data to show" without differentiating.

## `get_expenses_by_recurrence(user, year=None, month=None, months=1)` (`dashboard/services.py`)

The sixth chart on the reports page: expenses split into three buckets by how they recur, answering "how much of *this* month's outflow is from parcels I bought before".

Three mutually exclusive buckets, partitioned by the same `TransactionForm.clean` flags the rest of the app uses:

- **installment** — `is_installment_plan=True`: a purchase split into `installments > 1` months.
- **fixed** — `is_fixed=True`: a transaction that repeats every month until `fixed_until`.
- **one-off** — everything else, paid in a single shot.

| Key | Meaning |
|---|---|
| `total` | Sum of all three buckets for the window — the figure printed at the center of the donut. |
| `slices` | Always three entries in fixed order `installment, fixed, one_off`, so the legend doesn't reshuffle when the picked month changes. Each carries `name`, `tone`, `value`, `share` (0–100, rounded to one decimal), and a `draw` boolean — `False` for a bucket that is zero in the window, so it stays in the legend but is skipped when building the ring (`build_donut_chart` would otherwise paint a zero-width arc that the SVG renderer silently drops anyway, but the skip keeps the path list minimal). |

Like every other breakdown, it folds `Transaction.amount_for_month` over each transaction in the window, so a 3× plan of R$100 contributes `33.33` to the installment bucket on each of its three months — not the full `100` once. Investment stays out (PRD §8.5 keeps that outflow distinct from Expenses). The view filters `draw=True` before passing the slices to `build_donut_chart`, so an empty month yields `recurrence_chart=None` and the template renders its `empty_state` partial instead of a blank ring.

Two scopes, picked by the caller, identical to `get_expenses_by_payment_method`:

- `year`/`month` set, `months=1` — the single specific month the user picked (`?installment_month=2026-08`). This is the default view: the filter defaults to the current month, **not** to `ALL`, because the chart's job is "how much of *this* month is on installments" — a fresh visit should land on the month the user is actually in, not on a 12-month aggregate.
- `year=None, month=None, months=N` — the last `N` months anchored on today, which is what the `All time` filter option maps to (`?installment_month=ALL` resolves to `ALL_TIME_MONTHS`).

The rounding remainder is absorbed into the last **drawn** slice, mirroring `Transaction.amount_for_month`'s "the missing penny goes to the last one" policy — so the printed shares always add up to 100.0 and the ring closes exactly at 360° (see `build_donut_chart` below).

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
- **Tones, not colors.** `build_bar_chart` and `build_donut_chart` take semantic `tone` values (`'income'`/`'expense'`/`'investment'`, and `'installment'`/`'fixed'`/`'one_off'` for the donut) and the template maps them to Tailwind classes, so design tokens stay in the template layer with every other color decision ([frontend.md](../frontend.md)).
- **Labels pass through untouched.** `DashboardReportsView` hands the whole month row in as the label, so the template reads `point.label.date` and `point.label.is_current_month` off each point instead of zipping two lists in the template. The payment-method chart uses the same trick with its own rows, reading `group.label.name` / `group.label.share`.
- **Each bar carries a `value_y`**, a baseline `VALUE_LABEL_OFFSET` above its top. Only the single-series chart has the room to print a caption there, but the geometry belongs here — DTL cannot subtract, and `{{ bar.y|add:"-6" }}` silently renders empty on a float.
- **`build_bar_chart` needs at least one label.** With none it would divide the plot into zero slots; callers with nothing to draw have an empty state to render instead, which is why `DashboardReportsView` passes `payment_chart=None` for a month with no expenses.

### `build_donut_chart(slices)`

The geometry behind chart 6 (`get_expenses_by_recurrence`). Same "pure geometry, no money/Django knowledge" contract as the line and bar builders, but for a donut/ring instead of a Cartesian chart.

- **Constants**: `DONUT_SIZE=320`, `DONUT_PADDING=28`, `DONUT_STROKE=38`. Ring radius is `(size − 2·padding − stroke) / 2`; inner radius is `radius − stroke`. The whole canvas is sized so the ring plus a one-line text block at the center fits without clipping.
- **Ring starts at 12 o'clock (−90°).** Slices are placed clockwise in the **order the caller passes them** — `get_expenses_by_recurrence` always sends them `installment, fixed, one_off`, so the ring doesn't reshuffle when the picked month changes (the donut is read by position as much as by color, and a stable order keeps cross-month comparison honest).
- **The last slice absorbs the rounding remainder** so the ring closes exactly at 360°: instead of computing its sweep from its own `share`, the builder assigns it `270 − start_angle` (the angle from the current cursor back to +270°, which is −90° plus one full turn). This is the same "missing penny goes to the last one" policy the model applies to the final installment. Earlier slices' `share` values sum-cumulatively may total 99.9 or 100.1 because of `round(..., 1)` rounding, and the last slice quietly swallows the slack so the printed legend always reads 100.0 total **and** the SVG path actually closes — the two goals cannot be served independently without splitting the rounding-rest logic across two places, so it lives here.
- **The full-ring case is split into two semicircle arcs.** When the last slice is also the *only* drawn slice (a single bucket covering 100%), `sweep ≥ 359.999` and `start == end`, which the SVG `A` command cannot draw — it needs two distinct endpoints. The builder halves the sweep at the midpoint (start_angle + 180°, which lands at the bottom of the ring) and emits two `A` commands per radius, so the path renders a complete ring instead of nothing. The same branch fires when the rounding-remainder slice happens to round up to the full 360°.
- **Empty input returns `segments: []`.** An empty month's `recurrence_chart` therefore becomes `None` at the view level (the template checks `{% if recurrence_chart %}`), so the empty state renders instead of a blank donut SVG.

### `build_sparkline(labels, values)`

A tiny inline line chart (constants `SPARK_WIDTH=120` / `SPARK_HEIGHT=40` / `SPARK_PADDING=4`), used where a full chart would be too heavy — same `_bounds`-anchored y-axis as the big line chart, only without axis labels, grid, or markers. Pure geometry like every other builder here.

## View (`DashboardReportsView`)

A `TemplateView` that composes the six charts on the page. Everything else it does is composition — the finance math is in `services.py`, the pixel math in `charts.py`, and the view is the only place that knows both exist.

On an HTMX-driven swap (any `hx-get` interaction from inside the charts partial) it returns `templates/dashboard/_reports_charts.html` alone so the navbar and outer wrapper are not re-rendered; on a plain GET it returns the full `reports.html`. The partial owns the six SVG charts and every interactive control on the page, and every control carries both an `hx-*` wiring and a plain `href`/`action` no-JS fallback, in line with the rest of the project.

It reads **five independent query params** off `request.GET`, all with the same forgiving contract (malformed → silently fall back to the default rather than raise a 400):

| Param | Default | Bounded by | Drives |
|---|---|---|---|
| `?charts_offset=N` | `0` | `_is_offset_window_safe` (the whole 12-month window around `today + N` must be representable) | The anchor of charts 1 and 2's time-series window. |
| `?payment_month=ALL\|YYYY-MM` | `ALL` | `_is_representable` | Which month (or all of them) charts 3 and 4 fold — the two payment-method breakdowns share one window on purpose. |
| `?expense_method=NAME` | unset | validated against `expense_breakdown['methods']` (stale URLs cannot surface an empty panel) | Opens the inline "categories for this method" panel below chart 3 (spending). |
| `?income_method=NAME` | unset | validated against `income_breakdown['methods']` | Opens the inline "categories for this method" panel below chart 4 (income). |
| `?category_month=ALL\|YYYY-MM` | `ALL` | `_is_representable` | Which month (or all of them) the "where the money goes" chart (5) folds. |
| `?installment_month=ALL\|YYYY-MM` | **current month** | `_is_representable` | Which month (or all of them) the recurrence donut (chart 6) folds. Defaults to the current month, not `ALL`, because the chart answers "how much of *this* month is on installments". Parsed by the view's own `get_installment_month` method, which is the only param here that does not reuse `_parse_month_or_all` directly — it intercepts the empty param first and returns today's `YYYY-MM` before handing off to the shared parser. |

`_is_offset_window_safe` is the new bounds check the prev/next arrows need: the 12-month window around `today + offset` walks from `anchor − 5` to `anchor + 6`, and both extremes have to be representable as `date(year, month, 1)` so the chart's axis labels don't crash `date()` from inside the service. It mirrors the existing `_is_projectable` pattern on the index (same reasoning, smaller window).

The params **do not interact**: a user can offset the time-series window by 2 months while keeping the breakdown chart scoped to March 2026 and the recurrence donut to July 2026, and clicking a bar in chart 3 preserves every active filter. The template uses `{% querystring %}` everywhere so any one of them survives navigation to any other.

When `?expense_method=NAME` matches a method in the current spending breakdown, the view computes `expense_method_categories` (top categories for that method in the same window chart 3 is showing) and surfaces it in the inline panel below chart 3. `?income_method=NAME` does the same on the income side against chart 4, validated against the income breakdown so a stale URL cannot open a panel for a method that isn't on the chart it was clicked from. If `?payment_month=ALL`, both panels anchor on the current month — otherwise they follow the chosen month. A missing param, an unknown name, or a name from a stale URL is silently ignored and the panel stays hidden.

Chart 6 (`get_installment_month` / `recurrence_breakdown` / `recurrence_chart`) lives in the same partial. The view always computes the recurrence breakdown for the resolved window — even when all three buckets are zero — so the legend keeps rendering all three entries with `share=0`. `recurrence_chart` is set to `None` only when `recurrence_breakdown['slices']` itself is empty (`get_expenses_by_recurrence` returns `{'slices': []}` for a window with no expenses at all), at which point the template renders the `empty_state.html` partial instead of a blank SVG.

## Template (`templates/dashboard/_reports_charts.html`)

Six charts, all server-rendered, with no charting library or client-side SVG geometry. The partial itself contains no `<script>`; the shared `base.html` provides the narrow HTMX/theme/viewport helpers. The partial is swapped in by HTMX (`outerHTML` on `#reports-charts`) on every interactive click; the same controls also carry plain `href`/`action` fallbacks so the page still works without JavaScript. When HTMX is active, the shared lifecycle handler preserves the current scroll position and focused filter across the swap.

1. **Balance evolution** — an SVG `<polyline>` over a gradient-filled `<polygon>`, with one `<circle>` marker per month. Future months get a dimmer stroke. The **zero line is dashed rose** (`stroke-rose-400 dark:stroke-rose-500`, `stroke-width="1.5"`, `stroke-dasharray="5 4"`) rather than the muted slate of the rest of the grid, so a balance crossing zero reads at a glance instead of blending into the axis.
2. **Monthly cash flow** — grouped `<rect>` bars, three per month (emerald/rose/amber per PRD §9.1), with a legend.
3. **Spending by payment method** — one rose `<rect>` per method for the selected window, its share printed above it and its full name + amount listed underneath. **Each bar is a hyperlink** to `?expense_method={name}#method-categories` — the project is zero-JS, so the click-driven drill-down is a plain `<a>` rather than a JS popover.
4. **Income by payment method** — the same bar layout as chart 3, opposite direction of cash (emerald). Each bar hyperlinks to `?income_method={name}#method-categories` and opens its own inline panel below; the two drill-downs are independent so the user can have one open on each side at the same window.
5. **Where the money goes** — plain CSS bars (`style="width: {{ category.bar_width|unlocalize }}%"`), no SVG needed.
6. **How much is on installments** — a `<svg>` donut built by `build_donut_chart`, with the total printed at the center and a three-row legend below (`Installments` rose, `Fixed` indigo, `One-off` slate). The filter form lives in the card header and submits `?installment_month=`; the default the form preselects is the current month (`ALL` is still selectable for the wider view). When the window has no expenses at all, the entire SVG card is replaced by `partials/empty_state.html`.

Tooltips are native SVG `<title>` elements: browsers show them on hover with no JavaScript. Every SVG sits in an `overflow-x-auto` wrapper with a `min-w-[44rem]` canvas — on a phone the chart scrolls inside its own card instead of shrinking its axis labels into illegibility (same convention as the outlook table).

**Charts 1 and 2 — `←` / `→` time-series navigation.** A small `←` / `→` pair sits in the header of each card, anchored on the time-series window label (`"May 2026 – Apr 2027"`). A `"Back to today"` link appears whenever the window is not anchored on the current month, and a badge shows `"Anchored on today"` / `"Past window"` / `"Future window"`. The arrows use `{% querystring charts_offset=… %}` so any other active filter (category_month, payment_month, expense_method, income_method, installment_month) survives the click.

**Charts 3 and 4 — shared `All time` + month select.** The two payment-method breakdowns share **one** `<form method="get">` with a `<select>` for `?payment_month=`, because the two charts answer mirror-image questions over the same window — splitting the filter would force the user to keep two independent dropdowns in sync. `month_choices` is `[("ALL", "All time")]` plus the last 12 months from today. The default is `ALL` (a 12-month aggregate), which gives a quick "where does my money go overall" answer; picking a specific month scopes both charts at once on the same `amount_for_month` rules as before. The form is a plain `Filter` submit — no `onchange` auto-submit, in line with the rest of the project.

**Charts 3 and 4 — `method-categories` panels.** When `?expense_method=NAME` (or `?income_method=NAME`) is valid, an additional card renders **below** the chart that owns that param, with the same CSS-bar layout as chart 5 but filtered to the chosen method in the same window. A `"Close"` link in the panel header strips the param while preserving every other active filter. The `<title>` SVG tooltips still include the name + total + share of the window, so the drill-down is the only thing the click adds on top of the hover.

**Chart 6 — recurrence donut.** No arrows, no drill-down. The single `<form>` in its header submits `?installment_month=ALL|YYYY-MM`, defaulting to the current month (the only filter on the page that does *not* default to `ALL`). The donut itself is one `<path>` per drawn slice, plus a centered `<text>` block with the window's total expense — readable without the legend if the user just wants the headline number. Legend swatches use the same `tone` → Tailwind class mapping as the bars (`fill-rose-500 dark:fill-rose-400`, `fill-indigo-500 dark:fill-indigo-400`, `fill-slate-500 dark:fill-slate-400`), so the chart's color vocabulary stays consistent with the rest of the partial.

Two details in charts 3 and 4 are load-bearing:

- **Axis labels are truncated** (`truncatechars:expense_chart.label_chars` / `income_chart.label_chars`) — at the 8-method cap each slot is ~80px wide, and untruncated names would collide. The list under the chart always spells them out, which also makes the numbers readable on touch devices, where a `<title>` tooltip never appears.
- **Shares are printed above the bars**, not only in the tooltips, so "how is it distributed" is answerable without hovering.

## View (`DashboardIndexView`)

```python
def _selected_month(request, in_range):
    """Parse `?month=YYYY-MM` off `request`, falling back to the current month."""
    today = timezone.localdate()
    year_part, _, month_part = request.GET.get('month', '').partition('-')

    if year_part.isdigit() and month_part.isdigit():
        year, month = int(year_part), int(month_part)
        if 1 <= month <= 12 and in_range(year, month):
            return year, month

    return today.year, today.month
```

Month selection is a plain `?month=YYYY-MM` GET param — the same zero-JS convention as the transaction list's filter, and the same forgiving behavior: a malformed or out-of-range value silently falls back to the current month rather than raising a `400`. The bounds check matters because `selected_month_date` builds a real `datetime.date`, which would raise `ValueError` on month `13` or year `99999`.

Both screens share the parse and differ only in `in_range`, because they build different windows around the month:

```python
def _is_projectable(year, month):
    """True when the whole dashboard window around (year, month) is representable."""
    earliest_year, _ = add_months(year, month, -1)
    latest_year, _ = add_months(year, month, OUTLOOK_MONTHS - 1)
    return date.min.year <= earliest_year and latest_year <= date.max.year
```

Checking that the *selected* month is in range is not enough on the index: `?month=9999-12` passes that test, and then the outlook walks into year 10000 and `date()` raises `ValueError` from inside the service — a 500 triggered purely by a query string. The reports page projects nothing off the selected month on its own, so it uses the laxer `_is_representable` — but its `?charts_offset` uses a similar bounds check (`_is_offset_window_safe`) for the same reason.

The view also precomputes `previous_month_param` / `next_month_param` (`YYYY-MM` strings) so the template's navigation links stay dumb.

It is a `TemplateView`, not a `ListView` — the "list" here (recent transactions) is a secondary, capped slice (`RECENT_TRANSACTIONS_LIMIT = 5`), not the primary paginated resource (that's `transactions:list`). `select_related` avoids N+1 queries when rendering each recent transaction's category/payment method name.

`_recent_transactions(user, year, month)` scopes that slice to the **selected** month, on the same `amount_for_month` rule as the stat cards above it (§8.5) — a fixed subscription or the live slice of an installment plan shows up here too, not only in the month it was first recorded, and a credit-card purchase appears under the month its bill actually lands in, not its purchase date. That recurrence rule cannot be expressed as a SQL predicate (same reason as `get_dashboard_summary`), so it fetches the user's transactions, folds them in Python, and slices the first `RECENT_TRANSACTIONS_LIMIT` — still one query. Without this, the widget used to show the user's most recent transactions **overall**, independent of which month the rest of the screen was showing — confusing next to stat cards that do change with `?month=`.

## Routes

| Path | Name | View |
|---|---|---|
| `/dashboard/` | `dashboard:index` | `DashboardIndexView` (supports `?month=YYYY-MM`) |
| `/dashboard/reports/` | `dashboard:reports` | `DashboardReportsView` (supports `?charts_offset=N`, `?category_month=ALL\|YYYY-MM`, `?payment_month=ALL\|YYYY-MM`, `?expense_method=NAME`, `?income_method=NAME`, `?installment_month=ALL\|YYYY-MM`) |

`settings.LOGIN_REDIRECT_URL = 'dashboard:index'` — this is where both `LoginView` and `SignupView` send the user on success.

On the index, `?month=` moves the whole screen. On reports it has a different meaning per chart: the time-series charts move only via `?charts_offset` (a *shift* of the window, not a re-anchor); the two payment-method charts share `?payment_month` (each opens its own drill-down via `?expense_method` / `?income_method`); the category breakdown has its own `?category_month`; and the recurrence donut defaults to the current month under `?installment_month`. Mixing them is fine — `{% querystring %}` preserves whichever ones the user has set when they click any of the others.

## Template (`templates/dashboard/index.html`)

- A `New Transaction` button (linking to `transactions:create`), prominent per PRD 7.2.4.
- A **month navigation bar**: `←` / `→` links to the adjacent months, the selected month's name, a "Current month / Projection / Past month" label, and a "Back to this month" link whenever the user has navigated away. All plain `<a href>` — no JS.
- Six `partials/stat_card.html` includes in a `sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6` grid: **Current Balance** (neutral tone — no single semantic color owns a net figure that can be positive or negative), **Income (month)** (emerald), **Expenses (month)** (rose), **Investments (month)** (amber), **Balance (month)** (neutral), **Projected (end of month)** (neutral). Values are pre-formatted with `floatformat:2` and prefixed with `{{ CURRENCY_SYMBOL }}` before being passed into the partial — `stat_card.html` itself has no currency logic (see [frontend.md](../frontend.md)).
- An **Outlook table** — one row per upcoming month with Income / Expenses / Investments / Net / running projected balance. The selected row is tinted, the current month carries a `Now` badge, and negative figures turn rose. It sits in an `overflow-x-auto` wrapper with `min-w-[40rem]` so it scrolls inside its own container on mobile instead of forcing the page to scroll sideways.
- A "Recent transactions" list (up to 5 rows billed in the **selected** month, same color-coded `+`/`−` treatment as `transactions/list.html`), or `partials/empty_state.html` if nothing bills in that month.
