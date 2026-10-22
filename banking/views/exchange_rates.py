# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Exchange-rate consultation and evidence administration."""

from datetime import date
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView
from core.currencies import CURRENCIES
from banking.forms import ExchangeRateForm, ExchangeRateFilterForm
from banking.models import ExchangeRate
from .base import OwnedDeleteView, OwnedFormMixin


class ExchangeRateListView(LoginRequiredMixin, ListView):
    model = ExchangeRate
    template_name = 'banking/exchange_rates.html'
    context_object_name = 'rates'
    paginate_by = 30

    def get_queryset(self):
        rates = ExchangeRate.objects.filter(user=self.request.user)
        self.filter_form = ExchangeRateFilterForm(self.request.GET or None, user=self.request.user)
        if self.filter_form.is_bound:
            if not self.filter_form.is_valid():
                return rates.none()
            data = self.filter_form.cleaned_data
            for name in ('from_currency', 'to_currency'):
                if data[name]:
                    rates = rates.filter(**{name: data[name]})
            if data['date_from']:
                rates = rates.filter(effective_date__gte=data['date_from'])
            if data['date_to']:
                rates = rates.filter(effective_date__lte=data['date_to'])
            if data['q']:
                rates = rates.filter(Q(from_currency__icontains=data['q']) | Q(to_currency__icontains=data['q']) | Q(notes__icontains=data['q']))
        return rates.order_by('-effective_date', 'from_currency', 'to_currency', '-pk')

    def get_context_data(self, **kwargs):
        active_filter_count = (sum(bool(self.filter_form.cleaned_data.get(name))
            for name in self.filter_form.fields if name != 'q')
            if self.filter_form.is_bound and self.filter_form.is_valid() else 0)
        return super().get_context_data(**kwargs) | {'filter_form': self.filter_form,
            'has_filters': any(self.request.GET.get(name) for name in self.filter_form.fields),
            'active_filter_count': active_filter_count}


class ExchangeRateFormMixin(OwnedFormMixin):
    model = ExchangeRate
    form_class = ExchangeRateForm
    form_variant = 'exchange_rate'
    success_url = reverse_lazy('banking:exchange_rates')

    def get_cancel_url(self):
        return reverse('banking:exchange_rates')


class ExchangeRateCreateView(ExchangeRateFormMixin, CreateView):
    form_title = _('New exchange rate')

    def get_initial(self):
        initial = super().get_initial()
        for name in ('from_currency', 'to_currency'):
            value = self.request.GET.get(name, '')
            if value in CURRENCIES:
                initial[name] = value
        try:
            initial['effective_date'] = date.fromisoformat(self.request.GET.get('effective_date', ''))
        except ValueError:
            pass
        # A diagnostic may preselect the pair/date, never guess the price.
        return initial


class ExchangeRateUpdateView(ExchangeRateFormMixin, UpdateView):
    form_title = _('Edit exchange rate')


class ExchangeRateDeleteView(OwnedDeleteView):
    model = ExchangeRate

    def get_return_fallback(self):
        return reverse('banking:exchange_rates')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['delete_message'] = _(
            'This action cannot be undone. Current valuations may change or show missing rates. '
            'Conversions already saved in transfers and investments will be preserved.'
        )
        return context
