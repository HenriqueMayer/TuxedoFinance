from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from dashboard.charts import (
    build_bar_chart,
    build_line_chart,
)
from investments.forms import ExchangeRateForm, InvestmentForm
from investments.models import ExchangeRate, Investment
from investments.services import (
    TIMESERIES_MONTHS,
    get_latest_rates,
    get_monthly_flow_in_base,
    get_per_currency_totals,
    get_simulated_total_in_base,
    get_supported_currencies,
    get_total_in_base_timeseries,
)

ZERO = Decimal('0.00')


def _add_months(year, month, offset):
    """Return the (year, month) pair `offset` whole months from (year, month).

    Local copy of `investments.services._add_months` (itself a copy of
    `dashboard.services.add_months`) so this module does not reach into
    another app just to do month arithmetic. All three implementations
    are bit-for-bit identical and should stay so.
    """
    index = (year * 12 + month - 1) + offset
    return index // 12, index % 12 + 1


def _is_offset_window_safe(year, month):
    """Bounds check for the prev/next arrows on the investments charts.

    The 12-month window anchored at (`year`, `month`) runs from
    `anchor - 11` to `anchor`. Both extremes must be representable as
    `date(year, month, 1)` for the labels the chart renders; otherwise
    the shifted window would walk off the calendar and `date()` inside
    the service would raise — the same 500-via-query-string risk the
    dashboard's `_is_offset_window_safe` guards against.
    """
    earliest_year, earliest_month = _add_months(year, month, -(TIMESERIES_MONTHS - 1))
    latest_year, latest_month = year, month
    return (
        date.min.year <= earliest_year <= date.max.year
        and date.min.year <= latest_year <= date.max.year
        and 1 <= earliest_month <= 12
        and 1 <= latest_month <= 12
    )


def _parse_charts_offset(request, param_name='charts_offset'):
    """Parse `?{param_name}=N` (integer) with bounds from `_is_offset_window_safe`.

    The two charts page carry independent windows — each has its own
    `?total_offset=N` / `?flow_offset=N` param so the user can slide
    one chart without dragging the other along. `param_name` selects
    which one to read; `charts_offset` is the default for backward
    compatibility with any caller that hasn't migrated yet. Mirror of
    `dashboard.views._parse_charts_offset`, adapted to the investments
    window (11 past + current, no future) so the bounds check matches
    `TIMESERIES_MONTHS`.
    """
    raw = request.GET.get(param_name, '').strip()
    try:
        offset = int(raw)
    except ValueError:
        return 0

    anchor = _add_months(timezone.localdate().year, timezone.localdate().month, offset)
    if not _is_offset_window_safe(*anchor):
        return 0

    return offset


class InvestmentListView(LoginRequiredMixin, ListView):
    """List the logged-in user's investment entries with per-currency totals.

    The page opens with a grid of cards — one per supported currency
    (base first, then alphabetical) plus a "simulated total in base"
    card. Each per-currency card shows that currency's deposited,
    withdrawn and net balance; the simulated card sums every currency's
    balance, converted through the user's latest `ExchangeRate`. A
    currency with no rate yet is excluded from the simulation and the
    card surfaces that explicitly, instead of silently showing a too-low
    total.

    Below the cards, a paginated table of the entries themselves with
    two filters: `?kind=DEPOSIT|WITHDRAWAL` and `?q=` (search across
    title, reason, notes).

    At the bottom of the page, two charts over **independent** 12-month
    windows, one slideable anchor per chart. The two windows do not
    have to agree, so the user can slide chart 1 (investment evolution)
    to a year ago while still looking at the current month's flow
    chart 2.

      1. **Investment evolution** (`?total_offset=N`) — a line chart of
         the cumulative portfolio total in the base currency, folded per
         month through `get_rate_at` (the rate that was current at that
         month's close, falling back to the latest rate when no
         historical row exists). Answers "how my patrimony evolved".
         Inherits the Reports chart-1 visual convention (zero-line rose,
         indigo→fuchsia stroke).
      2. **Monthly flow** (`?flow_offset=N`) — grouped bars of Deposits ×
         Withdrawals per month, both in base through per-entry
         `get_rate_at` on `entry.date`. Answers "what I invested/rescued
         month by month".

    When a currency has no rate at all, both the simulated-total card
    and the FX-converted charts (1 and 2) exclude it and the page
    surfaces one unified warning — see `missing_rate_currencies` in the
    context.

    The cards' totals come from the **unfiltered** queryset, so a
    filtered list never makes the cards lie.
    """

    model = Investment
    template_name = 'investments/list.html'
    context_object_name = 'investments'
    paginate_by = 10

    KIND_FILTER_OPTIONS = ('DEPOSIT', 'WITHDRAWAL')

    def get_template_names(self):
        """Return the charts partial when HTMX asks for one, the full page otherwise.

        HTMX always sends `HX-Request: true` on the requests it makes,
        so the presence of that header is the cleanest signal that the
        caller wants only the charts island back, not the full list
        page. The partial (`_investments_charts.html`) and the full
        page (`list.html`) render through the same context the only
        difference is which template gets chosen here. Mirrors
        `DashboardReportsView.get_template_names` exactly.
        """
        if self.request.headers.get('HX-Request') == 'true':
            return ['investments/_investments_charts.html']
        return [self.template_name]

    def get_total_offset(self):
        """Parse `?total_offset=N` for chart 1 (Investment evolution)."""
        return _parse_charts_offset(self.request, 'total_offset')

    def get_flow_offset(self):
        """Parse `?flow_offset=N` for chart 2 (Monthly flow)."""
        return _parse_charts_offset(self.request, 'flow_offset')

    def get_queryset(self):
        queryset = Investment.objects.filter(user=self.request.user)

        kind = self.request.GET.get('kind', '').strip().upper()
        if kind in self.KIND_FILTER_OPTIONS:
            queryset = queryset.filter(kind=kind)

        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(reason__icontains=search)
                | Q(notes__icontains=search)
            )

        return queryset.order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_currency = settings.CURRENCY

        # Per-currency cards: one bucket per supported currency, even when
        # the user has no entries in that currency, so the grid never has
        # a hole. The order is base first, then alphabetical.
        supported = get_supported_currencies(base_currency)
        per_currency = get_per_currency_totals(self.request.user, supported)

        # Simulated total in the base currency, using the user's latest
        # rate per (foreign → base) pair. Returns the total and the list
        # of currencies excluded because no rate was set.
        rates = get_latest_rates(self.request.user, base_currency)
        balances = {code: bucket['balance'] for code, bucket in per_currency.items()}
        simulated_total, missing_currencies = get_simulated_total_in_base(
            self.request.user, base_currency, balances, rates
        )

        # Per-currency sparklines used to live here — replaced by two
        # full-size charts at the bottom of the page (investment
        # evolution line, monthly-flow bars). Both read a 12-month
        # window and fold currencies into {{ CURRENCY }} through
        # rate-at-time FX.

        # Each chart owns its own `?{kind}_offset=N` window, so the
        # user can slide one without dragging the other along.
        # Default for every offset is 0 (anchored on today); a bad or
        # out-of-range value falls back to 0 via `_parse_charts_offset`.
        total_offset = self.get_total_offset()
        flow_offset = self.get_flow_offset()
        today = timezone.localdate()

        # Chart 1 — investment evolution: cumulative total in base, one
        # line. Fold each month's per-currency balances through the
        # rate that was current at that month's close
        # (`get_total_in_base_timeseries` uses `get_rate_at`, falling
        # back to the latest rate when no historical row exists).
        total_rows, total_missing = get_total_in_base_timeseries(
            self.request.user, base_currency, supported,
            months=TIMESERIES_MONTHS, offset=total_offset,
        )
        chart_total = build_line_chart(
            total_rows,
            [float(row['total']) for row in total_rows],
        )

        # Chart 2 — monthly flow: Deposits × Withdrawals per month, both
        # in base through per-entry `get_rate_at` on `entry.date`. Two
        # series, grouped bars per month.
        flow_rows, flow_missing = get_monthly_flow_in_base(
            self.request.user, base_currency, supported,
            months=TIMESERIES_MONTHS, offset=flow_offset,
        )
        chart_flow = build_bar_chart(
            flow_rows,
            [
                {
                    'name': 'Deposits',
                    'tone': 'income',
                    'values': [float(row['deposits']) for row in flow_rows],
                },
                {
                    'name': 'Withdrawals',
                    'tone': 'expense',
                    'values': [float(row['withdrawals']) for row in flow_rows],
                },
            ],
        )

        # Union the missing-rate sets so one card-level warning covers
        # every chart. In practice they are identical (a currency
        # missing the latest rate is also missing every historical
        # lookup), but the union is cheap and survives any future
        # helper divergence.
        missing_rate_currencies = sorted(
            set(missing_currencies) | set(total_missing) | set(flow_missing)
        )

        context['per_currency_cards'] = [
            per_currency[code] for code in supported
        ]
        context['simulated_total'] = simulated_total
        context['missing_rate_currencies'] = missing_rate_currencies
        context['base_currency'] = base_currency
        context['kind_choices'] = Investment.Kind.choices
        context['selected_kind'] = self.request.GET.get('kind', '').strip().upper()
        context['search_query'] = self.request.GET.get('q', '').strip()
        # The two charts at the bottom of the page. Hidden when the
        # user has no investments — flat-at-zero lines and bars are not
        # informative, and the empty-state CTA above already tells the
        # user to add an entry.
        context['has_investments'] = Investment.objects.filter(
            user=self.request.user
        ).exists()
        context['chart_total'] = chart_total
        context['chart_flow'] = chart_flow
        context['today'] = today

        # Per-chart window slides. Each chart carries its own offset so
        # the prev/next arrows update only the param that chart owns —
        # `{% querystring <param>=N %}` on the arrows preserves the
        # other offset, plus the kind/search filters. The window label
        # comes from the first and last rows of each chart's own time
        # series so the label always matches what the chart shows.
        context['total_offset'] = total_offset
        context['total_previous_offset_param'] = total_offset - 1
        context['total_next_offset_param'] = total_offset + 1
        context['is_total_anchored_today'] = total_offset == 0
        t_anchor_y, t_anchor_m = _add_months(today.year, today.month, total_offset)
        context['total_anchor_date'] = date(t_anchor_y, t_anchor_m, 1)
        if total_rows:
            context['total_window_start_date'] = total_rows[0]['date']
            context['total_window_end_date'] = total_rows[-1]['date']

        context['flow_offset'] = flow_offset
        context['flow_previous_offset_param'] = flow_offset - 1
        context['flow_next_offset_param'] = flow_offset + 1
        context['is_flow_anchored_today'] = flow_offset == 0
        f_anchor_y, f_anchor_m = _add_months(today.year, today.month, flow_offset)
        context['flow_anchor_date'] = date(f_anchor_y, f_anchor_m, 1)
        if flow_rows:
            context['flow_window_start_date'] = flow_rows[0]['date']
            context['flow_window_end_date'] = flow_rows[-1]['date']
        return context


class InvestmentFormMixin(LoginRequiredMixin):
    """Shared plumbing for the create/update CBVs (per-user isolation, PRD R3)."""

    model = Investment
    form_class = InvestmentForm
    template_name = 'investments/form.html'
    success_url = reverse_lazy('investments:list')

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)


# `InvestmentFormMixin` precedes `SuccessMessageMixin` in the bases below for
# the same reason as in `payments/views.py` — keeping its `form_valid` last
# in the MRO so a save that turns into a failure never announces a success.
class InvestmentCreateView(InvestmentFormMixin, SuccessMessageMixin, CreateView):
    """Create an investment entry owned by the logged-in user."""

    success_message = 'Investment "%(title)s" created.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class InvestmentUpdateView(InvestmentFormMixin, SuccessMessageMixin, UpdateView):
    """Update one of the logged-in user's own investment entries."""

    success_message = 'Investment "%(title)s" updated.'


class InvestmentDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an investment entry with confirmation (zero-JS POST pattern)."""

    model = Investment
    template_name = 'investments/confirm_delete.html'
    context_object_name = 'investment'
    success_url = reverse_lazy('investments:list')

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)

    def form_valid(self, form):
        title = self.object.title
        response = super().form_valid(form)
        messages.success(self.request, f'Investment "{title}" deleted.')
        return response


# ---------------------------------------------------------------------------
# ExchangeRate — manual rates the user sets to convert foreign-currency
# investments into the project base currency. Rates are append-only; an
# update is a new row with a newer `effective_date`.
# ---------------------------------------------------------------------------


class ExchangeRateListView(LoginRequiredMixin, ListView):
    """List the user's exchange rates, grouped by `from_currency`.

    The most recent row per pair is the "current" rate and is rendered
    prominently; older rows for the same pair are kept in a collapsed
    history list (no JS, just a `<details>`). Delete is always a POST
    from the confirm screen — never a plain link/GET.
    """

    model = ExchangeRate
    template_name = 'investments/settings/exchange_rates_list.html'
    context_object_name = 'rates'
    paginate_by = 20

    def get_queryset(self):
        return (
            ExchangeRate.objects.filter(user=self.request.user)
            .order_by('from_currency', '-effective_date', '-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_currency = settings.CURRENCY
        context['base_currency'] = base_currency
        context['create_form'] = ExchangeRateForm(base_currency=base_currency)
        return context


class ExchangeRateCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    """Append a new `ExchangeRate` row for the logged-in user.

    There is no update view on purpose: rates are append-only. If the
    rate moved, the user creates a new row with a newer
    `effective_date`; the old one stays put for history.
    """

    model = ExchangeRate
    form_class = ExchangeRateForm
    template_name = 'investments/settings/exchange_rates_list.html'
    success_url = reverse_lazy('investments:exchange_rates')
    success_message = 'Exchange rate saved.'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['base_currency'] = settings.CURRENCY
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        # The create form reuses the list page template so the user sees
        # the current rates above the form and the form inline at the
        # bottom. The template references the form as `create_form` (set
        # by the list view), so we re-publish the bound form under that
        # key on a re-render after an invalid POST — otherwise the form
        # would appear empty and any field errors would be invisible.
        context = super().get_context_data(**kwargs)
        context['base_currency'] = settings.CURRENCY
        context['rates'] = (
            ExchangeRate.objects.filter(user=self.request.user)
            .order_by('from_currency', '-effective_date', '-created_at')
        )
        if 'form' in context:
            context['create_form'] = context['form']
        return context


class ExchangeRateDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an exchange rate with confirmation (zero-JS POST pattern)."""

    model = ExchangeRate
    template_name = 'investments/settings/confirm_delete_rate.html'
    context_object_name = 'rate'
    success_url = reverse_lazy('investments:exchange_rates')

    def get_queryset(self):
        return ExchangeRate.objects.filter(user=self.request.user)

    def form_valid(self, form):
        rate = self.object
        label = f'1 {rate.from_currency} = {rate.rate} {rate.to_currency}'
        response = super().form_valid(form)
        messages.success(self.request, f'Exchange rate ({label}) deleted.')
        return response
