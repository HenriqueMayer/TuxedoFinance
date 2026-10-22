# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bounded, read-only monthly salary simulations using the canonical workspace."""
from datetime import datetime
from decimal import Decimal, DecimalException
import json
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from banking.services import MissingExchangeRate, convert
from banking.models import CardInvoiceCredit
from categories.models import Category
from sandbox.forms import SalarySandboxForm
from sandbox.planning import commitment_snapshot, snapshot_total
from sandbox.services import calculate_monthly_plan, money
from sandbox.tax_rules import get_tax_rules
from transactions.models import Transaction


_MONEY_FIELDS = ('gross_salary', 'clt_pension', 'clt_transport', 'clt_food', 'clt_health', 'clt_other')
_FIELDS = frozenset((*_MONEY_FIELDS, 'planning_month', 'clt_dependents', 'extra_expenses', 'category_reductions'))
_DECIMAL = re.compile(r'\d{1,12}(?:\.\d{1,2})?')
MAX_RESULT_BYTES = 16 * 1024


def monthly_simulation_schema():
    """No user identity, formula, persisted draft or confirmation endpoint is accepted."""
    money = {'type': 'string', 'pattern': r'^\d{1,12}(?:\.\d{1,2})?$',
             'description': 'Canonical nonnegative BRL decimal amount, e.g. 600.00; never cents or a float.'}
    fields = {
        'planning_month': {'type': 'string', 'pattern': r'^\d{4}-\d{2}$',
                           'description': 'Explicit YYYY-MM month; use the current cutoff only when the user requested this month.'},
        'gross_salary': {**money, 'description': 'Positive gross monthly CLT salary in BRL, before INSS, IRRF and payroll deductions.'},
        'clt_dependents': {'type': 'integer', 'minimum': 0, 'maximum': 99},
        'clt_pension': money, 'clt_transport': money, 'clt_food': money, 'clt_health': money,
        'clt_other': {**money, 'description': 'Other payroll deductions in BRL. This is not a spending category or extra budget expense. Ask if ambiguous.'},
        'extra_expenses': {'type': 'array', 'maxItems': 20, 'items': {
            'type': 'object', 'properties': {
                'title': {'type': 'string', 'minLength': 1, 'maxLength': 80},
                'unit': {'type': 'string', 'enum': ['currency', 'percent']},
                'value': {**money, 'description': 'Additional unrecorded BRL expense, or 0–100 percent of gross salary; never double-count an existing expense.'},
            }, 'required': ['title', 'unit', 'value'], 'additionalProperties': False}},
        'category_reductions': {'type': 'array', 'maxItems': 20, 'description':
            'Explicit hypothetical BRL spending cuts in owned categories including descendants. '
            'Use [] when no cut was requested. Never change budgets or records, overlap families, '
            'or confuse a category named Other with other payroll deductions.', 'items': {
                'type': 'object', 'properties': {
                    'category_id': {'type': 'integer', 'minimum': 1, 'maximum': 9223372036854775807},
                    'amount': {**money, 'description': 'Positive BRL cut, at most this category family registered forecast.'},
                }, 'required': ['category_id', 'amount'], 'additionalProperties': False}},
    }
    return {'type': 'function', 'name': 'simulate_month', 'strict': True,
            'description': 'Run the application monthly CLT salary simulation without saving. '
                           'Includes the owned registered-expense forecast by statement/reference month. '
                           'Requires an explicit monthly-simulation request; ask for missing gross salary/month '
                           'or ambiguous payroll deductions. Unspecified payroll parameters are zero; extra_expenses and category_reductions are empty. '
                           'Returns aggregate amounts only, not registered descriptions or notes. '
                           'This is hypothetical BRL planning, not a balance, real income, goal, category budget or draft.',
            'parameters': {'type': 'object', 'properties': fields,
                           'required': list(fields), 'additionalProperties': False}}


def _problem(code, *, fields=None):
    result = {'kind': 'monthly_simulation', 'saved': False, 'complete': False, 'error': code}
    if fields:
        result['fields'] = fields
    return result


def _form(arguments):
    # Older local test fixtures omit cuts; strict provider schemas always send [].
    if not isinstance(arguments, dict) or set(arguments) not in (_FIELDS, _FIELDS - {'category_reductions'}):
        return None
    if (not isinstance(arguments['planning_month'], str)
            or not re.fullmatch(r'\d{4}-\d{2}', arguments['planning_month'])
            or type(arguments['clt_dependents']) is not int or not 0 <= arguments['clt_dependents'] <= 99):
        return None
    if any(not isinstance(arguments[name], str) or not _DECIMAL.fullmatch(arguments[name]) for name in _MONEY_FIELDS):
        return None
    rows = arguments['extra_expenses']
    if not isinstance(rows, list) or len(rows) > 20:
        return None
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'title', 'unit', 'value'}
                or not isinstance(row['title'], str) or not row['title'].strip() or len(row['title']) > 80
                or row['unit'] not in ('currency', 'percent')
                or not isinstance(row['value'], str) or not _DECIMAL.fullmatch(row['value'])):
            return None
    reductions = arguments.get('category_reductions', [])
    if not isinstance(reductions, list) or len(reductions) > 20:
        return None
    for row in reductions:
        if (not isinstance(row, dict) or set(row) != {'category_id', 'amount'}
                or type(row['category_id']) is not int or not 1 <= row['category_id'] <= 9223372036854775807
                or not isinstance(row['amount'], str) or not _DECIMAL.fullmatch(row['amount'])
                or Decimal(row['amount']) <= 0):
            return None
    data = {name: value for name, value in arguments.items() if name not in ('extra_expenses', 'category_reductions')}
    data.update(variable_label=[row['title'] for row in rows], variable_type=[row['unit'] for row in rows],
                variable_value=[row['value'] for row in rows])
    return SalarySandboxForm(data)


def _category_cuts(user, requested, rows, month, captured):
    """Reconcile owned category allocations to the same economic BRL snapshot.

    Monthly allocations carry installment and split rounding. Converting the
    event once, then distributing its BRL cents with the canonical allocator,
    avoids manufacturing a cent by independently rounding each split's FX.
    """
    if not requested:
        return [], Decimal('0'), Decimal('0')
    categories = {item.pk: item for item in Category.objects.filter(user=user)}
    families, occupied = [], set()
    for request in requested:
        category = categories.get(request['category_id'])
        if category is None or category.transaction_type == 'INCOME':
            raise ValidationError('invalid_category_reference')
        family = {category.pk} | category.descendant_ids()
        if occupied & family:
            raise ValidationError('overlapping_category_reductions')
        occupied |= family
        families.append((category, family, Decimal(request['amount'])))

    transaction_ids, redemption_ids, credit_ids = set(), set(), set()
    for row in rows:
        identity = row['key'].split(':')
        if identity[0] == 'transaction':
            transaction_ids.add(int(identity[1]))
        elif identity[0] == 'iof':
            redemption_ids.add(int(identity[1]))
        elif identity[0] == 'invoice-credit':
            credit_ids.add(int(identity[1]))
        elif identity[0] != 'points':
            raise ValidationError('category_mapping_unavailable')
    query = Transaction.objects.filter(user=user, transaction_type='EXPENSE').select_related(
        'category', 'bank_account', 'debit_card__account', 'credit_card__account',
    ).prefetch_related('splits__category')
    transactions = {item.pk: item for item in query.filter(pk__in=transaction_ids, reward_redemption__isnull=True)}
    redemptions = {item.reward_redemption_id: item for item in query.filter(reward_redemption_id__in=redemption_ids)}
    credits = {item.pk: item for item in CardInvoiceCredit.objects.filter(
        user=user, pk__in=credit_ids, reference_month=month,
    ).select_related('category', 'card__account')}
    totals = {category_id: Decimal('0') for category_id in occupied}
    rates, seen, points_total = {}, set(), Decimal('0')
    for row in rows:
        if not row['included']:
            continue
        if row['key'] in seen:
            raise ValidationError('category_mapping_unavailable')
        seen.add(row['key'])
        identity = row['key'].split(':')
        if identity[0] == 'points':
            # Purchased points have no category field; retain their expense once.
            points_total += Decimal(row['amount'])
            continue
        if identity[0] == 'invoice-credit':
            credit = credits.get(int(identity[1]))
            native = Decimal(row['native_amount'])
            if (credit is None or row['kind'] != 'invoice_credit' or native != credit.amount
                    or row['currency'] != credit.card.account.currency or credit.category_id not in categories):
                raise ValidationError('category_mapping_unavailable')
            currency = row['currency']
            if currency not in rates:
                rates[currency] = convert(user, Decimal('1'), currency, 'BRL', as_of=timezone.localdate(captured))
            converted = money(native * rates[currency])
            if converted != Decimal(row['amount']):
                raise ValidationError('category_mapping_unavailable')
            if credit.category_id in totals:
                totals[credit.category_id] -= converted
            continue
        item = (transactions if identity[0] == 'transaction' else redemptions).get(int(identity[1]))
        if item is None:
            # A legacy IOF without its generated expense has no safe category.
            raise ValidationError('category_mapping_unavailable')
        allocations = item.category_allocations_for_month(month.year, month.month)
        amounts = [value for _category, value in allocations]
        native = Decimal(row['native_amount'])
        if (item.native_currency != row['currency'] or sum(amounts, Decimal('0')) != native
                or any(category is None or category.pk not in categories or not value.is_finite() or value < 0
                       for category, value in allocations)):
            raise ValidationError('category_mapping_unavailable')
        currency = row['currency']
        if currency not in rates:
            rates[currency] = convert(user, Decimal('1'), currency, 'BRL', as_of=timezone.localdate(captured))
        converted = money(native * rates[currency])
        if converted != Decimal(row['amount']):
            raise ValidationError('category_mapping_unavailable')
        allocated = Transaction._split_amount(converted, amounts)
        for (category, _native_amount), amount in zip(allocations, allocated):
            if category.pk in totals:
                totals[category.pk] += amount
    results, reduction = [], Decimal('0')
    for category, family, amount in families:
        before = sum((totals[key] for key in family), Decimal('0'))
        if amount > before:
            raise ValidationError('category_reduction_exceeds_forecast')
        results.append({'category_id': category.pk, 'category': category.name,
                        'includes_descendants': True, 'before': format(before, '.2f'),
                        'reduction': format(amount, '.2f'), 'after': format(before - amount, '.2f')})
        reduction += amount
    return results, reduction, points_total


def _bounded(result):
    try:
        size = len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode('utf-8'))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return _problem('simulation_unavailable')
    return result if size < MAX_RESULT_BYTES else _problem('limit_exceeded')


def simulate_month(user, arguments):
    """Read the current owner's economic sources and calculate; never sync or save.

    The chat dispatcher owns explicit-request permission and repeated session/run
    authorization. No user ID, raw record selection or whole-history output is
    accepted from a model. Payroll deductions remain separate from expenses.
    """
    if (not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False)
            or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists()):
        return _problem('unauthorized')
    form = _form(arguments)
    if form is None:
        return _problem('invalid_parameters')
    if not form.is_valid():
        fields = {name: [str(error)[:240] for error in errors[:3]] for name, errors in form.errors.items()}
        return _bounded(_problem('invalid_parameters', fields=fields))
    month = form.cleaned_data['planning_month']
    key = month.strftime('%Y-%m')
    try:
        snapshot = commitment_snapshot(user, month, month_basis='reference_month')
        selected = [row for row in snapshot['rows'] if row['reference_month'] == key]
        missing = sorted({row['currency'] for row in selected if row['included'] and row['amount'] is None})
        total = None if missing else snapshot_total(snapshot, key)
    except (ValidationError, DecimalException, ValueError, OverflowError):
        return _problem('forecast_unavailable')
    rules = get_tax_rules()
    captured = datetime.fromisoformat(snapshot['captured_at'])
    result = {
        'kind': 'monthly_simulation', 'saved': False, 'complete': not missing, 'currency': 'BRL',
        'planning_month': key, 'captured_at': snapshot['captured_at'],
        'cutoff': timezone.localdate(captured).isoformat(), 'month_basis': 'reference_month',
        'tax_rules': {'year': rules.year, 'reviewed_on': rules.reviewed_on.isoformat(),
                      'source_urls': list(rules.source_urls[:2])},
        'inputs': {name: (form.cleaned_data[name] or 0 if name == 'clt_dependents'
                          else format(form.cleaned_data[name] or 0, '.2f'))
                   for name in (*_MONEY_FIELDS, 'clt_dependents')},
        'forecast': {'total': format(total, '.2f') if total is not None else None,
                     'count': len(selected), 'missing_currencies': missing},
        'payroll': None, 'budget': None, 'extra_expenses': [], 'category_reductions': [],
        'warnings': [f'Hypothetical ordinary monthly salary using implemented {rules.year} tax rules; '
                     'this does not assert the tax table for another year or a payslip amount.',
                     'Other payroll deductions reduce take-home pay once, not the IRRF base; '
                     'they are not registered categories or additional budget expenses.',
                     'Registered expenses follow their reference/statement month. Invoice payments are not counted again. '
                     'Extra expense percentages use gross salary; amounts already registered must not be added again.'],
        'references': [{'label': _('Monthly salary simulation'), 'url': reverse('sandbox:index')},
                       {'label': _('Monthly planning — %(month)s') % {'month': key},
                        'url': reverse('planning:index') + '?month=' + key}],
    }
    if missing:
        result['error'] = 'missing_exchange_rate'
        result['warnings'].append('The registered forecast is incomplete. Missing FX blocks the remaining-balance calculation; no zero expense total was assumed.')
        return _bounded(result)
    try:
        cuts, reduction, points_total = _category_cuts(
            user, arguments.get('category_reductions', []), selected, month, captured,
        )
    except (ValidationError, MissingExchangeRate, DecimalException, ValueError, OverflowError) as error:
        result['complete'] = False
        result['error'] = error.messages[0] if isinstance(error, ValidationError) else 'category_mapping_unavailable'
        result['warnings'].append('The requested category cuts cannot be safely applied to the registered forecast. '
                                  'No adjusted expense or remaining balance was assumed; all records and limits are unchanged.')
        return _bounded(result)
    result['category_reductions'] = cuts
    adjusted = total - reduction
    if cuts:
        result['forecast'].update(adjusted_total=format(adjusted, '.2f'), reduction_total=format(reduction, '.2f'))
        result['warnings'].append('Category cuts reduce only this hypothetical expense forecast, including descendants. '
                                  'Registered amounts, category limits and payroll are unchanged. BRL split cents use the canonical largest-remainder allocation.')
        if points_total:
            result['forecast']['uncategorized_points_expenses'] = format(points_total, '.2f')
            result['warnings'].append('Points purchases have no category allocation and remain in the forecast unchanged, counted once.')
    forecast = {'month': month, 'total': adjusted, 'count': len(selected), 'error': None}
    calculated = calculate_monthly_plan(form, forecast)
    if calculated is None:
        return _problem('simulation_unavailable')
    payroll, budget = calculated['payroll'], calculated['budget']
    result['payroll'] = {name: format(getattr(payroll, name), '.2f')
                         for name in ('gross', 'inss', 'irrf', 'deductions', 'net', 'irrf_base')}
    result['payroll']['irrf_method'] = payroll.irrf_method
    result['budget'] = {'net_income': format(budget.income, '.2f'),
                        'registered_expenses': format(budget.fixed_bills, '.2f'),
                        'additional_expenses': format(budget.custom_expenses, '.2f'),
                        'remaining': format(budget.remaining, '.2f')}
    if cuts:
        result['budget']['remaining_before_reductions'] = format(budget.remaining - reduction, '.2f')
    result['extra_expenses'] = [{'title': row.label, 'unit': row.value_type, 'value': format(row.value, '.2f'),
                                  'monthly_amount': format(row.monthly_amount, '.2f')}
                                 for row in calculated['variables']]
    return _bounded(result)
