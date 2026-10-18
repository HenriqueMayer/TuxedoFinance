from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from banking.models import Bank
from banking.services import MissingExchangeRate, convert, latest_exchange_rate
from dashboard.selection import selection_data, attach_details
from dashboard.charts import build_bar_chart, build_line_chart
from investments.forms import (AssetForm, InvestmentForm, InvestmentProductForm,
                               InvestmentChartFilterForm, InvestmentOperationFilterForm, PriceObservationForm,
                               PriceObservationFilterForm)
from investments.forms import GuidedInvestmentForm
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation, PositionPlanningSetting
from investments.positions import get_portfolio_valuation, validate_position_history
from investments.services import (
    TIMESERIES_MONTHS,
    cleanup_investment_ledger,
    get_monthly_flow_in_base,
    get_portfolio_groups,
    get_total_in_base_timeseries,
    sync_investment_ledger,
    refresh_fx_snapshot,
    create_guided_investment,
)
from accounts.models import UserPreference
from core.navigation import ReturnContextMixin, return_url, with_return_url


def _configured_rows(user, snapshot, purpose=None):
    """Zero configuration belongs in navigation, outside financial replay/totals."""
    known = {(row['product'].pk, row['asset'].pk) for row in snapshot['positions']}
    assets = Asset.objects.filter(user=user, opening_product__user=user).select_related('opening_product__bank')
    if purpose:
        assets = assets.filter(opening_product__purpose=purpose)
    zero = Decimal('0')
    rows = []
    for asset in assets:
        if (asset.opening_product_id, asset.pk) not in known:
            rows.append({'product': asset.opening_product, 'asset': asset, 'quantity': zero,
                'balance': zero, 'remaining_cost': zero, 'average_cost': zero, 'realized_gain': zero,
                'unrealized_gain': None, 'valuation': zero, 'base_value': zero, 'deposits': zero,
                'withdrawals': zero, 'yields': zero, 'unapplied_fees': zero, 'fees': zero,
                'price_observation': None, 'baseline_unknown': False, 'history_errors': [],
                'configured_only': True})
    return rows


def _position_row(user, product, asset):
    snapshot = get_portfolio_valuation(user)
    rows = snapshot['positions'] + _configured_rows(user, snapshot)
    row = next((row for row in rows if row['product'].pk == product.pk and row['asset'].pk == asset.pk), None)
    if row is None:
        # Future operations also establish owned context, without current money.
        if not Investment.objects.filter(user=user, product=product, asset=asset).exists():
            from django.http import Http404
            raise Http404
        row = {'product': product, 'asset': asset, 'quantity': Decimal('0'), 'balance': Decimal('0'),
            'remaining_cost': Decimal('0'), 'average_cost': Decimal('0'), 'realized_gain': Decimal('0'),
            'unrealized_gain': None, 'valuation': Decimal('0'), 'price_observation': None,
            'unapplied_fees': Decimal('0'), 'baseline_unknown': False, 'history_errors': [], 'configured_only': True}
    observation = row['price_observation']
    last_date = Investment.objects.filter(user=user, product=product, asset=asset, date__lte=timezone.localdate()).order_by('-date').values_list('date', flat=True).first()
    return {**row, 'id': asset.pk, 'name': asset.name, 'code': asset.code, 'currency': asset.currency,
            'evidence_date': observation.date if observation else (last_date or asset.opening_date),
            'valuation_mode': asset.valuation_mode, 'is_archived': asset.is_archived}


def _asset_configuration_url(request, asset):
    # Restoration belongs to the owned configuration list, with its archived
    # disclosure opened before navigating to the precise asset anchor. Its
    # links let the fragment scroll instead of the boosted shell's page top.
    target = reverse('investments:settings') + '?' + urlencode({'archived': asset.pk}) + f'#asset-{asset.pk}'
    return with_return_url(target, request.get_full_path())


@login_required
def position_detail(request, product_pk, asset_pk):
    product = get_object_or_404(InvestmentProduct.objects.select_related('bank'), user=request.user,
                              bank__user=request.user, pk=product_pk)
    asset = get_object_or_404(Asset, user=request.user, pk=asset_pk)
    row = _position_row(request.user, product, asset)
    planning_enabled = PositionPlanningSetting.objects.filter(user=request.user, product=product, asset=asset).values_list('planning_enabled', flat=True).first()
    detail_url = reverse('investments:position_detail', args=[product.pk, asset.pk])
    history_url = reverse('investments:operations') + '?' + urlencode({'product': product.pk, 'asset': asset.pk})
    update_url = reverse('investments:position_update', args=[product.pk, asset.pk])
    operations = Investment.objects.filter(user=request.user, product=product, asset=asset).order_by('-date', '-created_at', '-pk')[:10]
    return render(request, 'investments/position.html', {'position': row, 'product': product, 'asset': row,
        'selected_section': 'positions', 'today': timezone.localdate(), 'history_url': history_url,
        'update_url': with_return_url(update_url, request.get_full_path()),
        'asset_edit_url': with_return_url(reverse('investments:update_asset', args=[asset.pk]), request.get_full_path()),
        'product_edit_url': with_return_url(reverse('investments:update_product', args=[product.pk]), request.get_full_path()),
        'configuration_url': _asset_configuration_url(request, asset),
        'recent_operations': operations, 'detail_url': detail_url,
        'planning_enabled': planning_enabled is not False})


@login_required
def position_update(request, product_pk, asset_pk):
    product = get_object_or_404(InvestmentProduct.objects.select_related('bank'), user=request.user,
                              bank__user=request.user, pk=product_pk)
    asset = get_object_or_404(Asset, user=request.user, pk=asset_pk)
    row = _position_row(request.user, product, asset)
    destination = return_url(request, reverse('investments:position_detail', args=[product.pk, asset.pk]))
    actions = {kind.lower(): with_return_url(reverse('investments:create') + '?' + urlencode(
        {'product': product.pk, 'asset': asset.pk, 'kind': kind}), destination) for kind in Investment.Kind.values}
    actions['price'] = with_return_url(reverse('investments:create_price') + '?' + urlencode({'asset': asset.pk}), destination)
    return render(request, 'investments/position_update.html', {'position': row, 'product': product,
        'selected_section': 'positions', 'actions': actions, 'return_url': destination,
        'configuration_url': _asset_configuration_url(request, asset)})


@login_required
@require_http_methods(['GET', 'POST'])
def guided_investment(request):
    form = GuidedInvestmentForm(request.POST or None, user=request.user)
    destination = return_url(request, reverse('investments:list'))
    if request.method == 'POST' and form.is_valid():
        try:
            product, asset = create_guided_investment(request.user, form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            if isinstance(error, IntegrityError):
                form.add_error(None, _('The institution or investment already exists. Review the configuration.'))
            else:
                mapping = {'bank': 'institution', 'name': 'name', 'code': 'code'}
                for field, errors in getattr(error, 'message_dict', {'__all__': error.messages}).items():
                    for message in errors:
                        form.add_error(mapping.get(field, field) if mapping.get(field, field) in form.fields else None, message)
        else:
            messages.success(request, _('Investment added. Existing holdings were recorded without a bank payment.'))
            return redirect(with_return_url(reverse('investments:position_detail', args=[product.pk, asset.pk]), destination))
    return render(request, 'investments/guided_form.html', {'form': form, 'return_url': destination})


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


def _investment_setup(user):
    has_bank = Bank.objects.filter(user=user).exists()
    has_products = InvestmentProduct.objects.filter(user=user, bank__user=user).exists()
    has_assets = Asset.objects.filter(user=user, is_archived=False).exists()
    return {
        'has_bank': has_bank,
        'has_products': has_products,
        'has_assets': has_assets,
        'setup_complete': has_bank and has_products and has_assets,
    }


def _historical_fx_issues(issues, base):
    rows = {}
    for issue in issues:
        operation = issue.get('operation')
        asset = operation.asset if operation else issue['asset']
        key = (bool(operation), operation.pk if operation else asset.pk, issue['date'])
        row = {
            'asset': asset, 'date': issue['date'], 'currency': asset.currency,
            'base_currency': base,
            'rate_url': reverse('banking:exchange_rate_create') + '?' + urlencode({
                'from_currency': asset.currency, 'to_currency': base,
                'effective_date': issue['date'].isoformat(),
            }),
        }
        if operation:
            row['operation_url'] = reverse('investments:update', args=[operation.pk])
            row['snapshot_target'] = operation.fx_target_currency
            has_evidence = operation.fx_snapshot_status in {
                Investment.FxSnapshotStatus.CAPTURED, Investment.FxSnapshotStatus.RECONSTRUCTED,
            }
            row['reason'] = 'base' if has_evidence and operation.fx_target_currency != base else 'snapshot'
            if not operation.fx_target_currency:
                row['reason'] = 'rate'
        else:
            row['reason'] = 'opening'
        rows[key] = row
    return sorted(rows.values(), key=lambda row: (row['date'], row['currency'], row['asset'].name))


class InvestmentListView(LoginRequiredMixin, TemplateView):
    template_name = 'investments/list.html'

    def get_section(self):
        scope = self.request.GET.get('scope', self.request.GET.get('section', 'all'))
        return scope if scope in ('portfolio', 'cash') else 'all'

    def get_purpose(self):
        return {'cash': InvestmentProduct.Purpose.MONTHLY_CASH,
                'portfolio': InvestmentProduct.Purpose.INVESTMENT}.get(self.get_section())

    def get(self, request, *args, **kwargs):
        if request.headers.get('HX-Target') == 'investments-charts':
            # Older open pages still request chart islands from the former
            # combined workspace; preserve their scope without computing cash.
            query = request.GET.copy()
            query.setdefault('scope', 'cash' if query.get('section') == 'cash' else 'portfolio')
            request.GET = query
            return InvestmentChartsView.as_view()(request, *args, **kwargs)
        movement_request = request.headers.get('HX-Target') == 'investment-movements'
        legacy_search = 'section' in request.GET and 'q' in request.GET and 'scope' not in request.GET
        if movement_request or legacy_search or any(key in request.GET for key in ('page', 'kind', 'bank', 'product', 'asset', 'tab')):
            query = request.GET.copy()
            if query.get('section') != 'cash':
                query['section'] = 'portfolio'
            return redirect(f"{reverse_lazy('investments:operations')}?{query.urlencode()}")
        return super().get(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.headers.get('HX-Request') == 'true':
            if self.request.headers.get('HX-Target') == 'investments-charts':
                return ['investments/_investments_charts.html']
            if self.request.headers.get('HX-Target') == 'investment-position-list':
                return ['investments/_position_list.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update(_investment_setup(user))
        base = UserPreference.for_user(user).base_currency
        today = timezone.localdate()
        total = Decimal('0')
        missing = set()
        native_totals = {}
        rates = {}
        snapshot = get_portfolio_valuation(user, purpose=self.get_purpose(), base_currency=base)
        display_snapshot = {**snapshot, 'positions': snapshot['positions'] + _configured_rows(user, snapshot, self.get_purpose())}
        portfolio_groups = get_portfolio_groups(user, purpose=self.get_purpose(), snapshot=display_snapshot)
        last_dates = {(row['product_id'], row['asset_id']): row['last_date'] for row in
            Investment.objects.filter(user=user, date__lte=today).values('product_id', 'asset_id').annotate(last_date=Max('date'))}
        planning_flags = {(product, asset): enabled for product, asset, enabled in
            PositionPlanningSetting.objects.filter(user=user).values_list('product_id', 'asset_id', 'planning_enabled')}
        # Current positions must not inherit missing FX from an unrelated
        # historical chart window. Zero balances need no exchange rate.
        for bank in portfolio_groups:
            for product in bank['products']:
                product['create_url'] = with_return_url(
                    reverse('investments:create') + '?' + urlencode({'product': product['id']}),
                    self.request.get_full_path(), fragment=f"product-{product['id']}")
                product['edit_url'] = with_return_url(reverse('investments:update_product', args=[product['id']]),
                    self.request.get_full_path(), fragment=f"product-{product['id']}")
                for asset in product['assets']:
                    asset['anchor'] = f"position-{product['id']}-{asset['id']}"
                    asset['planning_enabled'] = planning_flags.get((product['id'], asset['id']), True)
                    asset['detail_url'] = reverse('investments:position_detail', args=[product['id'], asset['id']])
                    asset['history_url'] = reverse('investments:operations') + '?' + urlencode({'product': product['id'], 'asset': asset['id']})
                    asset['update_url'] = with_return_url(reverse('investments:position_update', args=[product['id'], asset['id']]),
                        self.request.get_full_path(), fragment=asset['anchor'])
                    asset['mobile_update_url'] = with_return_url(reverse('investments:position_update', args=[product['id'], asset['id']]),
                        self.request.get_full_path(), fragment=asset['anchor'] + '-mobile')
                    opening_date = asset['asset'].opening_date
                    asset['evidence_date'] = last_dates.get((product['id'], asset['id']), opening_date)
                    if asset['price_observation']:
                        asset['evidence_label'] = _('Local unit price')
                        asset['evidence_date'] = asset['price_observation'].date
                    elif asset.get('configured_only'):
                        asset['evidence_label'] = _('No current position') if opening_date else _('Ready for the first operation')
                    else:
                        asset['evidence_label'] = _('Recorded balance') if asset['valuation_mode'] == 'MONETARY' else _('At remaining acquisition cost')
                    for name, fragment in (('action_urls', asset['anchor']), ('mobile_action_urls', asset['anchor'] + '-mobile')):
                        asset[name] = {
                            kind.lower(): with_return_url(
                                reverse('investments:create') + '?' + urlencode({'product': product['id'], 'asset': asset['id'], 'kind': kind}),
                                self.request.get_full_path(), fragment=fragment)
                            for kind in Investment.Kind.values
                        }
                        asset[name]['price'] = with_return_url(
                            reverse('investments:create_price') + '?' + urlencode({'asset': asset['id']}),
                            self.request.get_full_path(), fragment=fragment)
                    currency = asset['currency']
                    native_totals[currency] = native_totals.get(currency, Decimal('0')) + asset['valuation']
                    try:
                        asset['base_balance'] = asset['base_value']
                        if asset['base_balance'] is None:
                            missing.add(currency)
                            continue
                        total += asset['base_balance']
                        if currency != base and asset['valuation'] and currency not in rates:
                            rate = latest_exchange_rate(user, currency, base) or latest_exchange_rate(user, base, currency)
                            rates[currency] = rate
                    except MissingExchangeRate:
                        asset['base_balance'] = None
                        missing.add(currency)
        # Archiving hides current position rows, not money: value every holding
        # before filtering the display, and keep accounting/history queries intact.
        visible_groups = []
        has_archived_positions = False
        position_rows = []
        query = self.request.GET.get('q', '').strip()
        for bank in portfolio_groups:
            visible_products = []
            for product in bank['products']:
                active_assets = [asset for asset in product['assets'] if not asset['is_archived']]
                has_archived_positions |= len(active_assets) != len(product['assets'])
                assets = [asset for asset in active_assets if not query or query.casefold() in
                          ' '.join((asset['name'], asset['code'], product['name'], bank['name'])).casefold()]
                position_rows.extend({**asset, 'bank_name': bank['name'], 'product_name': product['name'],
                                      'purpose': product['purpose']} for asset in assets)
                if assets:
                    visible_products.append({**product, 'assets': assets})
            if visible_products:
                visible_groups.append({**bank, 'products': visible_products})
        context.update({
            'selected_section': 'positions',
            'position_scope': self.get_section(),
            'position_rows': position_rows,
            'position_count': len(position_rows),
            'search_query': query,
            'portfolio_groups': visible_groups,
            'has_archived_positions': has_archived_positions,
            'simulated_total': total.quantize(Decimal('0.01')),
            'missing_rate_currencies': sorted(missing),
            'native_totals': sorted(native_totals.items()),
            'valuation_rates': list(rates.values()),
            'base_currency': base,
            'has_investments': bool(portfolio_groups),
            'today': today,
            'portfolio_snapshot': snapshot,
        })
        return context


class InvestmentChartsView(InvestmentListView):
    template_name = 'investments/charts.html'

    def get(self, request, *args, **kwargs):
        return TemplateView.get(self, request, *args, **kwargs)

    def get_purpose(self):
        return {'portfolio': InvestmentProduct.Purpose.INVESTMENT,
                'cash': InvestmentProduct.Purpose.MONTHLY_CASH}.get(self.request.GET.get('scope'))

    def get_context_data(self, **kwargs):
        context = TemplateView.get_context_data(self, **kwargs)
        user = self.request.user
        context.update(_investment_setup(user))
        base = UserPreference.for_user(user).base_currency
        today = timezone.localdate()
        purpose = self.get_purpose()
        total_offset = _parse_offset(self.request, 'total_offset')
        flow_offset = _parse_offset(self.request, 'flow_offset')
        fx_issues = []
        total_rows, total_missing = get_total_in_base_timeseries(
            user, base, months=TIMESERIES_MONTHS, offset=total_offset,
            purpose=purpose, fx_issues=fx_issues,
        )
        flow_rows, flow_missing = get_monthly_flow_in_base(
            user, base, months=TIMESERIES_MONTHS, offset=flow_offset,
            purpose=purpose, fx_issues=fx_issues,
        )
        context.update({
            'selected_section': 'charts',
            'base_currency': base,
            'chart_missing_rate_currencies': sorted(set(total_missing) | set(flow_missing)),
            'chart_fx_issues': _historical_fx_issues(fx_issues, base),
            'chart_total': build_line_chart(total_rows, [float(row['total']) for row in total_rows]),
            'chart_flow': build_bar_chart(flow_rows, [
                {'name': _('Deposits'), 'tone': 'income', 'values': [float(row['deposits']) for row in flow_rows]},
                {'name': _('Withdrawals'), 'tone': 'expense', 'values': [float(row['withdrawals']) for row in flow_rows]},
                {'name': _('Yields'), 'tone': 'investment', 'values': [float(row['yields']) for row in flow_rows]},
            ]),
            'today': today,
            'portfolio_snapshot': get_portfolio_valuation(user, purpose=purpose, base_currency=base),
            'chart_unknown_baselines': any(row['snapshot']['unknown_baselines'] for row in total_rows),
            'chart_missing_prices': any(row['snapshot']['missing_prices'] for row in total_rows),
            'chart_history_errors': any(row['snapshot']['history_errors'] for row in total_rows),
            'performance_rows': total_rows,
            'total_offset': total_offset,
            'total_previous_offset_param': total_offset - 1,
            'total_next_offset_param': total_offset + 1,
            'is_total_anchored_today': total_offset == 0,
            'flow_offset': flow_offset,
            'flow_previous_offset_param': flow_offset - 1,
            'flow_next_offset_param': flow_offset + 1,
            'is_flow_anchored_today': flow_offset == 0,
        })
        context['total_selection'] = selection_data(total_rows, [('total', _('Total'))],
            mode='change', opening=total_rows[0]['opening_balance'], chart=context['chart_total'])
        context['flow_selection'] = selection_data(flow_rows, [
            ('deposits', _('Deposits')), ('withdrawals', _('Withdrawals')), ('yields', _('Yields')),
        ], chart=context['chart_flow'])
        attach_details(context['total_selection'], user, 'portfolio', total_rows, ['total'], purpose=purpose, opening_date=total_rows[0]['date'].isoformat())
        attach_details(context['flow_selection'], user, 'portfolio-flow', flow_rows, ['deposits', 'withdrawals', 'yields'], purpose=purpose)
        for prefix, offset, rows in (
            ('total', total_offset, total_rows), ('flow', flow_offset, flow_rows)
        ):
            year, month = _add_months(today.year, today.month, offset)
            context[f'{prefix}_anchor_date'] = date(year, month, 1)
            context[f'{prefix}_window_start_date'] = rows[0]['date']
            context[f'{prefix}_window_end_date'] = rows[-1]['date']
        context['chart_scope'] = self.request.GET.get('scope', '') if purpose else ''
        context['chart_filter'] = InvestmentChartFilterForm(initial={'scope': context['chart_scope']})
        return context


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


class InvestmentSettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'investments/settings/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_investment_setup(self.request.user))
        context['products'] = InvestmentProduct.objects.filter(
            user=self.request.user, bank__user=self.request.user
        ).select_related('bank').annotate(operation_count=Count('operations')).order_by('bank__name', 'bank_id', 'name')
        assets = list(Asset.objects.filter(user=self.request.user).annotate(
            operation_count=Count('operations')
        ))
        context['assets'] = [asset for asset in assets if not asset.is_archived]
        context['archived_assets'] = [asset for asset in assets if asset.is_archived]
        context['show_archived_assets'] = any(
            str(asset.pk) == self.request.GET.get('archived') for asset in context['archived_assets']
        )
        return context


class SetupFormMixin(ReturnContextMixin, LoginRequiredMixin):
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
    setup_description = gettext_lazy('Name a product and assign it to a bank registered in Accounts.')
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


class SetupDeleteView(ReturnContextMixin, LoginRequiredMixin, DeleteView):
    template_name = 'investments/settings/confirm_delete_entity.html'
    success_url = reverse_lazy('investments:settings')
    entity_label = ''

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['entity_label'] = self.entity_label
        if isinstance(self.object, Asset):
            context['delete_warning'] = self.object.deletion_block_reason
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, _('This item has an opening position or investment history and cannot be deleted.'))
            return redirect(self.get_return_url())
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


def _set_asset_archived(request, pk, archived):
    asset = get_object_or_404(Asset, pk=pk, user=request.user)
    asset.is_archived = archived
    asset.save(update_fields=['is_archived', 'updated_at'])
    message = (
        _('Asset "%(name)s" archived. Its positions and history remain available.') if archived
        else _('Asset "%(name)s" restored. It is available for new operations.')
    )
    messages.success(request, message % {'name': asset.name})
    url = reverse('investments:settings')
    if archived:
        url += '?' + urlencode({'archived': asset.pk})
    # Native submissions land on the changed asset; same-page HTMX keeps focus
    # on its stable action button, which becomes Restore after archiving.
    return redirect(f'{url}#asset-{asset.pk}')


@login_required
@require_POST
def archive_asset(request, pk):
    return _set_asset_archived(request, pk, True)


@login_required
@require_POST
def restore_asset(request, pk):
    return _set_asset_archived(request, pk, False)


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
