from dataclasses import replace
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import FormView

from sandbox.forms import (
    SalarySandboxForm,
    budget_from_form,
    clt_scenario_from_form,
    custom_variable_rows,
    pj_scenario_from_form,
)
from sandbox.services import (
    apply_custom_variables,
    build_budget,
    calculate_clt,
    calculate_pj,
    solve_equivalent_clt,
    solve_equivalent_pj,
)
from sandbox.tax_rules import get_tax_rules


class SalarySandboxView(LoginRequiredMixin, FormView):
    template_name = 'sandbox/clt_pj.html'
    form_class = SalarySandboxForm
    login_url = 'accounts:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rules'] = get_tax_rules()
        context.setdefault('selected_type', None)
        context.setdefault('variable_rows', custom_variable_rows(self.request.POST if self.request.method == 'POST' else None))
        return context

    def _respond(self, context):
        if self.request.POST.get('response_mode') == 'fragment':
            return render(self.request, 'sandbox/_workspace.html', context)
        return self.render_to_response(context)

    def form_invalid(self, form):
        selected_type = self.request.POST.get('scenario_type')
        return self._respond(self.get_context_data(
            form=form,
            selected_type=selected_type if selected_type in {'clt', 'pj'} else None,
        ))

    def form_valid(self, form):
        source_type = form.cleaned_data['scenario_type']
        intent = self.request.POST.get('intent', 'select')
        if intent == 'select':
            if not self.request.POST.get('current_scenario_type'):
                form = self.form_class(initial={'scenario_type': source_type})
                variable_rows = []
            else:
                variable_rows = custom_variable_rows(self.request.POST)
            return self._respond(self.get_context_data(
                form=form,
                selected_type=source_type,
                variable_rows=variable_rows,
            ))

        rules = get_tax_rules(int(form.cleaned_data.get('tax_year') or 2026))
        budget_input = budget_from_form(form)
        comparison = None

        if source_type == 'clt':
            clt = calculate_clt(clt_scenario_from_form(form), rules)
            source_income = clt.monthly_normalized_net
            result = {'type': 'clt', 'clt': clt}
            if intent == 'compare':
                pj_assumptions = pj_scenario_from_form(form, comparison=True)
                equivalent = solve_equivalent_pj(clt, pj_assumptions, rules)
                if equivalent.revenue_monthly is not None:
                    pj = calculate_pj(replace(pj_assumptions, revenue_monthly=equivalent.revenue_monthly), rules)
                    comparison = self._comparison(clt, pj, budget_input, equivalent)
                else:
                    comparison = {'valid': False, 'warnings': equivalent.warnings}
        else:
            pj = calculate_pj(pj_scenario_from_form(form), rules)
            source_income = pj.monthly_normalized_net
            result = {'type': 'pj', 'pj': pj}
            if intent == 'compare' and pj.valid:
                clt_assumptions = clt_scenario_from_form(form, comparison=True)
                equivalent = solve_equivalent_clt(pj, clt_assumptions, rules)
                clt = calculate_clt(replace(clt_assumptions, gross_monthly=equivalent.gross_monthly), rules)
                comparison = self._comparison(clt, pj, budget_input, equivalent)

        source_budget = build_budget(source_income, source_income, budget_input)['clt']
        result['budget'] = source_budget
        result['variables'] = apply_custom_variables(source_income, budget_input)
        context = self.get_context_data(
            form=form,
            result=result,
            comparison=comparison,
            selected_type=source_type,
        )
        return self._respond(context)

    @staticmethod
    def _comparison(clt, pj, budget_input, equivalent):
        budgets = build_budget(clt.monthly_normalized_net, pj.monthly_normalized_net, budget_input)
        clt_value = clt.annual_worker_value
        pj_value = pj.annual_net
        difference = pj_value - clt_value
        difference_percent = difference / clt_value * Decimal('100') if clt_value else Decimal('0')
        return {
            'valid': pj.valid,
            'clt': clt,
            'pj': pj,
            'budget': budgets,
            'equivalent': equivalent,
            'difference': difference,
            'difference_percent': difference_percent,
        }
