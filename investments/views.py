from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from dashboard.charts import build_sparkline
from investments.forms import ExchangeRateForm, InvestmentForm
from investments.models import ExchangeRate, Investment
from investments.services import (
    TIMESERIES_MONTHS,
    get_cumulative_balance_timeseries,
    get_latest_rates,
    get_per_currency_totals,
    get_simulated_total_in_base,
    get_supported_currencies,
)

ZERO = Decimal('0.00')


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

    The cards' totals come from the **unfiltered** queryset, so a
    filtered list never makes the cards lie.
    """

    model = Investment
    template_name = 'investments/list.html'
    context_object_name = 'investments'
    paginate_by = 10

    KIND_FILTER_OPTIONS = ('DEPOSIT', 'WITHDRAWAL')

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

        # Per-currency sparklines: one mini chart per code, each in its
        # own scale. Built by walking the same monthly window used by
        # the rest of the page and pulling each currency's running
        # balance at the close of every month.
        cumulative = get_cumulative_balance_timeseries(
            self.request.user, supported, months=TIMESERIES_MONTHS
        )
        sparklines = []
        for code in supported:
            bucket = per_currency[code]
            values = [float(row['balances'].get(code, Decimal('0.00'))) for row in cumulative]
            labels = [row['date'] for row in cumulative]
            sparklines.append(
                {
                    'code': code,
                    'symbol': bucket['symbol'],
                    'name': bucket['name'],
                    'current_balance': bucket['balance'],
                    'sparkline': build_sparkline(labels, values),
                }
            )

        context['per_currency_cards'] = [
            per_currency[code] for code in supported
        ]
        context['simulated_total'] = simulated_total
        context['missing_rate_currencies'] = missing_currencies
        context['base_currency'] = base_currency
        context['kind_choices'] = Investment.Kind.choices
        context['selected_kind'] = self.request.GET.get('kind', '').strip().upper()
        context['search_query'] = self.request.GET.get('q', '').strip()
        # The sparkline grid at the bottom of the page. Hidden when
        # the user has no investments — six flat-at-zero sparklines
        # are not informative, and the empty-state CTA above already
        # tells the user to add an entry.
        context['has_investments'] = Investment.objects.filter(
            user=self.request.user
        ).exists()
        context['sparklines'] = sparklines
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
