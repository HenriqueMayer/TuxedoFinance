"""Private planning workspaces: calculations read records, explicit saves write drafts."""
import json
import re
from copy import deepcopy
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.models import UserPreference
from sandbox.forms import (
    DraftNameForm, SalarySandboxForm, YieldSimulationForm, parse_month,
    variable_rows, variables_from_data,
)
from sandbox.models import ScenarioDraft
from sandbox.planning import commitment_snapshot, simulate_yield, snapshot_total
from dashboard.services import add_months
from sandbox.services import BudgetInput, CltScenario, apply_variables, build_budget, calculate_clt, payroll_brackets
from sandbox.tax_rules import get_tax_rules


def _data_from_payload(payload):
    data = QueryDict(mutable=True)
    for key, values in payload.get('inputs', {}).items():
        data.setlist(key, values)
    return data


def _row_action(data, action):
    """Submit buttons keep adding/removing repeated rows usable without JS."""
    if not action.startswith(('add_', 'remove_')):
        return data
    copy = data.copy()
    for prefix in ('variable',):
        rows = variable_rows(data, prefix)
        if action == f'add_{prefix}' and len(rows) < 20:
            rows.append({})
        if action.startswith(f'remove_{prefix}_'):
            try:
                rows.pop(int(action.rsplit('_', 1)[1]))
            except (ValueError, IndexError):
                pass
        for name, key in (('label', 'label'), ('type', 'value_type'), ('value', 'value')):
            copy.setlist(f'{prefix}_{name}', [row.get(key, 'currency' if name == 'type' else '') for row in rows])
    return copy


def _expense_forecast(user, month, snapshot=None):
    # New plans follow the Report statement month; saved legacy plans retain their captured basis.
    snapshot = snapshot or commitment_snapshot(user, month, month_basis="reference_month")
    month_key = month.strftime('%Y-%m')
    rows = [row for row in snapshot['rows'] if row[snapshot.get('month_basis', 'payment_date')].startswith(month_key)]
    try:
        total = snapshot_total(snapshot, month_key)
        error = None
    except ValidationError as exc:
        total = None
        error = exc.message
    return snapshot, {'month': month, 'total': total, 'count': len(rows), 'error': error}


def _calculate_budget(form, forecast, *, apply_clt=True):
    if not form.is_valid():
        return None
    data = form.cleaned_data
    if forecast['total'] is None:
        form.add_error(None, forecast['error'])
        return None
    variables = variables_from_data(form.data, 'variable')
    budget = BudgetInput(fixed_bills=forecast['total'], custom_variables=variables)
    gross = data['gross_salary']
    rules = get_tax_rules()
    scenario = CltScenario(
        gross, dependents=data.get('clt_dependents') or 0,
        pension=data.get('clt_pension') or Decimal('0'),
        vt_enabled=bool(data.get('clt_transport')), vt_cost=data.get('clt_transport') or Decimal('0'),
        food_employee=data.get('clt_food') or Decimal('0'),
        health_employee=data.get('clt_health') or Decimal('0'),
        other_deductions=data.get('clt_other') or Decimal('0'),
    )
    payroll = calculate_clt(scenario, rules).ordinary if apply_clt else None
    income = payroll.net if payroll else gross
    return {
        'mode': 'simple',
        'budget': build_budget(income, budget, custom_variable_base=gross),
        'gross': gross,
        'payroll': payroll,
        'tax_bands': payroll_brackets(payroll, rules) if payroll else None,
        'tax_rule_year': get_tax_rules().year if payroll else None,
        'variables': apply_variables(gross, variables),
        'forecast': forecast,
    }


def _calculate_yield(form):
    if not form.is_valid():
        return None
    data = form.cleaned_data
    try:
        return simulate_yield(initial=data['initial_balance'], start_month=data['start_month'], months=data['months'],
                              rate=data['rate'], rate_period=data['rate_period'], contribution=data['contribution'],
                              withdrawal=data['withdrawal'], overrides=data['overrides'])
    except ValidationError as error:
        form.add_error(None, error)
        return None


def _canonical_inputs(data, kind):
    """Normalize individually valid values; retain incomplete raw input verbatim."""
    fields = (SalarySandboxForm if kind == 'budget' else YieldSimulationForm).base_fields
    inputs = {}
    for key in data:
        field = fields.get(key)
        if field is None and re.fullmatch(r'(contribution|withdrawal)_\d{1,3}', key):
            field = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
        if field is None:
            continue
        raw = data.get(key, '')
        try:
            value = field.clean(raw)
            if key in ('planning_month', 'start_month'):
                value = parse_month(raw).strftime('%Y-%m')
            elif isinstance(value, Decimal):
                value = format(value.quantize(Decimal(1).scaleb(-field.decimal_places)), 'f')
            elif isinstance(value, bool):
                value = 'on' if value else ''
            else:
                value = str(value) if value is not None else ''
        except ValidationError:
            value = raw
        inputs[key] = [value]
    for prefix in ('variable',):
        for name in ('label', 'type', 'value'):
            key = f'{prefix}_{name}'
            if key in data:
                inputs[key] = data.getlist(key)
        for index, row in enumerate(variable_rows(data, prefix)):
            if any(index >= len(inputs.get(f'{prefix}_{name}', [])) for name in ('label', 'type', 'value')):
                continue
            single = QueryDict(mutable=True)
            for name, key in (('label', 'label'), ('type', 'value_type'), ('value', 'value')):
                single.setlist(f'{prefix}_{name}', [row[key]])
            try:
                values = variables_from_data(single, prefix)
            except ValidationError:
                continue
            if values:
                inputs[f'{prefix}_label'][index] = values[0].label
                inputs[f'{prefix}_value'][index] = format(values[0].value.quantize(Decimal('.01')), 'f')
    return inputs


def _canonical_snapshot(snapshot):
    if not snapshot:
        return snapshot
    snapshot = deepcopy(snapshot)
    field = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
    for row in snapshot['rows']:
        try:
            value = field.clean(row.get('override', ''))
            if value is not None:
                row['override'] = format(value.quantize(Decimal('.01')), 'f')
        except ValidationError:
            pass
    return snapshot


def _save(request, data, kind, snapshot, draft, result):
    name_form = DraftNameForm(data)
    if not name_form.is_valid():
        return None, name_form
    inputs = _canonical_inputs(data, kind)
    if len(json.dumps(inputs)) > 64000:
        name_form.add_error(None, _('This draft is too large. Reduce the number or length of its inputs.'))
        return None, name_form
    preference = UserPreference.for_user(request.user)
    input_format = (draft.payload.get('input_format') if draft else None) or {
        'date_order': preference.date_format, 'month': 'YYYY-MM', 'decimal': '.',
    }
    payload = {'schema_version': 1, 'calculation_version': 2 if kind == 'budget' else 1, 'input_format': input_format,
               'inputs': inputs, 'snapshot': _canonical_snapshot(snapshot), 'complete': result is not None,
               'tax_rule_year': get_tax_rules().year}
    if draft is None:
        draft = ScenarioDraft(user=request.user, kind=kind)
    draft.name = name_form.cleaned_data['draft_name']
    draft.payload = payload
    draft.save()
    messages.success(request, _('Draft saved. Your financial records have not changed.'))
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse()
        response['HX-Redirect'] = reverse('sandbox:draft_detail', kwargs={'pk': draft.pk})
        return response, name_form
    return redirect('sandbox:draft_detail', pk=draft.pk), name_form


def _workspace(request, kind='budget', draft=None):
    posted = request.method == 'POST'
    action = request.POST.get('action', 'calculate') if posted else ''
    data = request.POST if posted else _data_from_payload(draft.payload) if draft else None
    if posted:
        data = _row_action(data, action)
        if kind == 'budget' and action in ('previous_month', 'next_month'):
            data = data.copy()
            # Move the month in the submitted form so unsaved salary/rows survive native and HTMX requests.
            try:
                month = parse_month(data.get('planning_month'))
                year, number = add_months(month.year, month.month, -1 if action == 'previous_month' else 1)
                data['planning_month'] = parse_month(f'{year:04d}-{number:02d}').strftime('%Y-%m')
            except ValidationError:
                pass
            action = 'forecast'
    form_class = SalarySandboxForm if kind == 'budget' else YieldSimulationForm
    form_kwargs = {'data': data}
    if kind == 'budget':
        form_kwargs['require_salary'] = action not in ('forecast', 'add_variable') and not action.startswith('remove_')
    form = form_class(**form_kwargs)
    snapshot = None
    forecast = None
    if kind == 'budget':
        raw_month = (data or {}).get('planning_month') or timezone.localdate().strftime('%Y-%m')
        try:
            month = parse_month(raw_month)
        except ValidationError:
            month = timezone.localdate().replace(day=1)
        saved_snapshot = deepcopy(draft.payload.get('snapshot')) if draft and not posted else None
        snapshot, forecast = _expense_forecast(request.user, month, saved_snapshot)
    result = None
    if data is not None and not action.startswith(('add_', 'remove_')) and action not in ('forecast', 'rows'):
        # Opening a legacy draft preserves its gross-based result; deliberate recalculation uses CLT.
        apply_clt = posted or not draft or draft.payload.get('calculation_version', 1) >= 2
        result = _calculate_budget(form, forecast, apply_clt=apply_clt) if kind == 'budget' else _calculate_yield(form)
    name_form = DraftNameForm(initial={'draft_name': draft.name if draft else ''})
    if posted and action == 'save':
        response, name_form = _save(request, data, kind, snapshot, draft, result)
        if response:
            return response
    elif data is not None and data.get('draft_name'):
        name_form = DraftNameForm(initial={'draft_name': data['draft_name']})
    context = {'form': form, 'result': result, 'kind': kind, 'draft': draft, 'name_form': name_form,
               'rules': get_tax_rules(), 'snapshot': snapshot, 'forecast': forecast,
               'workspace_url': request.path, 'CURRENCY_SYMBOL': 'R$',
               'draft_save_open': bool(draft or name_form.errors)}
    if kind == 'budget':
        clt_names = [name for name in form.fields if name.startswith('clt_')]
        context['clt_fields'] = [form[name] for name in clt_names]
        settings_requested = (data or {}).get('clt_settings_open')
        context['clt_settings_open'] = form.is_bound and (
            any(form.errors.get(name) for name in clt_names)
            or (settings_requested == '1' if settings_requested is not None
                else any(form.cleaned_data.get(name) for name in clt_names))
        )
        context['tax_bands_open'] = action == 'tax_bands' or (data or {}).get('tax_bands_open') == '1'
        # Suggestions belong only to a new workspace, never to submitted or saved rows.
        context['variable_rows'] = (
            [{'label': _('Emergency reserve'), 'value_type': 'currency', 'value': '0.00'},
             {'label': _('Investment'), 'value_type': 'currency', 'value': '0.00'}]
            if data is None else variable_rows(data, 'variable', include_blank=True)
        )
        template = 'sandbox/_workspace.html' if posted and data.get('response_mode') == 'fragment' else 'sandbox/index.html'
    else:
        try:
            count = min(max(int((data or {}).get('months', 12)), 1), 120)
        except (TypeError, ValueError):
            count = 12
        context['override_rows'] = [{'index': index, 'number': index + 1,
            'contribution': (data or {}).get(f'contribution_{index}', ''),
            'withdrawal': (data or {}).get(f'withdrawal_{index}', '')} for index in range(count)]
        context['overrides_open'] = action == 'rows' or any(
            row['contribution'] or row['withdrawal'] for row in context['override_rows']
        )
        context['simulation_currency'] = (data or {}).get('currency', 'BRL')
        template = 'sandbox/_simulation_result.html' if posted and data.get('response_mode') == 'result' else 'sandbox/simulation.html'
    return render(request, template, context)


@login_required
def index(request):
    return _workspace(request)


@login_required
def simulation(request):
    return _workspace(request, kind='yield')


@login_required
def draft_detail(request, pk):
    draft = get_object_or_404(ScenarioDraft, user=request.user, pk=pk)
    return _workspace(request, draft.kind, draft)


@login_required
def drafts(request):
    return render(request, 'sandbox/drafts.html', {'drafts': ScenarioDraft.objects.filter(user=request.user)})


@login_required
@require_POST
def draft_duplicate(request, pk):
    draft = get_object_or_404(ScenarioDraft, user=request.user, pk=pk)
    copy = ScenarioDraft.objects.create(user=request.user, kind=draft.kind,
        name=(_('Copy of %(name)s') % {'name': draft.name})[:120], payload=deepcopy(draft.payload))
    return redirect('sandbox:draft_detail', pk=copy.pk)


@login_required
def draft_delete(request, pk):
    draft = get_object_or_404(ScenarioDraft, user=request.user, pk=pk)
    if request.method == 'POST':
        draft.delete()
        return redirect('sandbox:drafts')
    return render(request, 'sandbox/confirm_delete.html', {'draft': draft})


@login_required
def compare(request):
    if len(request.GET.getlist('draft')) > 3:
        messages.warning(request, _('Only the first three selected drafts are shown.'))
    ids = request.GET.getlist('draft')[:3]
    scenarios = []
    for pk in dict.fromkeys(ids):
        if not pk.isdigit():
            continue
        draft = get_object_or_404(ScenarioDraft, user=request.user, pk=pk)
        data = _data_from_payload(draft.payload)
        form = (SalarySandboxForm if draft.kind == 'budget' else YieldSimulationForm)(data=data)
        if draft.kind == 'budget':
            # Move the month in the submitted form so unsaved salary/rows survive native and HTMX requests.
            try:
                month = parse_month(data.get('planning_month'))
            except ValidationError:
                month = timezone.localdate().replace(day=1)
            _saved_snapshot, forecast = _expense_forecast(
                request.user, month, deepcopy(draft.payload.get('snapshot')),
            )
            result = _calculate_budget(form, forecast, apply_clt=draft.payload.get('calculation_version', 1) >= 2)
        else:
            result = _calculate_yield(form)
        scenarios.append({'draft': draft, 'result': result,
                          'currency': 'BRL' if draft.kind == 'budget' else data.get('currency'),
                          'month': data.get('planning_month') if draft.kind == 'budget' else data.get('start_month'),
                          'months': '1' if draft.kind == 'budget' else data.get('months'),
                          'initial': data.get('gross_salary') if draft.kind == 'budget' else data.get('initial_balance'),
                          'rate': data.get('rate'), 'rate_period': data.get('rate_period')})
    return render(request, 'sandbox/compare.html', {'scenarios': scenarios})
