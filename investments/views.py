from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from banking.models import Bank
from banking.services import MissingExchangeRate, convert
from dashboard.charts import build_bar_chart, build_line_chart
from investments.forms import AssetForm, InvestmentForm, InvestmentProductForm
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import (
    TIMESERIES_MONTHS,
    cleanup_investment_ledger,
    get_asset_positions,
    get_monthly_flow_in_base,
    get_portfolio_groups,
    get_total_in_base_timeseries,
    sync_investment_ledger,
    refresh_fx_snapshot,
)
from accounts.models import UserPreference


def _add_months(year, month, offset):
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1


def _parse_offset(request, name):
    try:
        offset = int(request.GET.get(name, '0'))
        start_year, _ = _add_months(
            timezone.localdate().year,
            timezone.localdate().month,
            offset - TIMESERIES_MONTHS + 1,
        )
        end_year, _ = _add_months(
            timezone.localdate().year, timezone.localdate().month, offset
        )
        return offset if date.min.year <= start_year <= end_year <= date.max.year else 0
    except (TypeError, ValueError):
        return 0


class InvestmentListView(LoginRequiredMixin, ListView):
    model = Investment
    template_name = 'investments/list.html'
    context_object_name = 'investments'
    paginate_by = 10

    def get_template_names(self):
        if self.request.headers.get('HX-Request') == 'true':
            if self.request.headers.get('HX-Target') == 'investment-movements':
                return ['investments/_investment_movements.html']
            return ['investments/_investments_charts.html']
        return [self.template_name]

    def get_queryset(self):
        queryset = Investment.objects.filter(user=self.request.user).select_related(
            'product__bank', 'asset', 'source_account', 'source_program',
            'destination_account'
        )
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
        base = UserPreference.for_user(user).base_currency
        total = Decimal('0.00')
        missing = set()
        for position in get_asset_positions(user):
            try:
                total += convert(
                    user,
                    position['value_flow'],
                    position['asset'].currency,
                    base,
                )
            except MissingExchangeRate:
                missing.add(position['asset'].currency)

        total_offset = _parse_offset(self.request, 'total_offset')
        flow_offset = _parse_offset(self.request, 'flow_offset')
        total_rows, total_missing = get_total_in_base_timeseries(
            user, base, months=TIMESERIES_MONTHS, offset=total_offset
        )
        flow_rows, flow_missing = get_monthly_flow_in_base(
            user, base, months=TIMESERIES_MONTHS, offset=flow_offset
        )
        portfolio_groups = get_portfolio_groups(user)
        portfolio_missing = set()
        for bank in portfolio_groups:
            for product in bank['products']:
                for asset in product['assets']:
                    try:
                        asset['base_balance'] = convert(
                            user, asset['balance'], asset['currency'], base
                        )
                    except MissingExchangeRate:
                        asset['base_balance'] = None
                        portfolio_missing.add(asset['currency'])
        today = timezone.localdate()
        context.update({
            'portfolio_groups': portfolio_groups,
            'simulated_total': total.quantize(Decimal('0.01')),
            'missing_rate_currencies': sorted(
                missing | set(total_missing) | set(flow_missing) | portfolio_missing
            ),
            'base_currency': base,
            'kind_choices': Investment.Kind.choices,
            'selected_kind': self.request.GET.get('kind', '').upper(),
            'bank_choices': Bank.objects.filter(user=user),
            'product_choices': InvestmentProduct.objects.filter(user=user).select_related('bank'),
            'asset_choices': Asset.objects.filter(user=user),
            'selected_bank': self.request.GET.get('bank', ''),
            'selected_product': self.request.GET.get('product', ''),
            'selected_asset': self.request.GET.get('asset', ''),
            'search_query': self.request.GET.get('q', '').strip(),
            'has_investments': Investment.objects.filter(user=user).exists(),
            'chart_total': build_line_chart(total_rows, [float(row['total']) for row in total_rows]),
            'chart_flow': build_bar_chart(flow_rows, [
                {'name': _('Deposits'), 'tone': 'income', 'values': [float(row['deposits']) for row in flow_rows]},
                {'name': _('Withdrawals'), 'tone': 'expense', 'values': [float(row['withdrawals']) for row in flow_rows]},
                {'name': _('Yields'), 'tone': 'investment', 'values': [float(row['yields']) for row in flow_rows]},
            ]),
            'today': today,
            'total_offset': total_offset,
            'total_previous_offset_param': total_offset - 1,
            'total_next_offset_param': total_offset + 1,
            'is_total_anchored_today': total_offset == 0,
            'flow_offset': flow_offset,
            'flow_previous_offset_param': flow_offset - 1,
            'flow_next_offset_param': flow_offset + 1,
            'is_flow_anchored_today': flow_offset == 0,
        })
        for prefix, offset, rows in (
            ('total', total_offset, total_rows), ('flow', flow_offset, flow_rows)
        ):
            year, month = _add_months(today.year, today.month, offset)
            context[f'{prefix}_anchor_date'] = date(year, month, 1)
            context[f'{prefix}_window_start_date'] = rows[0]['date']
            context[f'{prefix}_window_end_date'] = rows[-1]['date']
        return context


class InvestmentFormMixin(LoginRequiredMixin):
    model = Investment
    form_class = InvestmentForm
    template_name = 'investments/form.html'
    success_url = reverse_lazy('investments:list')

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        refresh_snapshot = not self.object or bool(
            set(form.changed_data)
            & {'asset', 'quantity', 'unit_price', 'amount', 'ending_balance', 'fees', 'date'}
        )
        form.instance.user = self.request.user
        with transaction.atomic():
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


class InvestmentSettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'investments/settings/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = InvestmentProduct.objects.filter(
            user=self.request.user, bank__user=self.request.user
        ).select_related('bank').annotate(operation_count=Count('operations'))
        context['assets'] = Asset.objects.filter(user=self.request.user).annotate(
            operation_count=Count('operations')
        )
        return context


class SetupFormMixin(LoginRequiredMixin):
    template_name = 'investments/setup_form.html'
    success_url = reverse_lazy('investments:settings')
    entity_label = ''
    setup_description = ''
    duplicate_field = 'name'
    duplicate_message = gettext_lazy('This item already exists.')

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        action = gettext_lazy('Edit') if self.object else gettext_lazy('Add')
        context['setup_title'] = format_lazy('{} {}', action, self.entity_label)
        context['setup_description'] = self.setup_description
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            with transaction.atomic():
                return super().form_valid(form)
        except IntegrityError:
            form.add_error(self.duplicate_field, self.duplicate_message)
            return self.form_invalid(form)


class ProductFormMixin(SetupFormMixin):
    model = InvestmentProduct
    form_class = InvestmentProductForm
    entity_label = gettext_lazy('investment product')
    setup_description = gettext_lazy('Name a product and assign it to a bank you manage in Banking.')
    duplicate_message = gettext_lazy('This bank already has a product with this name.')

    def get_queryset(self):
        return super().get_queryset().filter(bank__user=self.request.user)


class InvestmentProductCreateView(ProductFormMixin, SuccessMessageMixin, CreateView):
    success_message = gettext_lazy('Investment product "%(name)s" created.')


class InvestmentProductUpdateView(ProductFormMixin, SuccessMessageMixin, UpdateView):
    success_message = gettext_lazy('Investment product "%(name)s" updated.')


class AssetFormMixin(SetupFormMixin):
    model = Asset
    form_class = AssetForm
    entity_label = gettext_lazy('asset')
    setup_description = gettext_lazy('Class describes what it is; currency describes how its unit price is quoted.')
    duplicate_field = 'code'
    duplicate_message = gettext_lazy('You already have an asset with this code.')


class AssetCreateView(AssetFormMixin, SuccessMessageMixin, CreateView):
    success_message = gettext_lazy('Asset "%(name)s" created.')


class AssetUpdateView(AssetFormMixin, SuccessMessageMixin, UpdateView):
    success_message = gettext_lazy('Asset "%(name)s" updated.')


class SetupDeleteView(LoginRequiredMixin, DeleteView):
    template_name = 'investments/settings/confirm_delete_entity.html'
    success_url = reverse_lazy('investments:settings')
    entity_label = ''

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['entity_label'] = self.entity_label
        return context

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, _('This item is used by investment operations.'))
            return redirect('investments:settings')
        messages.success(
            self.request,
            _('%(entity)s deleted.') % {'entity': self.entity_label.title()},
        )
        return response


class InvestmentProductDeleteView(SetupDeleteView):
    model = InvestmentProduct
    context_object_name = 'entity'
    entity_label = gettext_lazy('investment product')

    def get_queryset(self):
        return super().get_queryset().filter(bank__user=self.request.user)


class AssetDeleteView(SetupDeleteView):
    model = Asset
    context_object_name = 'entity'
    entity_label = gettext_lazy('asset')


class InvestmentDeleteView(LoginRequiredMixin, DeleteView):
    model = Investment
    template_name = 'investments/confirm_delete.html'
    context_object_name = 'investment'
    success_url = reverse_lazy('investments:list')

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)

    def form_valid(self, form):
        with transaction.atomic():
            cleanup_investment_ledger(self.object)
            response = super().form_valid(form)
        messages.success(self.request, _('Investment operation deleted.'))
        return response
