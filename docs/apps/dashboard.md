# `dashboard`

Two screens over the same data: the **index** (six aggregate indicators, a forward-looking outlook table, and a recent-transactions list) and **reports** (charts of how the account evolves over a year, plus a per-month breakdown of which payment method paid for what). The index is `LOGIN_REDIRECT_URL` — the first screen every user sees after signing up or logging in.

Both are a **forecast**, not a report of the past: the month the index shows can be navigated forward, and fixed transactions and open installment plans recur into those future months automatically.

## Files

| File | Contents |
|---|---|
| `dashboard/services.py` | `get_dashboard_summary(user, year, month)`, `get_account_evolution(user)`, `get_expenses_by_payment_method(user, year, month)`, `add_months()`, `OUTLOOK_MONTHS`, `EVOLUTION_MONTHS` |
| `dashboard/charts.py` | `build_line_chart()`, `build_bar_chart()` — SVG geometry only |
| `dashboard/views.py` | `DashboardIndexView`, `DashboardReportsView` |
| `dashboard/urls.py` | `app_name = 'dashboard'`; routes `index`, `reports` |
| `dashboard/models.py` | empty — this app has no data of its own, only aggregates `Transaction` |
| `dashboard/admin.py` | empty |
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

`_projection_queryset(user, with_category=True)` adds `select_related('category')` and `category__name` to the deferred column list, so the breakdown reads `category.name` per row without an N+1. The whole function is **one query**, as is `get_dashboard_summary`.

## `get_expenses_by_payment_method(user, year, month)` (`dashboard/services.py`)

The fourth chart on the reports page: **one month's** expenses split across the payment methods that paid for them.

| Key | Meaning |
|---|---|
| `methods` | Up to `TOP_PAYMENT_METHODS` (8) rows, biggest first: `name`, `total`, `share`. |
| `total` | Every method's spending that month, **including** any the cap trimmed. |
| `shown` / `used` | Rows charted vs. methods actually used. `shown < used` means the drawn shares stop short of 100%, and the template says so. |

- **A single month, deliberately** — the rest of the page spans 12 months. "July went on which card?" is asked one statement cycle at a time, and averaging it over a year blurs exactly the detail being looked for. This is the only part of the page `?month=` moves.
- **Recurrences count**, on the same `amount_for_month` rules as everything else: a fixed subscription and the current slice of an installment plan both land on the month they are actually paid, not on the month they were recorded.
- **Expense only**, like `_expenses_by_category` — income arrives independently of how anything is paid, and Investment stays a distinct outflow (PRD §8.5).
- Grouping by **name** is safe because `unique_payment_method_per_user` makes it unique within a user; the aggregation never crosses users, since the queryset starts from `user=user` (PRD R3).
- `TOP_PAYMENT_METHODS` (8) is higher than `TOP_CATEGORIES` (6) because these bars are vertical: the ceiling is how many axis labels fit side by side, not how tall the card grows.

`_projection_queryset(user, with_payment_method=True)` joins `payment_method__name` the same way the category breakdown joins its own — **one query**. The reports page therefore costs **two** transaction queries in total (this one plus `get_account_evolution`), because the two cover different windows: folding both from one fetch would couple two independent services to save a query that SQLite answers from the same page cache.

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
- **Labels pass through untouched.** `DashboardReportsView` hands the whole month row in as the label, so the template reads `point.label.date` and `point.label.is_current_month` off each point instead of zipping two lists in the template. The payment-method chart uses the same trick with its own rows, reading `group.label.name` / `group.label.share`.
- **Each bar carries a `value_y`**, a baseline `VALUE_LABEL_OFFSET` above its top. Only the single-series chart has the room to print a caption there, but the geometry belongs here — DTL cannot subtract, and `{{ bar.y|add:"-6" }}` silently renders empty on a float.
- **`build_bar_chart` needs at least one label.** With none it would divide the plot into zero slots; callers with nothing to draw have an empty state to render instead, which is why `DashboardReportsView` passes `payment_chart=None` for a month with no expenses.

## View (`DashboardReportsView`)

A `TemplateView` that calls `get_account_evolution()` once and feeds the same 12 rows into both chart builders, then `get_expenses_by_payment_method()` for the selected month. Everything else it does is composition — the finance math is in `services.py`, the pixel math in `charts.py`, and the view is the only place that knows both exist.

It reads `?month=YYYY-MM` through the same `_selected_month()` helper as the index, but with a laxer bound: `_is_representable` only requires that `date(year, month, 1)` can be built for the label, because nothing here projects a window off the selected month (that is what `_is_projectable` guards on the index). **The month moves the payment-method chart only** — the other three stay anchored on today by construction, since they are about the shape of the account over time and re-anchoring them would ask a different question than the page exists to answer.

## Template (`templates/dashboard/reports.html`)

Four charts, all server-rendered, no `<script>` anywhere on the page:

1. **Balance evolution** — an SVG `<polyline>` over a gradient-filled `<polygon>`, with a dashed zero line and one `<circle>` marker per month. Future months get a dimmer stroke.
2. **Monthly cash flow** — grouped `<rect>` bars, three per month (emerald/rose/amber per PRD §9.1), with a legend.
3. **Where the money goes** — plain CSS bars (`style="width: {{ category.bar_width }}%"`), no SVG needed.
4. **Spending by payment method** — one rose `<rect>` per method for the selected month, its share printed above it and its full name + amount listed underneath.

Tooltips are native SVG `<title>` elements: browsers show them on hover with no JavaScript. Every SVG sits in an `overflow-x-auto` wrapper with a `min-w-[44rem]` canvas — on a phone the chart scrolls inside its own card instead of shrinking its axis labels into illegibility (same convention as the outlook table).

Chart 4 is the only one with a control, and its `<form method="get">` sits **inside that card** rather than in the page header: a filter at the top would look like it moves all four charts. It posts back to `#payment-methods` so submitting returns the reader to the chart they just filtered. Two details in it are load-bearing:

- **Axis labels are truncated** (`truncatechars:14`) — at the 8-method cap each slot is ~80px wide, and untruncated names would collide. The list under the chart always spells them out, which also makes the numbers readable on touch devices, where a `<title>` tooltip never appears.
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

Checking that the *selected* month is in range is not enough on the index: `?month=9999-12` passes that test, and then the outlook walks into year 10000 and `date()` raises `ValueError` from inside the service — a 500 triggered purely by a query string. The reports page projects nothing off the selected month, so it uses the laxer `_is_representable`.

The view also precomputes `previous_month_param` / `next_month_param` (`YYYY-MM` strings) so the template's navigation links stay dumb.

It is a `TemplateView`, not a `ListView` — the "list" here (recent transactions) is a secondary, capped slice (`RECENT_TRANSACTIONS_LIMIT = 5`), not the primary paginated resource (that's `transactions:list`). `select_related` avoids N+1 queries when rendering each recent transaction's category/payment method name.

## Routes

| Path | Name | View |
|---|---|---|
| `/dashboard/` | `dashboard:index` | `DashboardIndexView` (supports `?month=YYYY-MM`) |
| `/dashboard/reports/` | `dashboard:reports` | `DashboardReportsView` (supports `?month=YYYY-MM`, payment-method chart only) |

`settings.LOGIN_REDIRECT_URL = 'dashboard:index'` — this is where both `LoginView` and `SignupView` send the user on success.

`?month=` means something narrower on reports than on the index. On the index it moves the whole screen; on reports it moves **only** the payment-method breakdown, because the other three charts are windows relative to today by construction — re-anchoring them on a picked month would just be a second, subtly different way to ask what the index already answers.

## Template (`templates/dashboard/index.html`)

- A `New Transaction` button (linking to `transactions:create`), prominent per PRD 7.2.4.
- A **month navigation bar**: `←` / `→` links to the adjacent months, the selected month's name, a "Current month / Projection / Past month" label, and a "Back to this month" link whenever the user has navigated away. All plain `<a href>` — no JS.
- Six `partials/stat_card.html` includes in a `sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6` grid: **Current Balance** (neutral tone — no single semantic color owns a net figure that can be positive or negative), **Income (month)** (emerald), **Expenses (month)** (rose), **Investments (month)** (amber), **Balance (month)** (neutral), **Projected (end of month)** (neutral). Values are pre-formatted with `floatformat:2` and prefixed with `{{ CURRENCY_SYMBOL }}` before being passed into the partial — `stat_card.html` itself has no currency logic (see [frontend.md](../frontend.md)).
- An **Outlook table** — one row per upcoming month with Income / Expenses / Investments / Net / running projected balance. The selected row is tinted, the current month carries a `Now` badge, and negative figures turn rose. It sits in an `overflow-x-auto` wrapper with `min-w-[40rem]` so it scrolls inside its own container on mobile instead of forcing the page to scroll sideways.
- A "Recent transactions" list (up to 5 rows, same color-coded `+`/`−` treatment as `transactions/list.html`), or `partials/empty_state.html` if the user has never recorded one.
