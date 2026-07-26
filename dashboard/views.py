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
)
from transactions.models import Transaction

RECENT_TRANSACTIONS_LIMIT = 5


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


class DashboardIndexView(LoginRequiredMixin, TemplateView):
    """Post-login landing page (FR05, FR15, `LOGIN_REDIRECT_URL`).

    Renders the stat cards (Current Balance, Income/Expenses/Investments for
    the selected month, Balance month, Projected Balance), a forward-looking
    outlook table, and a recent-transactions list. All data is scoped to
    `request.user` (PRD R3) and computed by `dashboard.services`.

    Month selection is a plain `?month=YYYY-MM` GET param (zero-JS, same
    convention as the transaction list filter); an absent or malformed value
    falls back to the current month rather than raising a 400.
    """

    template_name = 'dashboard/index.html'

    def get_selected_month(self):
        """Parse `?month=YYYY-MM`, falling back to the current month."""
        today = timezone.localdate()
        raw = self.request.GET.get('month', '')
        year_part, _, month_part = raw.partition('-')

        if year_part.isdigit() and month_part.isdigit():
            year, month = int(year_part), int(month_part)
            if 1 <= month <= 12 and _is_projectable(year, month):
                return year, month

        return today.year, today.month

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self.get_selected_month()
        context.update(get_dashboard_summary(self.request.user, year, month))

        previous_year, previous_month = add_months(year, month, -1)
        next_year, next_month = add_months(year, month, 1)
        context['previous_month_param'] = f'{previous_year:04d}-{previous_month:02d}'
        context['next_month_param'] = f'{next_year:04d}-{next_month:02d}'

        context['recent_transactions'] = Transaction.objects.filter(
            user=self.request.user
        ).select_related('category', 'payment_method')[:RECENT_TRANSACTIONS_LIMIT]
        return context


class DashboardReportsView(LoginRequiredMixin, TemplateView):
    """Charts showing how the account evolves over a year (FR16).

    Two charts over the same 12-month window — balance evolution (line) and
    monthly cash flow (grouped bars) — plus a spending-by-category breakdown.
    All three are server-rendered SVG/CSS: the view turns the numeric series
    from `dashboard.services` into pixel coordinates via `dashboard.charts`,
    so the template only interpolates attributes and no JavaScript runs.

    Scoped to `request.user` like every other internal screen (PRD R3).
    """

    template_name = 'dashboard/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        evolution = get_account_evolution(self.request.user)
        months = evolution['months']

        # The whole month row travels through as the label, so the template
        # can read `.date`/`.is_current_month` off each point without having
        # to index back into `months` in parallel.
        context['evolution'] = evolution
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
        return context
