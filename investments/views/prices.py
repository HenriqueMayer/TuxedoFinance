# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owned local observed-price consultation and editing."""

from urllib.parse import urlencode
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from investments.forms import PriceObservationForm, PriceObservationFilterForm
from investments.models import Asset, PriceObservation
from core.navigation import ReturnContextMixin, with_return_url


class PriceObservationListView(LoginRequiredMixin, ListView):
    model = PriceObservation
    template_name = 'investments/prices.html'
    context_object_name = 'observations'
    paginate_by = 30

    def get_queryset(self):
        rows = PriceObservation.objects.filter(user=self.request.user).select_related('asset')
        self.price_filter = PriceObservationFilterForm(self.request.GET, user=self.request.user)
        if not self.price_filter.is_valid():
            # Invalid or foreign identifiers must never broaden a financial view.
            return rows.none()
        asset = self.price_filter.cleaned_data.get('asset')
        return rows.filter(asset=asset) if asset else rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_section'] = 'prices'
        context['price_filter'] = self.price_filter
        context['selected_price_asset'] = self.price_filter.cleaned_data.get('asset')
        context['selected_asset'] = (str(context['selected_price_asset'].pk)
            if context['selected_price_asset'] else '')
        target = reverse('investments:create_price')
        if context['selected_asset']:
            target += '?' + urlencode({'asset': context['selected_asset']})
        context['price_create_url'] = with_return_url(target, self.request.get_full_path())
        return context


class PriceObservationFormMixin(ReturnContextMixin, LoginRequiredMixin):
    model = PriceObservation
    form_class = PriceObservationForm
    template_name = 'investments/price_form.html'
    success_url = reverse_lazy('investments:prices')

    def get_queryset(self):
        return PriceObservation.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        asset = self.request.GET.get('asset', '')
        if asset.isdigit() and Asset.objects.filter(user=self.request.user, pk=asset, valuation_mode='UNITS', is_archived=False).exists():
            initial['asset'] = asset
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            with transaction.atomic():
                return super().form_valid(form)
        except IntegrityError:
            form.add_error('date', _('A price exists for this asset and date. Edit that observation instead.'))
            return self.form_invalid(form)


class PriceObservationCreateView(PriceObservationFormMixin, CreateView):
    pass


class PriceObservationUpdateView(PriceObservationFormMixin, UpdateView):
    pass


class PriceObservationDeleteView(ReturnContextMixin, LoginRequiredMixin, DeleteView):
    model = PriceObservation
    template_name = 'investments/price_confirm_delete.html'
    success_url = reverse_lazy('investments:prices')

    def get_queryset(self):
        return PriceObservation.objects.filter(user=self.request.user)
