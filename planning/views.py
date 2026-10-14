# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.navigation import return_url
from planning.forms import CategoryBudgetForm, FinancialGoalForm, GoalCreationForm, GoalAllocationForm, MonthForm, SignalSettingsForm
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalDecision
from planning.monthly import monthly_outlook
from transactions.services import sync_user_ledger
from planning.services import budget_progress, copy_previous_budgets, create_goal, goal_progress, local_signals, save_allocation, save_budget, set_goal_archived, signal_settings


def _month(request):
    form = MonthForm(request.GET or None)
    month = timezone.localdate().replace(day=1)
    if form.is_bound and form.is_valid():
        month = form.cleaned_data['month']
    return form, month


@login_required
def index(request):
    form, month = _month(request)
    sync_user_ledger(request.user)
    budget_rows = budget_progress(request.user, month)
    return render(request, 'planning/index.html', {
        'section': 'overview', 'month': month, 'month_form': form, 'rows': budget_rows,
        'outlook': monthly_outlook(request.user, month), 'budget_count': len(budget_rows),
        'budget_attention_count': sum(row['over_budget'] or row['forecast_over_budget'] or not row['complete'] for row in budget_rows),
        'goal_count': FinancialGoal.objects.filter(user=request.user, is_archived=False).count(),
    })


@login_required
def budgets(request):
    # Keep old bookmarks and form return URLs while owning one monthly view.
    form, month = _month(request)
    if form.is_bound and not form.is_valid():
        return index(request)
    return redirect(reverse('planning:index') + f'?month={month:%Y-%m}#budgets')


@login_required
def tools(request):
    return render(request, 'planning/tools.html', {'section': 'tools'})


@login_required
def budget_form(request, pk=None):
    instance = get_object_or_404(CategoryBudget, pk=pk, user=request.user) if pk else None
    initial = {}
    month_form, month = _month(request)
    fallback_month = instance.month if instance else month
    if not month_form.is_bound or month_form.is_valid():
        initial['month'] = month.strftime('%Y-%m')
    form = CategoryBudgetForm(request.POST or None, user=request.user, instance=instance, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            budget = save_budget(form.save(commit=False))
        except ValidationError as error:
            if hasattr(error, 'message_dict'):
                for name, errors in error.message_dict.items():
                    form.add_error(name if name in form.fields else None, errors)
            else:
                form.add_error(None, error)
        else:
            messages.success(request, _('Budget saved.'))
            return redirect(return_url(request, reverse('planning:budgets') + f'?month={budget.month:%Y-%m}'))
    cancel_url = return_url(request, reverse('planning:budgets') + f'?month={fallback_month:%Y-%m}')
    return render(request, 'planning/form.html', {'form': form, 'section': 'budgets', 'heading': _('Edit category budget') if pk else _('New category budget'), 'cancel_url': cancel_url, 'return_url': return_url(request, '')})


@login_required
@require_POST
def budget_copy(request):
    form = MonthForm(request.POST)
    if not form.is_valid():
        return render(request, 'planning/form.html', {'form': form, 'section': 'budgets', 'heading': _('Copy previous month'), 'cancel_url': reverse('planning:budgets')}, status=400)
    month = form.cleaned_data['month']
    copied, skipped = copy_previous_budgets(request.user, month)
    messages.success(request, _('Copied %(copied)s limits; skipped %(skipped)s existing or overlapping limits.') % {'copied': copied, 'skipped': skipped})
    return redirect(reverse('planning:budgets') + f'?month={month:%Y-%m}')


@login_required
@require_POST
def budget_delete(request, pk):
    budget = get_object_or_404(CategoryBudget, user=request.user, pk=pk)
    month = budget.month
    budget.delete()
    messages.success(request, _('Budget removed.'))
    return redirect(reverse('planning:budgets') + f'?month={month:%Y-%m}')


@login_required
def goals(request):
    query = request.GET.get('q', '').strip()[:200]
    rows = goal_progress(request.user, include_archived=request.GET.get('archived') == '1')
    if query:
        rows = [row for row in rows if query.casefold() in row['goal'].name.casefold()]
    return render(request, 'planning/goals.html', {'section': 'goals', 'rows': rows, 'query': query,
        'include_archived': request.GET.get('archived') == '1'})


@login_required
def goal_form(request, pk=None):
    instance = get_object_or_404(FinancialGoal, user=request.user, pk=pk) if pk else None
    form_class = FinancialGoalForm if pk else GoalCreationForm
    form = form_class(request.POST or None, user=request.user, instance=instance)
    if request.method == 'POST' and form.is_valid():
        try:
            goal = form.save() if pk else create_goal(form.save(commit=False), form.allocation)
        except ValidationError as error:
            form.add_error(None, '\n'.join(error.messages))
        else:
            messages.success(request, _('Goal saved.') if pk or form.allocation else _('Goal saved. Reserve an existing balance to record progress.'))
            return redirect(return_url(request, reverse('planning:goal_detail', args=[goal.pk])))
    return render(request, 'planning/form.html', {'form': form, 'goal_creation': not pk, 'section': 'goals', 'heading': _('Edit goal') if pk else _('New goal'), 'cancel_url': return_url(request, reverse('planning:goals')), 'return_url': return_url(request, '')})


@login_required
def goal_detail(request, pk):
    goal = get_object_or_404(FinancialGoal, user=request.user, pk=pk)
    progress = next(row for row in goal_progress(request.user, include_archived=True) if row['goal'].pk == goal.pk)
    return render(request, 'planning/goal_detail.html', {'section': 'goals', 'row': progress, 'goal': goal})


@login_required
def allocation_form(request, goal_pk, pk=None):
    goal = get_object_or_404(FinancialGoal, user=request.user, pk=goal_pk)
    instance = get_object_or_404(GoalAllocation, user=request.user, goal=goal, pk=pk) if pk else None
    if goal.is_archived:
        raise Http404
    form = GoalAllocationForm(request.POST or None, user=request.user, goal=goal, instance=instance)
    if request.method == 'POST' and form.is_valid():
        try:
            save_allocation(form.instance)
        except ValidationError as error:
            form.add_error(None, '\n'.join(error.messages))
        else:
            messages.success(request, _('Balance reserved for this goal.'))
            return redirect(return_url(request, reverse('planning:goal_detail', args=[goal.pk])))
    return render(request, 'planning/form.html', {'form': form, 'section': 'goals', 'heading': _('Edit goal reservation') if pk else _('Reserve a balance'), 'cancel_url': return_url(request, reverse('planning:goal_detail', args=[goal.pk])), 'return_url': return_url(request, '')})


@login_required
@require_POST
def allocation_delete(request, pk):
    allocation = get_object_or_404(GoalAllocation, user=request.user, goal__user=request.user, pk=pk)
    goal_pk = allocation.goal_id
    allocation.delete()
    messages.success(request, _('Reservation released.'))
    return redirect('planning:goal_detail', pk=goal_pk)


@login_required
@require_POST
def goal_archive(request, pk):
    goal = get_object_or_404(FinancialGoal, user=request.user, pk=pk)
    try:
        set_goal_archived(goal, not goal.is_archived)
    except ValidationError as error:
        messages.error(request, '\n'.join(error.messages))
    else:
        messages.success(request, _('Goal archived and reservations released.') if goal.is_archived else _('Goal restored.'))
    return redirect('planning:goal_detail', pk=goal.pk)


@login_required
def signals(request):
    result = local_signals(request.user)
    result['include_reviewed'] = request.GET.get('reviewed') == '1'
    result['open_count'] = sum(1 for row in result['signals'] if row['decision'] is None)
    if not result['include_reviewed']:
        result['signals'] = [row for row in result['signals'] if row['decision'] is None]
    result['section'] = 'signals'
    return render(request, 'planning/signals.html', result)


@login_required
def signals_settings(request):
    form = SignalSettingsForm(request.POST or None, user=request.user, instance=signal_settings(request.user))
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, _('Signal settings saved.'))
        return redirect('planning:signals')
    return render(request, 'planning/form.html', {'form': form, 'section': 'signals', 'heading': _('Local signal settings'), 'cancel_url': reverse('planning:signals')})


@login_required
@require_POST
def signal_decision(request):
    action, key = request.POST.get('action'), request.POST.get('key')
    if action not in {'ACK', 'DISMISS', 'REOPEN'}:
        return HttpResponseBadRequest(_('Select a valid review action.'))
    if not any(row['key'] == key for row in local_signals(request.user)['signals']):
        raise Http404
    if action == 'REOPEN':
        SignalDecision.objects.filter(user=request.user, key=key).delete()
    else:
        SignalDecision.objects.update_or_create(user=request.user, key=key, defaults={'action': action})
    return redirect('planning:signals')
