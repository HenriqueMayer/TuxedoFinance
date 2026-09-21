"""Private planning workspaces: calculations read records, explicit saves write drafts."""
import json
import re
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.models import UserPreference
from sandbox.forms import (
    DraftNameForm, SalarySandboxForm, YieldSimulationForm, budget_from_form,
    clt_scenario_from_form, parse_month, variable_rows, variables_from_data,
)
from sandbox.models import ScenarioDraft
from sandbox.planning import add_months, commitment_snapshot, merge_snapshot, simulate_yield, snapshot_total
from sandbox.services import apply_variables, build_budget, calculate_clt, calculate_manual
from sandbox.tax_rules import get_tax_rules

SNAPSHOT_SALT = 'sandbox.commitments.v1'


def _data_from_payload(payload):
    data = QueryDict(mutable=True)
    for key, values in payload.get('inputs', {}).items():
        data.setlist(key, values)
    return data


def _snapshot_token(snapshot):
    return signing.dumps(snapshot, salt=SNAPSHOT_SALT, compress=True) if snapshot else ''


def _load_snapshot(token, user):
    if not token:
        return None
    try:
        snapshot = signing.loads(token, salt=SNAPSHOT_SALT)
        if snapshot.get('user_id') != user.pk:
            raise signing.BadSignature
        return snapshot
    except (signing.BadSignature, ValueError, AttributeError):
        raise ValidationError(_('This commitment snapshot is invalid. Reload your draft or capture commitments again.'))


def _apply_snapshot_edits(snapshot, data):
    if not snapshot:
        return None
    snapshot = deepcopy(snapshot)
    for index, row in enumerate(snapshot['rows']):
        if f'commitment_present_{index}' not in data:
            continue
        row['included'] = data.get(f'commitment_include_{index}') == 'on'
        row['override'] = data.get(f'commitment_amount_{index}', '').strip()
    return snapshot


def _row_action(data, action):
    """Submit buttons keep adding/removing repeated rows usable without JS."""
    if not action.startswith(('add_', 'remove_')):
        return data
    copy = data.copy()
    for prefix in ('deduction', 'variable'):
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


def _calculate_budget(form, snapshot):
    if not form.is_valid():
        return None
    data = form.cleaned_data
    if data.get('use_clt'):
        clt = calculate_clt(clt_scenario_from_form(form))
        income = clt.ordinary.net
        result = {'mode': 'clt', 'clt': clt}
    else:
        manual = calculate_manual(data['gross_salary'], variables_from_data(form.data, 'deduction'))
        income = manual.monthly_net
        result = {'mode': 'manual', 'manual': manual}
    budget = budget_from_form(form)
    if data['expense_basis'] == 'recorded':
        if not snapshot:
            form.add_error(None, _('Capture and review commitments before calculating this plan.'))
            return None
        month = data['planning_month'].strftime('%Y-%m')
        if not snapshot['start_month'] <= month < add_months(parse_month(snapshot['start_month']), 12).strftime('%Y-%m'):
            form.add_error('planning_month', _('This month is outside the captured 12-month window. Refresh the commitments.'))
            return None
        try:
            amount = snapshot_total(snapshot, month)
        except ValidationError as error:
            form.add_error(None, error)
            return None
        budget = replace(budget, fixed_bills=amount, fixed_percent=0)
        result['recorded'] = True
    result['budget'] = build_budget(income, budget)
    result['variables'] = apply_variables(max(income, 0), budget.custom_variables)
    return result


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
    for prefix in ('variable', 'deduction'):
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
    payload = {'schema_version': 1, 'calculation_version': 1, 'input_format': input_format,
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
    form_class = SalarySandboxForm if kind == 'budget' else YieldSimulationForm
    initial = {'expense_basis': 'recorded'} if request.GET.get('basis') == 'recorded' else {}
    form = form_class(data=data, initial=initial)
    snapshot = deepcopy(draft.payload.get('snapshot')) if draft else None
    preview = None
    snapshot_error = None
    if posted:
        try:
            snapshot = _apply_snapshot_edits(_load_snapshot(data.get('snapshot_token'), request.user), data)
            if action == 'apply_refresh':
                candidate = _load_snapshot(data.get('preview_token'), request.user)
                if candidate is None:
                    raise ValidationError(_('Capture commitments before applying a refresh.'))
                snapshot = merge_snapshot(snapshot, candidate)
            elif action == 'refresh':
                month = parse_month(data.get('planning_month', ''))
                preview = merge_snapshot(snapshot, commitment_snapshot(request.user, month))
        except ValidationError as error:
            snapshot_error = error
    result = None
    if data is not None and not action.startswith(('add_', 'remove_')) and action not in ('refresh', 'apply_refresh', 'cancel_refresh', 'rows'):
        result = _calculate_budget(form, snapshot) if kind == 'budget' else _calculate_yield(form)
    if snapshot_error:
        form.is_valid()
        form.add_error(None, snapshot_error)
        result = None
    name_form = DraftNameForm(initial={'draft_name': draft.name if draft else ''})
    if posted and action == 'save' and snapshot_error is None:
        response, name_form = _save(request, data, kind, snapshot, draft, result)
        if response:
            return response
    elif data is not None and data.get('draft_name'):
        name_form = DraftNameForm(initial={'draft_name': data['draft_name']})
    context = {'form': form, 'result': result, 'kind': kind, 'draft': draft, 'name_form': name_form,
               'rules': get_tax_rules(), 'snapshot': snapshot, 'snapshot_token': _snapshot_token(snapshot),
               'refresh_preview': preview, 'preview_token': _snapshot_token(preview),
               'workspace_url': request.path, 'CURRENCY_SYMBOL': 'R$',
               'fixed_cost_result_label': _('Recorded commitments') if result and kind == 'budget' and result.get('recorded') else _('Fixed costs target'),
               'snapshot_captured': datetime.fromisoformat(snapshot['captured_at']) if snapshot else None}
    if preview:
        context['refresh_preview'] = {**preview, 'rows': [
            {**row, 'due_date': date.fromisoformat(row['payment_date'])} for row in preview['rows']
        ]}
    if kind == 'budget':
        context['deduction_rows'] = variable_rows(data, 'deduction', include_blank=True)
        context['variable_rows'] = variable_rows(data, 'variable')
        # Funding and hypothetical salary remain separate; no salary is added to bank cash.
        from banking.services import get_planning_availability
        context['availability'] = get_planning_availability(request.user)
        context['commitment_months'] = _commitment_months(snapshot)
        template = 'sandbox/_workspace.html' if posted and data.get('response_mode') == 'fragment' else 'sandbox/index.html'
    else:
        try:
            count = min(max(int((data or {}).get('months', 12)), 1), 120)
        except (TypeError, ValueError):
            count = 12
        context['override_rows'] = [{'index': index, 'number': index + 1,
            'contribution': (data or {}).get(f'contribution_{index}', ''),
            'withdrawal': (data or {}).get(f'withdrawal_{index}', '')} for index in range(count)]
        context['simulation_currency'] = (data or {}).get('currency', 'BRL')
        template = 'sandbox/_simulation_result.html' if posted and data.get('response_mode') == 'result' else 'sandbox/simulation.html'
    return render(request, template, context)


def _commitment_months(snapshot):
    if not snapshot:
        return []
    start = parse_month(snapshot['start_month'])
    groups = []
    for index in range(12):
        month = add_months(start, index)
        rows = []
        for row_index, row in enumerate(snapshot['rows']):
            if row['payment_date'].startswith(month.strftime('%Y-%m')):
                rows.append({**row, 'index': row_index, 'due_date': date.fromisoformat(row['payment_date'])})
        try:
            total = snapshot_total(snapshot, month.strftime('%Y-%m'))
        except ValidationError:
            total = None
        groups.append({'month': month, 'rows': rows, 'total': total})
    return groups


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
        result = _calculate_budget(form, draft.payload.get('snapshot')) if draft.kind == 'budget' else _calculate_yield(form)
        scenarios.append({'draft': draft, 'result': result,
                          'currency': 'BRL' if draft.kind == 'budget' else data.get('currency'),
                          'month': data.get('planning_month') if draft.kind == 'budget' else data.get('start_month'),
                          'months': '1' if draft.kind == 'budget' else data.get('months'),
                          'initial': data.get('gross_salary') if draft.kind == 'budget' else data.get('initial_balance'),
                          'rate': data.get('rate'), 'rate_period': data.get('rate_period')})
    return render(request, 'sandbox/compare.html', {'scenarios': scenarios})
