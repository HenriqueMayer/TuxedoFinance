from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import FormView

from sandbox.forms import (
    SalarySandboxForm,
    budget_from_form,
    clt_scenario_from_form,
    variable_rows,
    variables_from_data,
)
from sandbox.services import apply_variables, build_budget, calculate_clt, calculate_manual
from sandbox.tax_rules import get_tax_rules


class SalarySandboxView(LoginRequiredMixin, FormView):
    template_name = 'sandbox/index.html'
    form_class = SalarySandboxForm
    login_url = 'accounts:login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rules'] = get_tax_rules()
        posted = self.request.POST if self.request.method == 'POST' else None
        context.setdefault('deduction_rows', variable_rows(posted, 'deduction', include_blank=True))
        context.setdefault('variable_rows', variable_rows(posted, 'variable'))
        return context

    def _respond(self, context):
        if self.request.POST.get('response_mode') == 'fragment':
            return render(self.request, 'sandbox/_workspace.html', context)
        return self.render_to_response(context)

    def form_invalid(self, form):
        return self._respond(self.get_context_data(form=form))

    def form_valid(self, form):
        use_clt = form.cleaned_data.get('use_clt', False)
        if use_clt:
            clt = calculate_clt(clt_scenario_from_form(form))
            # The monthly plan must be affordable from a normal paycheque;
            # vacation and the 13th salary remain visible in the annual view.
            income = clt.ordinary.net
            result = {'mode': 'clt', 'clt': clt}
        else:
            manual = calculate_manual(
                form.cleaned_data['gross_salary'],
                variables_from_data(form.data, 'deduction'),
            )
            income = manual.monthly_net
            result = {'mode': 'manual', 'manual': manual}

        budget_input = budget_from_form(form)
        result['budget'] = build_budget(income, budget_input)
        result['variables'] = apply_variables(max(income, 0), budget_input.custom_variables)
        return self._respond(self.get_context_data(form=form, result=result))
