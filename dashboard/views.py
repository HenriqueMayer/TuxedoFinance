from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from dashboard.charts import (
    build_bar_chart,
    build_donut_chart,
    build_instrument_chart,
    build_line_chart,
)
from dashboard.services import (
    EVOLUTION_PAST_MONTHS,
    OUTLOOK_MONTHS,
    _expenses_by_category,
    _transactions,
    add_months,
    get_account_evolution,
    get_dashboard_summary,
    get_expenses_by_category_for_instrument,
    get_expenses_by_recurrence,
    get_income_by_category_for_account,
    get_instrument_activity,
)
from transactions.services import sync_user_ledger


ALL_TIME_MONTHS = 12


def _selected_month(request, in_range):
    today = timezone.localdate()
    year_part, _, month_part = request.GET.get('month', '').partition('-')
    if year_part.isdigit() and month_part.isdigit():
        year, month = int(year_part), int(month_part)
        if 1 <= month <= 12 and in_range(year, month):
            return year, month
    return today.year, today.month


def _is_representable(year, month):
    return date.min.year <= year <= date.max.year


def _is_projectable(year, month):
    earliest_year, _ = add_months(year, month, -1)
    latest_year, _ = add_months(year, month, OUTLOOK_MONTHS - 1)
    return date.min.year <= earliest_year and latest_year <= date.max.year


def _month_choices():
    today = timezone.localdate()
    choices = [('ALL', _('All time'))]
    for step in range(ALL_TIME_MONTHS):
        year, month = add_months(today.year, today.month, -step)
        choices.append((f'{year:04d}-{month:02d}', date_format(date(year, month, 1), 'F Y')))
    return choices


def _parse_month_or_all(request, param_name, in_range):
    raw = request.GET.get(param_name, '').strip().upper()
    if not raw or raw == 'ALL':
        return 'ALL', None, None
    year_part, _, month_part = raw.partition('-')
    if not (year_part.isdigit() and month_part.isdigit()):
        return 'ALL', None, None
    year, month = int(year_part), int(month_part)
    if not (1 <= month <= 12 and in_range(year, month)):
        return 'ALL', None, None
    return f'{year:04d}-{month:02d}', year, month


def _parse_charts_offset(request, in_range):
    try:
        offset = int(request.GET.get('charts_offset', '').strip())
    except ValueError:
        return 0
    today = timezone.localdate()
    if not in_range(*add_months(today.year, today.month, offset)):
        return 0
    return offset


def _is_offset_window_safe(year, month):
    earliest_year, _ = add_months(year, month, -EVOLUTION_PAST_MONTHS)
    latest_year, _ = add_months(
        year, month, ALL_TIME_MONTHS - EVOLUTION_PAST_MONTHS - 1
    )
    return date.min.year <= earliest_year and latest_year <= date.max.year


class DashboardIndexView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sync_user_ledger(self.request.user)
        year, month = _selected_month(self.request, _is_projectable)
        context.update(get_dashboard_summary(self.request.user, year, month))
        previous_year, previous_month = add_months(year, month, -1)
        next_year, next_month = add_months(year, month, 1)
        context['previous_month_param'] = f'{previous_year:04d}-{previous_month:02d}'
        context['next_month_param'] = f'{next_year:04d}-{next_month:02d}'
        return context


class DashboardReportsView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/reports.html'

    def get_template_names(self):
        if self.request.headers.get('HX-Request') == 'true':
            return ['dashboard/_reports_charts.html']
        return [self.template_name]

    def get_installment_month(self):
        raw = self.request.GET.get('installment_month', '').strip().upper()
        if not raw:
            today = timezone.localdate()
            return f'{today:%Y-%m}', today.year, today.month
        return _parse_month_or_all(
            self.request, 'installment_month', _is_representable
        )

    def _selected_instrument(self, breakdown, param_name):
        key = self.request.GET.get(param_name, '').strip()
        return next(
            (row for row in breakdown['instruments'] if row['key'] == key), None
        )

    def _drilldown_window(self, value, year, month):
        if value == 'ALL':
            today = timezone.localdate()
            return today.year, today.month, date_format(today, 'F Y'), 'current month'
        return year, month, date_format(date(year, month, 1), 'F Y'), 'selected month'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sync_user_ledger(self.request.user)
        offset = _parse_charts_offset(self.request, _is_offset_window_safe)
        evolution = get_account_evolution(self.request.user, offset=offset)
        months = evolution['months']
        context.update(
            {
                'evolution': evolution,
                'charts_offset': offset,
                'previous_offset_param': offset - 1,
                'next_offset_param': offset + 1,
                'balance_chart': build_line_chart(
                    months, [float(row['closing_balance']) for row in months]
                ),
                'cashflow_chart': build_bar_chart(
                    months,
                    [
                        {'name': _('Income'), 'tone': 'income', 'values': [float(row['income']) for row in months]},
                        {'name': _('Expenses'), 'tone': 'expense', 'values': [float(row['expenses']) for row in months]},
                        {'name': _('Investments'), 'tone': 'investment', 'values': [float(row['investments']) for row in months]},
                    ],
                ),
                'month_choices': _month_choices(),
            }
        )

        period_value, period_year, period_month = _parse_month_or_all(
            self.request, 'instrument_month', _is_representable
        )
        context['instrument_month_param'] = period_value
        context['instrument_window_label'] = (
            _('All time')
            if period_value == 'ALL'
            else date_format(date(period_year, period_month, 1), 'F Y')
        )
        if period_value == 'ALL':
            activity = get_instrument_activity(self.request.user, months=ALL_TIME_MONTHS)
        else:
            activity = get_instrument_activity(
                self.request.user, period_year, period_month
            )
        context['instrument_activity'] = activity
        context['instrument_chart'] = self._instrument_chart(activity)

        selected_expense = self._selected_instrument(
            activity, 'expense_instrument'
        )
        selected_income = self._selected_instrument(
            activity, 'income_account'
        )
        if selected_expense and not selected_expense['expense_total']:
            selected_expense = None
        if selected_income and not selected_income['income_total']:
            selected_income = None
        context['selected_expense_instrument'] = selected_expense
        context['selected_income_account'] = selected_income
        year, month, label, window = self._drilldown_window(
            period_value, period_year, period_month
        )
        context['instrument_categories_label'] = label
        context['instrument_categories_window'] = window
        context['expense_instrument_categories'] = (
            get_expenses_by_category_for_instrument(
                self.request.user, selected_expense['key'], year, month
            )
            if selected_expense
            else []
        )
        context['income_account_categories'] = (
            get_income_by_category_for_account(
                self.request.user, selected_income['key'], year, month
            )
            if selected_income
            else []
        )

        category_value, category_year, category_month = _parse_month_or_all(
            self.request, 'category_month', _is_representable
        )
        context['category_month_param'] = category_value
        if category_value == 'ALL':
            context['expenses_by_category'] = evolution['expenses_by_category']
            context['category_window_label'] = _('All time')
        else:
            rows, category_missing = _expenses_by_category(
                self.request.user,
                _transactions(self.request.user),
                category_year,
                category_month,
                1,
            )
            context['expenses_by_category'] = rows
            context['category_window_label'] = date_format(
                date(category_year, category_month, 1), 'F Y'
            )
            evolution['missing_currencies'] = sorted(
                set(evolution['missing_currencies']) | set(category_missing)
            )

        installment_value, year, month = self.get_installment_month()
        context['installment_month_param'] = installment_value
        if installment_value == 'ALL':
            recurrence = get_expenses_by_recurrence(
                self.request.user, months=ALL_TIME_MONTHS
            )
            context['installment_window_label'] = _('All time')
        else:
            recurrence = get_expenses_by_recurrence(self.request.user, year, month)
            context['installment_window_label'] = date_format(date(year, month, 1), 'F Y')
        context['recurrence_breakdown'] = recurrence
        context['recurrence_chart'] = (
            build_donut_chart([row for row in recurrence['slices'] if row['draw']])
            if any(row['draw'] for row in recurrence['slices'])
            else None
        )
        context['missing_currencies'] = sorted(
            set(evolution['missing_currencies'])
            | set(activity['missing_currencies'])
            | set(recurrence['missing_currencies'])
        )
        return context

    @staticmethod
    def _instrument_chart(activity):
        rows = activity['instruments']
        if not rows:
            return None
        return build_instrument_chart(
            rows,
            [
                {
                    'name': _('Expenses'),
                    'tone': 'expense',
                    'values': [float(row['expense_total']) for row in rows],
                },
                {
                    'name': _('Income'),
                    'tone': 'income',
                    'values': [float(row['income_total']) for row in rows],
                },
            ],
        )
