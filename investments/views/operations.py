# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Operation consultation, editing and explicit ledger synchronization."""

from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from banking.models import Bank
from investments.forms import InvestmentForm, InvestmentOperationFilterForm
from investments.models import Asset, Investment, InvestmentProduct
from investments.positions import validate_position_history
from investments.services import cleanup_investment_ledger, sync_investment_ledger, refresh_fx_snapshot
from accounts.models import UserPreference
from core.navigation import ReturnContextMixin, with_return_url
from .setup import _investment_setup


class InvestmentOperationsView(LoginRequiredMixin, ListView):
    model = Investment
    template_name = 'investments/operations.html'
    context_object_name = 'investments'
    paginate_by = 10

    def get_purpose(self):
        return {
            'portfolio': InvestmentProduct.Purpose.INVESTMENT,
            'cash': InvestmentProduct.Purpose.MONTHLY_CASH,
        }.get(self.request.GET.get('section'))

    def get_template_names(self):
        if (self.request.headers.get('HX-Request') == 'true'
                and self.request.headers.get('HX-Target') == 'investment-movements'):
            return ['investments/_investment_movements.html']
        return [self.template_name]

    def get_queryset(self):
        queryset = Investment.objects.filter(
            user=self.request.user,
        ).select_related(
            'product__bank', 'asset', 'source_account', 'source_program',
            'destination_account'
        )
        purpose = self.get_purpose()
        if purpose:
            queryset = queryset.filter(product__purpose=purpose)
        kind = self.request.GET.get('kind', '').upper()
        if kind in Investment.Kind.values:
            queryset = queryset.filter(kind=kind)
        bank = self.request.GET.get('bank', '')
        product = self.request.GET.get('product', '')
        asset = self.request.GET.get('asset', '')
        if bank.isdigit():
            queryset = queryset.filter(product__bank_id=bank)
        if product.isdigit():
            queryset = queryset.filter(product_id=product)
        if asset.isdigit():
            queryset = queryset.filter(asset_id=asset)
        self.operation_filter = InvestmentOperationFilterForm(self.request.GET, user=self.request.user)
        if self.operation_filter.is_valid():
            values = self.operation_filter.cleaned_data
            for name, lookup in (('currency', 'asset__currency'), ('asset_class', 'asset__asset_class'),
                                 ('date_from', 'date__gte'), ('date_to', 'date__lte')):
                if values.get(name):
                    queryset = queryset.filter(**{lookup: values[name]})
        else:
            # Invalid ranges must not quietly broaden the financial history.
            queryset = queryset.none()
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(reason__icontains=search)
                | Q(notes__icontains=search)
                | Q(product__name__icontains=search)
                | Q(asset__name__icontains=search)
                | Q(asset__code__icontains=search)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update(_investment_setup(user))
        # Keep all owned products available when switching the purpose filter.
        context.update({
            'selected_section': 'operations',
            'selected_purpose': self.request.GET.get('section', '') if self.get_purpose() else '',
            'kind_choices': Investment.Kind.choices,
            'selected_kind': self.request.GET.get('kind', '').upper(),
            'bank_choices': Bank.objects.filter(user=user),
            'product_choices': InvestmentProduct.objects.filter(user=user).select_related('bank'),
            'asset_choices': Asset.objects.filter(user=user),
            'selected_bank': self.request.GET.get('bank', ''),
            'selected_product': self.request.GET.get('product', ''),
            'selected_asset': self.request.GET.get('asset', ''),
            'search_query': self.request.GET.get('q', '').strip(),
            'operation_filter': self.operation_filter,
            'has_extra_filters': any(self.request.GET.get(name) for name in self.operation_filter.fields),
            'history_filter_count': sum(bool(self.request.GET.get(name)) for name in
                ('section', 'kind', 'bank', 'product', 'asset', *self.operation_filter.fields)),
        })
        return context


class InvestmentFormMixin(ReturnContextMixin, LoginRequiredMixin):
    model = Investment
    form_class = InvestmentForm
    template_name = 'investments/form.html'
    success_url = reverse_lazy('investments:operations')

    def get_return_fallback(self):
        url = str(self.success_url)
        if self.object and self.object.product.purpose == InvestmentProduct.Purpose.MONTHLY_CASH:
            return f'{url}?section=cash'
        return url

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context['form']
        if 'capture_missing_fx' in form.fields:
            target = reverse('banking:exchange_rate_create') + '?' + urlencode({
                'from_currency': form.instance.currency,
                'to_currency': UserPreference.for_user(self.request.user).base_currency,
                'effective_date': form.instance.date.isoformat() if form.instance.date else '',
            })
            context['exchange_rate_create_url'] = with_return_url(
                target, self.request.get_full_path(), fragment='investment-operation-form')
        return context

    def form_valid(self, form):
        refresh_snapshot = not self.object or bool(
            set(form.changed_data)
            & {'asset', 'quantity', 'unit_price', 'amount', 'ending_balance', 'fees', 'date'}
        ) or form.cleaned_data.get('capture_missing_fx', False)
        form.instance.user = self.request.user
        with transaction.atomic():
            prior_pair = Investment.objects.filter(pk=form.instance.pk, user=self.request.user).values_list('product_id', 'asset_id').first() if form.instance.pk else None
            try:
                form.refresh_yield_amount(lock=True)
                form.instance.full_clean()
            except ValidationError as error:
                for field, values in error.message_dict.items():
                    target = field if field in form.fields else None
                    for value in values:
                        form.add_error(target, value)
                return self.form_invalid(form)
            response = super().form_valid(form)
            if refresh_snapshot:
                refresh_fx_snapshot(self.object)
            try:
                sync_investment_ledger(self.object)
                pairs = [(self.object.product_id, self.object.asset_id)]
                if prior_pair:
                    pairs.append(prior_pair)
                validate_position_history(self.request.user, pairs)
            except Exception as error:
                if hasattr(error, 'message_dict'):
                    transaction.set_rollback(True)
                    for field, values in error.message_dict.items():
                        target = field if field in form.fields else None
                        for value in values:
                            form.add_error(target, value)
                    return self.form_invalid(form)
                raise
        return response


class InvestmentCreateView(InvestmentFormMixin, SuccessMessageMixin, CreateView):
    success_message = gettext_lazy('Investment operation created.')

    def get_initial(self):
        initial = super().get_initial()
        # Position shortcuts select only explicitly requested, owned records.
        # A bound POST remains authoritative in Django's form initialization.
        for name, model in (('product', InvestmentProduct), ('asset', Asset)):
            value = self.request.GET.get(name, '')
            choices = model.objects.filter(user=self.request.user)
            if model is Asset:
                choices = choices.filter(is_archived=False)
            if value.isdigit() and choices.filter(pk=value).exists():
                initial[name] = value
        kind = self.request.GET.get('kind', '').upper()
        if kind in Investment.Kind.values:
            initial['kind'] = kind
        return initial


class InvestmentUpdateView(InvestmentFormMixin, SuccessMessageMixin, UpdateView):
    success_message = gettext_lazy('Investment operation updated.')


@login_required
@require_POST
def yield_preview(request):
    """Render a non-persistent, server-calculated monetary yield preview."""
    operation = None
    operation_id = request.POST.get('operation_id', '')
    if operation_id.isdigit():
        operation = get_object_or_404(Investment, pk=operation_id, user=request.user)

    form = InvestmentForm(request.POST, user=request.user, instance=operation)
    form.is_valid()
    preview = form.yield_preview if not form.errors else None
    error = None
    for field in ('ending_balance', 'amount', 'yield_input_mode'):
        if form.errors.get(field):
            error = form.errors[field][0]
            break
    return render(request, 'investments/_yield_preview.html', {
        'preview': preview,
        'currency': form.cleaned_data['asset'].currency if preview else None,
        'error': error,
    })


class InvestmentDeleteView(ReturnContextMixin, LoginRequiredMixin, DeleteView):
    model = Investment
    template_name = 'investments/confirm_delete.html'
    context_object_name = 'investment'
    success_url = reverse_lazy('investments:operations')

    def get_return_fallback(self):
        url = str(self.success_url)
        if self.object.product.purpose == InvestmentProduct.Purpose.MONTHLY_CASH:
            return f'{url}?section=cash'
        return url

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                validate_position_history(self.request.user, [(self.object.product_id, self.object.asset_id)], exclude_pk=self.object.pk)
                cleanup_investment_ledger(self.object)
                response = super().form_valid(form)
        except ValidationError as error:
            form.add_error(None, error.messages)
            return self.form_invalid(form)
        messages.success(self.request, _('Investment operation deleted.'))
        return response
