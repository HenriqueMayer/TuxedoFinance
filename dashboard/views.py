from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from dashboard.charts import build_bar_chart, build_line_chart
from dashboard.services import (
    OUTLOOK_MONTHS,
    add_months,
    get_account_evolution,
    get_dashboard_summary,
    get_expenses_by_category_for_method,
    get_expenses_by_payment_method,
)
from transactions.models import Transaction

RECENT_TRANSACTIONS_LIMIT = 5

# How many months the "All time" option on the breakdown charts aggregates.
# Mirrors `EVOLUTION_MONTHS` in `dashboard.services` so the totals the user
# sees in the breakdown match the totals of the time-series window they
# would scroll to with the arrows.
ALL_TIME_MONTHS = 12


def _selected_month(request, in_range):
    """Parse `?month=YYYY-MM` off `request`, falling back to the current month.

    Both screens read the same param under the same forgiving contract: the
    value arrives in a query string, so a malformed or out-of-range one falls
    back to today's month rather than raising a 400. They differ only in
    `in_range`, since they build different windows around the month.
    """
    today = timezone.localdate()
    year_part, _, month_part = request.GET.get('month', '').partition('-')

    if year_part.isdigit() and month_part.isdigit():
        year, month = int(year_part), int(month_part)
        if 1 <= month <= 12 and in_range(year, month):
            return year, month

    return today.year, today.month


def _is_representable(year, month):
    """True when the selected month itself can be built as a `date`.

    All the reports page needs: it projects nothing off the selected month —
    the charts around it are anchored on today — so the only hard requirement
    is that `date(year, month, 1)` does not raise for the label.
    """
    return date.min.year <= year <= date.max.year


def _recent_transactions(user, year, month):
    """The user's most recent transactions billed in (`year`, `month`).

    Scoped to the selected month on the same `amount_for_month` rule as every
    other figure on the page (§8.5), so a fixed subscription or the current
    slice of an installment plan counts here too, not only the month it was
    first recorded. That rule cannot be expressed as a SQL predicate (see
    `dashboard.services`), so this folds in Python and slices the tail end —
    still one query, over one user's rows.
    """
    transactions = Transaction.objects.filter(user=user).select_related(
        'category', 'payment_method'
    )
    return [txn for txn in transactions if txn.amount_for_month(year, month)][
        :RECENT_TRANSACTIONS_LIMIT
    ]


def _is_projectable(year, month):
    """True when the whole dashboard window around (`year`, `month`) is representable.

    The page renders more than the selected month: it links to both
    neighbours, and `get_dashboard_summary` builds an outlook running
    `OUTLOOK_MONTHS` ahead with every row materialised as a `date`. Checking
    that the selected month is itself in range is therefore not enough —
    `?month=9999-12` passes that test, then its outlook walks into year 10000
    and `date()` raises `ValueError: year 10000 is out of range` from inside
    the service. That is a 500 triggered purely by a query string, so the
    bounds have to cover the window the view actually builds.
    """
    earliest_year, _ = add_months(year, month, -1)
    latest_year, _ = add_months(year, month, OUTLOOK_MONTHS - 1)
    return date.min.year <= earliest_year and latest_year <= date.max.year


def _month_choices():
    """List of `(value, label)` pairs for the breakdown filter selects.

    Sentinel `'ALL'` plus the last `ALL_TIME_MONTHS` months anchored on
    today, newest first. Shared by the two breakdown charts so the dropdowns
    look the same — the choice itself is per-chart in the URL.
    """
    today = timezone.localdate()
    choices = [('ALL', 'All time')]
    for step in range(ALL_TIME_MONTHS):
        year, month = add_months(today.year, today.month, -step)
        choices.append((f'{year:04d}-{month:02d}', date(year, month, 1).strftime('%B %Y')))
    return choices


def _parse_month_or_all(request, param_name, in_range):
    """Parse `?<param_name>=ALL|YYYY-MM` with the same forgiving contract.

    Returns `('ALL', None, None)` for the sentinel (or for a missing/empty
    value), and `(value, year, month)` for a specific month that passes
    `in_range`. A bad or out-of-range value falls back to `'ALL'` — the same
    silent fallback every other reports-page filter uses.
    """
    raw = request.GET.get(param_name, '').strip().upper()
    if not raw or raw == 'ALL':
        return 'ALL', None, None

    year_part, _, month_part = raw.partition('-')
    if not (year_part.isdigit() and month_part.isdigit()):
        return 'ALL', None, None

    year, month = int(year_part), int(month_part)
    if not (1 <= month <= 12 and in_range(year, month)):
        return 'ALL', None, None

    return f'{year:04d}-{month:02d}', year, month


def _parse_charts_offset(request, in_range):
    """Parse `?charts_offset=N` (integer) with bounds from `in_range`.

    `in_range` is called with the shifted anchor year/month and must return
    True when the whole 12-month window the view will build fits inside the
    calendar — a 500 inside `get_account_evolution` would otherwise be
    triggerable by a query string, same reasoning as `_is_projectable`.
    """
    raw = request.GET.get('charts_offset', '').strip()
    try:
        offset = int(raw)
    except ValueError:
        return 0

    anchor = add_months(timezone.localdate().year, timezone.localdate().month, offset)
    if not in_range(*anchor):
        return 0

    return offset


def _is_offset_window_safe(year, month):
    """Bounds check for the prev/next arrows on the reports time-series charts.

    The 12-month window around (`year`, `month`) has its extremes at
    `year-5/month` and `year+6/month`. Both have to be representable as
    `date(year, month, 1)` for the labels the chart renders; otherwise the
    shifted window would walk off the calendar and `date()` inside the
    service would raise — the same 500-via-query-string risk that
    `_is_projectable` guards against on the dashboard index.
    """
    earliest_year, earliest_month = add_months(year, month, -5)
    latest_year, latest_month = add_months(year, month, 6)
    return (
        date.min.year <= earliest_year <= date.max.year
        and date.min.year <= latest_year <= date.max.year
        and 1 <= earliest_month <= 12
        and 1 <= latest_month <= 12
    )


class DashboardIndexView(LoginRequiredMixin, TemplateView):
    """Post-login landing page (FR05, FR15, `LOGIN_REDIRECT_URL`).

    Renders the stat cards (Current Balance, Income/Expenses/Investments for
    the selected month, Balance month, Projected Balance), a forward-looking
    outlook table, and a recent-transactions list scoped to that same selected
    month. All data is scoped to `request.user` (PRD R3) and computed by
    `dashboard.services`.

    Month selection is a plain `?month=YYYY-MM` GET param (zero-JS, same
    convention as the transaction list filter); an absent or malformed value
    falls back to the current month rather than raising a 400.
    """

    template_name = 'dashboard/index.html'

    def get_selected_month(self):
        """Parse `?month=YYYY-MM`, falling back to the current month."""
        return _selected_month(self.request, _is_projectable)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self.get_selected_month()
        context.update(get_dashboard_summary(self.request.user, year, month))

        previous_year, previous_month = add_months(year, month, -1)
        next_year, next_month = add_months(year, month, 1)
        context['previous_month_param'] = f'{previous_year:04d}-{previous_month:02d}'
        context['next_month_param'] = f'{next_year:04d}-{next_month:02d}'

        context['recent_transactions'] = _recent_transactions(
            self.request.user, year, month
        )
        return context


class DashboardReportsView(LoginRequiredMixin, TemplateView):
    """Charts showing how the account evolves over a year (FR16).

    Four server-rendered charts, all reading the same Transaction rows on
    exactly the same recurrence rules:

      1. Balance evolution          — area + line, window of `EVOLUTION_MONTHS`
                                      months, slideable through time via
                                      `?charts_offset=N`.
      2. Monthly cash flow          — grouped bars over the same window, so
                                      the two time-series charts always tell
                                      the same story.
      3. Where the money goes       — top expense categories. Optional
                                      `?category_month=ALL|YYYY-MM` chooses
                                      the window (default: the last 12
                                      months, in line with the time-series
                                      window).
      4. Spending by payment method — one bar per method, with
                                      `?payment_month=ALL|YYYY-MM` (default
                                      `ALL`) choosing the window. Each bar
                                      is a hyperlink to a `method-categories`
                                      panel that answers the next question
                                      ("what did I buy on that card?").

    The four filters are independent — offsetting the time-series window
    leaves the breakdown filters untouched, and the breakdown filters never
    move the time-series window. The template uses `{% querystring %}` so
    any one of them survives clicks on the others.

    Scoped to `request.user` like every other internal screen (PRD R3).
    """

    template_name = 'dashboard/reports.html'

    def get_charts_offset(self):
        """Parse `?charts_offset=N`, falling back to 0 on bad / out-of-window values."""
        return _parse_charts_offset(self.request, _is_offset_window_safe)

    def get_category_month(self):
        """Parse `?category_month=ALL|YYYY-MM` (default `ALL`)."""
        return _parse_month_or_all(self.request, 'category_month', _is_representable)

    def get_payment_month(self):
        """Parse `?payment_month=ALL|YYYY-MM` (default `ALL`)."""
        return _parse_month_or_all(self.request, 'payment_month', _is_representable)

    def get_selected_payment_method(self, breakdown):
        """Parse `?payment_method=NAME`, validated against the current breakdown.

        Only a method that appears in the current breakdown's `methods` is
        accepted — anything else silently returns `None`, so a stale URL
        from a different month cannot surface an empty panel.
        """
        if not breakdown['methods']:
            return None
        valid_names = {row['name'] for row in breakdown['methods']}
        raw = self.request.GET.get('payment_method', '').strip()
        return raw if raw in valid_names else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Charts 1 & 2 — the time-series window, slideable through time.
        offset = self.get_charts_offset()
        evolution = get_account_evolution(self.request.user, offset=offset)
        months = evolution['months']

        # The whole month row travels through as the label, so the template
        # can read `.date`/`.is_current_month` off each point without having
        # to index back into `months` in parallel.
        context['evolution'] = evolution
        context['charts_offset'] = offset
        context['previous_offset_param'] = offset - 1
        context['next_offset_param'] = offset + 1
        context['balance_chart'] = build_line_chart(
            months, [float(row['closing_balance']) for row in months]
        )
        context['cashflow_chart'] = build_bar_chart(
            months,
            [
                {
                    'name': 'Income',
                    'tone': 'income',
                    'values': [float(row['income']) for row in months],
                },
                {
                    'name': 'Expenses',
                    'tone': 'expense',
                    'values': [float(row['expenses']) for row in months],
                },
                {
                    'name': 'Investments',
                    'tone': 'investment',
                    'values': [float(row['investments']) for row in months],
                },
            ],
        )

        # Filter choices shared by both breakdown charts so the dropdowns
        # look and read the same.
        context['month_choices'] = _month_choices()

        # Chart 3 — "Where the money goes". The breakdown lives inside
        # `evolution` already, but only for the time-series window. When the
        # user picks a different month (or explicitly `ALL`), we recompute.
        category_value, category_year, category_month = self.get_category_month()
        context['category_month_param'] = category_value
        if category_value == 'ALL':
            # Reuse the breakdown the evolution already computed, since
            # "all time" on this filter means the same 12-month window.
            context['expenses_by_category'] = evolution['expenses_by_category']
            context['category_window_label'] = 'All time'
        else:
            from dashboard.services import (
                _expenses_by_category,
                _projection_queryset,
            )

            transactions = list(
                _projection_queryset(self.request.user, with_category=True)
            )
            context['expenses_by_category'] = _expenses_by_category(
                transactions, category_year, category_month, 1
            )
            context['category_window_label'] = (
                date(category_year, category_month, 1).strftime('%B %Y')
            )

        # Chart 4 — "Spending by payment method". `ALL` aggregates the
        # last `ALL_TIME_MONTHS` months; a specific `YYYY-MM` reads that
        # single month on the same `amount_for_month` rule as before.
        payment_value, payment_year, payment_month = self.get_payment_month()
        context['payment_month_param'] = payment_value
        if payment_value == 'ALL':
            breakdown = get_expenses_by_payment_method(
                self.request.user, months=ALL_TIME_MONTHS
            )
            context['payment_window_label'] = 'All time'
        else:
            breakdown = get_expenses_by_payment_method(
                self.request.user, payment_year, payment_month
            )
            context['payment_window_label'] = (
                date(payment_year, payment_month, 1).strftime('%B %Y')
            )
        context['payment_breakdown'] = breakdown
        context['payment_chart'] = (
            build_bar_chart(
                breakdown['methods'],
                [
                    {
                        'name': 'Expenses',
                        'tone': 'expense',
                        'values': [float(row['total']) for row in breakdown['methods']],
                    }
                ],
            )
            if breakdown['methods']
            else None
        )

        # The "method categories" panel that opens when a bar is clicked.
        # Validated against the current breakdown so a stale URL never shows
        # a panel for a method that isn't on the chart it was clicked from.
        selected_method = self.get_selected_payment_method(breakdown)
        context['selected_payment_method'] = selected_method
        if selected_method is not None:
            if payment_value == 'ALL':
                # No specific month was chosen — anchor the panel on today's
                # month so it answers "what did I buy with this card most
                # recently" rather than aggregating a fuzzy 12-month window.
                today = timezone.localdate()
                method_categories = get_expenses_by_category_for_method(
                    self.request.user,
                    selected_method,
                    today.year,
                    today.month,
                )
                context['method_categories_label'] = today.strftime('%B %Y')
                context['method_categories_window'] = 'current month'
            else:
                method_categories = get_expenses_by_category_for_method(
                    self.request.user,
                    selected_method,
                    payment_year,
                    payment_month,
                )
                context['method_categories_label'] = (
                    date(payment_year, payment_month, 1).strftime('%B %Y')
                )
                context['method_categories_window'] = 'selected month'
            context['method_categories'] = method_categories
        else:
            context['method_categories'] = []
            context['method_categories_label'] = ''
            context['method_categories_window'] = ''

        return context
