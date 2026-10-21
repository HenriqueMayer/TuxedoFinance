# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""On-demand owned financial evidence. Never call views or synchronize ledgers."""
from calendar import monthrange
from datetime import date
import json
import re

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.models import UserPreference
from assistant.action_service import ActionError
from banking.models import BankAccount, CreditCard, DebitCard, CardInvoice, ExchangeRate, LoyaltyProgram
from banking.services import ConversionContext, account_balance
from categories.models import Category
from transactions.models import Transaction


AREAS = ('accounts', 'cards', 'invoices', 'transactions', 'categories', 'planning',
         'goals', 'investments', 'reports', 'exchange_rates', 'loyalty', 'saved_scenarios')
PAGE_SIZE = 20
MAX_RESPONSE_BYTES = 15000


def assert_owned_sources(user):
    """Reject malformed legacy ownership before a canonical aggregate can join it.

    Model validation normally enforces this. Reads must also handle imported or
    legacy rows without allowing a foreign label/amount into the model context.
    """
    if (not getattr(user, 'is_authenticated', False) or not user.is_active
            or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists()):
        raise ActionError('unauthorized', 403)
    dependencies = {
        'banking.BankAccount': ('bank',), 'banking.CreditCard': ('account',),
        'banking.DebitCard': ('account',), 'banking.CardInvoice': ('card',),
        'banking.CardInvoiceCredit': ('card', 'category'),
        'banking.BankMovement': ('account', 'invoice', 'transfer'),
        'banking.BankTransfer': ('source_account', 'destination_account'),
        'banking.InvoicePayment': ('account', 'invoice', 'movement'),
        'banking.LoyaltyProgram': ('bank',),
        'banking.LoyaltyEntry': ('program', 'funding_account', 'funding_credit_card'),
        'banking.RewardRedemption': ('program', 'target_account', 'iof_account', 'iof_credit_card',
                                     'loyalty_entry', 'reward_movement', 'iof_movement'),
        'categories.Category': ('parent_category',),
        'transactions.Transaction': ('category', 'bank_account', 'credit_card', 'debit_card', 'reward_redemption'),
        'investments.Asset': ('opening_product',), 'investments.InvestmentProduct': ('bank',),
        'investments.Investment': ('product', 'asset'), 'investments.PriceObservation': ('asset',),
        'investments.PositionPlanningSetting': ('product', 'asset'),
        'planning.CategoryBudget': ('category',),
        'planning.GoalAllocation': ('goal', 'bank_account', 'product', 'asset'),
    }
    for model_name, paths in dependencies.items():
        invalid = Q()
        for path in paths:
            invalid |= Q(**{path + '__isnull': False}) & ~Q(**{path + '__user': user})
        if apps.get_model(model_name).objects.filter(user=user).filter(invalid).exists():
            raise ActionError('inconsistent_ownership', 409)
    if (apps.get_model('transactions.TransactionSplit').objects.filter(transaction__user=user)
            .exclude(category__user=user).exists()
            or apps.get_model('banking.BankMovement').objects.filter(account__user=user).exclude(user=user).exists()
            or apps.get_model('banking.InvoicePayment').objects.filter(invoice__user=user).exclude(user=user).exists()
            or apps.get_model('planning.GoalAllocation').objects.filter(goal__user=user).exclude(user=user).exists()):
        raise ActionError('inconsistent_ownership', 409)


def consultation_schema():
    return {'type': 'function', 'name': 'read_financial_data', 'strict': True,
            'description': 'Consult the authenticated user saved finances in ANY workspace, independent of the current page. '
            'Use planning/reports for a requested month, then simulate_month for salary/monthly scenarios. '
            'Reads and simulations need no confirmation. Query narrows names; record_id selects one owned record; page starts at 0. '
            'No raw SQL, authentication data, unsent forms or external requests are available.',
            'parameters': {'type': 'object', 'additionalProperties': False,
                'required': ['area', 'month', 'query', 'record_id', 'page'], 'properties': {
                    'area': {'type': 'string', 'enum': list(AREAS)},
                    'month': {'type': ['string', 'null'], 'description': 'YYYY-MM; null means current month.'},
                    'query': {'type': 'string', 'maxLength': 120},
                    'record_id': {'type': ['integer', 'null'], 'minimum': 1},
                    'page': {'type': 'integer', 'minimum': 0, 'maximum': 10000}}}}


def read_financial_data(user, arguments):
    if not isinstance(arguments, dict) or set(arguments) != {'area', 'month', 'query', 'record_id', 'page'}:
        raise ActionError('invalid_parameters')
    area, raw_month, query, identifier, page = (arguments[key] for key in ('area', 'month', 'query', 'record_id', 'page'))
    if (not isinstance(area, str) or area not in AREAS or not isinstance(query, str) or len(query) > 120
            or type(page) is not int or not 0 <= page <= 10000
            or identifier is not None and (type(identifier) is not int or not 1 <= identifier <= 9223372036854775807)):
        raise ActionError('invalid_parameters')
    today = timezone.localdate()
    if raw_month is None:
        month = today.replace(day=1)
    else:
        if not isinstance(raw_month, str) or not re.fullmatch(r'\d{4}-\d{2}', raw_month):
            raise ActionError('invalid_parameters')
        try:
            month = date.fromisoformat(raw_month + '-01')
        except ValueError:
            raise ActionError('invalid_parameters') from None
        if not 1901 <= month.year <= 9988:
            raise ActionError('invalid_parameters')
    assert_owned_sources(user)
    cutoff = min(today, month.replace(day=monthrange(month.year, month.month)[1]))
    base = UserPreference.objects.filter(user=user).values_list('base_currency', flat=True).first() or 'BRL'
    conversion = ConversionContext(user, base_currency=base)
    result = {'area': area, 'month': month.strftime('%Y-%m'), 'captured_at': timezone.now().isoformat(),
              'cutoff': cutoff.isoformat(), 'base_currency': base, 'saved': False,
              'warnings': ['Stored sources are read without refreshing financial projections.'],
              'references': [], 'items': [], 'page': page, 'has_more': False}

    def reference(label, url):
        if len(result['references']) < 20:
            result['references'].append({'label': str(label)[:160], 'url': url})

    def select(rows, field='name'):
        if identifier is not None:
            rows = rows.filter(pk=identifier)
            if not rows.exists():
                raise ActionError('invalid_reference', 404)
        if query.strip():
            rows = rows.filter(**{field + '__icontains': query.strip()})
        selected = list(rows.order_by('pk')[page * PAGE_SIZE:(page + 1) * PAGE_SIZE + 1])
        result['has_more'] |= len(selected) > PAGE_SIZE
        return selected[:PAGE_SIZE]

    if area == 'accounts':
        for item in select(BankAccount.objects.filter(user=user).select_related('bank')):
            result['items'].append({'id': item.pk, 'name': item.name[:160], 'bank': item.bank.name[:160],
                'currency': item.currency, 'balance': account_balance(item, cutoff),
                'opening_date': item.opening_date, 'reserved': item.reserved_amount, 'planning_enabled': item.planning_enabled})
            reference(item.name, reverse('banking:detail', args=[item.bank_id]) + f'#account-row-{item.pk}')
    elif area == 'cards':
        # IDs are scoped to the kind: a debit and a credit record may share one.
        remaining, offset, found = PAGE_SIZE + 1, page * PAGE_SIZE, False
        for model, kind in ((CreditCard, 'credit'), (DebitCard, 'debit')):
            rows = model.objects.filter(user=user).select_related('account__bank')
            if identifier is not None:
                rows = rows.filter(pk=identifier)
                found |= rows.exists()
            if query.strip():
                rows = rows.filter(name__icontains=query.strip())
            count = rows.count()
            if offset >= count:
                offset -= count
                continue
            selected = list(rows.order_by('pk')[offset:offset + remaining])
            offset = 0
            for item in selected:
                row = {'id': item.pk, 'kind': kind, 'name': item.name[:160], 'account': item.account.name[:160],
                       'account_id': item.account_id, 'bank': item.account.bank.name[:160], 'currency': item.account.currency}
                if kind == 'credit':
                    row.update(closing_day=item.closing_day, due_day=item.due_day)
                result['items'].append(row)
            remaining -= len(selected)
            if not remaining:
                break
        if identifier is not None and not found:
            raise ActionError('invalid_reference', 404)
        result['has_more'] = len(result['items']) > PAGE_SIZE
        result['items'] = result['items'][:PAGE_SIZE]
        reference(_('Cards'), reverse('banking:list'))
    elif area == 'invoices':
        rows = CardInvoice.objects.filter(user=user).select_related('card__account__bank').prefetch_related('payments')
        if identifier is None:
            rows = rows.filter(reference_month=month)
        for item in select(rows, 'card__name'):
            result['items'].append({'id': item.pk, 'card': item.card.name[:160], 'currency': item.card.account.currency,
                'reference_month': item.reference_month, 'due_date': item.due_date, 'amount': item.amount,
                'gross_amount': item.gross_amount, 'credits_amount': item.credits_amount,
                'credit_balance': item.credit_balance,
                'status': item.status, 'manual_settlement': item.manual_settlement,
                'remaining_today': item.remaining_amount})
            reference(item.card.name, reverse('banking:invoice_detail', args=[item.pk]))
    elif area == 'transactions':
        rows = Transaction.objects.filter(user=user).select_related('category', 'bank_account', 'debit_card__account', 'credit_card__account')
        if identifier is None:
            # Include recurring/installment sources started earlier; their
            # amount_for_month is the canonical economic allocation, not total.
            rows = rows.filter(date__lte=month.replace(day=monthrange(month.year, month.month)[1]))
        for item in select(rows, 'title'):
            result['items'].append({'id': item.pk, 'title': item.title[:160], 'date': item.date,
                'source_amount': item.amount, 'month_amount': item.amount_for_month(month.year, month.month),
                'currency': item.native_currency, 'type': item.transaction_type, 'category_id': item.category_id,
                'category': item.category.name[:160], 'payment_channel': item.payment_channel,
                'installments': item.installments, 'recurring': item.is_fixed,
                **({'notes': item.notes[:2000]} if identifier is not None else {})})
            if not item.reward_redemption_id:
                reference(item.title, reverse('transactions:update', args=[item.pk]))
        result['warnings'].append('Source amounts, month allocations and invoice payments are different measures; never sum them together.')
        result['warnings'].append('Month allocations are scheduled economic amounts, not proof that every occurrence was realized by the cutoff.')
    elif area == 'categories':
        for item in select(Category.objects.filter(user=user)):
            result['items'].append({'id': item.pk, 'name': item.name[:160], 'parent_id': item.parent_category_id, 'type': item.transaction_type})
        reference(_('Categories'), reverse('categories:list'))
    elif area == 'planning':
        from planning.monthly import monthly_outlook
        from planning.services import budget_progress
        outlook = monthly_outlook(user, month, conversion=conversion)
        result['outlook'] = {key: outlook.get(key) for key in ('base_currency', 'cutoff', 'end', 'supported', 'unknown_openings',
            'projected_available', 'projected_reserved', 'unpaid_invoices', 'known_change', 'complete', 'missing_currencies')}
        result['outlook']['recorded_available'] = outlook['recorded']['available_total']
        rows = budget_progress(user, month, as_of=today)
        if identifier is not None and not any(row['budget'].pk == identifier for row in rows):
            raise ActionError('invalid_reference', 404)
        matching = [row for row in rows if (identifier is None or row['budget'].pk == identifier)
                    and query.casefold() in row['budget'].category.name.casefold()]
        for row in matching[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
            item = row['budget']
            result['items'].append({'id': item.pk, 'category_id': item.category_id, 'category': item.category.name[:160],
                'limit': item.amount, 'currency': item.currency, **{key: row[key] for key in ('actual', 'forecast', 'remaining', 'complete', 'missing_currencies')}})
        result['has_more'] = len(matching) > (page + 1) * PAGE_SIZE
        reference(_('Monthly planning'), reverse('planning:index') + f'?month={month:%Y-%m}')
        result['warnings'].append('The outlook covers the entire owned month; the query narrows budget details only.')
    elif area == 'goals':
        from planning.services import goal_progress
        if identifier is not None and not apps.get_model('planning.FinancialGoal').objects.filter(user=user, pk=identifier).exists():
            raise ActionError('invalid_reference', 404)
        rows = [row for row in goal_progress(user, as_of=cutoff, include_archived=identifier is not None) if (identifier is None or row['goal'].pk == identifier)
                and query.casefold() in row['goal'].name.casefold()]
        for row in rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
            item = row['goal']
            result['items'].append({'id': item.pk, 'name': item.name[:160], 'currency': item.currency,
                'target': item.target_amount, 'target_date': item.target_date, 'archived': item.is_archived,
                **{key: row[key] for key in ('progress', 'declared', 'remaining', 'complete', 'missing_currencies')}})
            reference(item.name, reverse('planning:goal_detail', args=[item.pk]))
        result['has_more'] = len(rows) > (page + 1) * PAGE_SIZE
    elif area == 'investments':
        from investments.positions import get_portfolio_valuation
        if identifier is not None and not apps.get_model('investments.Asset').objects.filter(user=user, pk=identifier).exists():
            raise ActionError('invalid_reference', 404)
        snapshot = get_portfolio_valuation(user, as_of=cutoff, base_currency=base, conversion=conversion)
        result['valuation'] = {key: snapshot[key] for key in ('total', 'cost_total', 'realized_total', 'unrealized_total',
            'yield_total', 'complete', 'performance_complete', 'missing_currencies', 'performance_missing_currencies')}
        rows = [row for row in snapshot['positions'] if (identifier is None or row['asset'].pk == identifier)
                and query.casefold() in (row['asset'].name + ' ' + row['product'].name).casefold()]
        for row in rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
            result['items'].append({'asset_id': row['asset'].pk, 'asset': row['asset'].name[:160],
                'product': row['product'].name[:160], 'currency': row['asset'].currency,
                'valuation': row.get('valuation'),
                **{key: row.get(key) for key in ('quantity', 'remaining_cost', 'market_available', 'base_value', 'baseline_unknown')}})
        result['has_more'] = len(rows) > (page + 1) * PAGE_SIZE
        reference(_('Investments'), reverse('investments:list'))
        result['warnings'].append('Valuation totals cover all owned positions at the cutoff; the query narrows position details only.')
    elif area == 'reports':
        from dashboard.services import get_dashboard_summary
        report = get_dashboard_summary(user, month.year, month.month, conversion=conversion)
        result['performance'] = report['performance']
        result.update(period_kind=report['period_kind'], period_cutoff=report['period_cutoff'], missing_currencies=report['missing_currencies'])
        categories = report['expense_categories']
        if identifier is not None:
            if not Category.objects.filter(user=user, pk=identifier).exists():
                raise ActionError('invalid_reference', 404)
            categories = [row for row in categories if row['id'] == identifier]
        categories = [row for row in categories if query.casefold() in row['name'].casefold()]
        result['items'] = [{'id': row['id'], 'name': row['name'][:160], 'total': row['total']}
                           for row in categories[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]]
        result['has_more'] = len(categories) > (page + 1) * PAGE_SIZE
        reference(_('Analytics'), reverse('analytics:index') + f'?month={month:%Y-%m}')
        result['warnings'].append('Performance covers the entire owned month; the query narrows category details only.')
        result['warnings'].append('Category details are limited to the report top categories, not every category; an omitted category is not a zero amount.')
        result['limited_to_report_top_categories'] = True
    elif area == 'exchange_rates':
        for item in select(ExchangeRate.objects.filter(user=user, effective_date__lte=cutoff), 'from_currency'):
            result['items'].append({'id': item.pk, 'from_currency': item.from_currency, 'to_currency': item.to_currency,
                'rate': item.rate, 'effective_date': item.effective_date})
        reference(_('Exchange rates'), reverse('banking:exchange_rates'))
    elif area == 'loyalty':
        from django.db.models import Sum
        from banking.models import LoyaltyEntry
        for item in select(LoyaltyProgram.objects.filter(user=user)):
            totals = dict(LoyaltyEntry.objects.filter(user=user, program=item, date__lte=cutoff).values('direction').annotate(total=Sum('amount')).values_list('direction', 'total'))
            result['items'].append({'id': item.pk, 'name': item.name[:160], 'unit': item.unit_name,
                                   'balance': totals.get('CREDIT', 0) - totals.get('DEBIT', 0)})
        reference(_('Accounts and loyalty'), reverse('banking:list'))
    else:
        from sandbox.models import ScenarioDraft
        for item in select(ScenarioDraft.objects.filter(user=user)):
            row = {'id': item.pk, 'name': item.name[:160], 'kind': item.kind, 'updated_at': item.updated_at}
            if identifier is not None:
                row['payload'] = _scenario_payload(user, item)
            result['items'].append(row)
        reference(_('Saved scenarios'), reverse('sandbox:drafts'))
    # Bound the serialized result, including non-ASCII text, without dropping
    # warnings or presenting an incomplete list as a complete financial total.
    if len(json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=True).encode()) > MAX_RESPONSE_BYTES:
        result['warnings'].append('Response size limit omitted details. Narrow the query or inspect one record; this list is incomplete.')
        result['truncated'] = True
    while len(json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=True).encode()) > MAX_RESPONSE_BYTES:
        if result['items']:
            last = result['items'][-1]
            payload = last.get('payload', {})
            snapshot = payload.get('snapshot', {})
            if snapshot.get('rows'):
                snapshot['rows'].pop()
                snapshot['has_more'] = True
            elif payload.get('inputs'):
                payload['inputs'].pop(next(reversed(payload['inputs'])))
                payload['inputs_truncated'] = True
            else:
                result['items'].pop()
            result['has_more'] = True
        elif result['references']:
            result['references'].pop()
        else:
            raise ActionError('context_too_large')
    return json.loads(json.dumps(result, cls=DjangoJSONEncoder))


def _scenario_payload(user, draft):
    """Selected saved inputs only; never echo arbitrary JSON or credential keys."""
    from sandbox.forms import SalarySandboxForm, YieldSimulationForm

    payload = draft.payload
    if not isinstance(payload, dict) or draft.kind not in {'budget', 'yield'}:
        raise ActionError('invalid_saved_scenario')
    fields = (SalarySandboxForm if draft.kind == 'budget' else YieldSimulationForm).base_fields
    inputs = payload.get('inputs', {})
    if not isinstance(inputs, dict):
        raise ActionError('invalid_saved_scenario')
    selected = {}
    for key, values in inputs.items():
        if (key not in fields and not re.fullmatch(r'(contribution|withdrawal)_\d{1,3}|variable_(label|type|value)', key)):
            continue
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ActionError('invalid_saved_scenario')
        selected[key] = [value[:2000] for value in values[:20]]
    result = {key: payload[key] for key in ('schema_version', 'calculation_version', 'tax_rule_year', 'complete')
              if type(payload.get(key)) in (int, bool)}
    result['inputs'] = selected
    input_format = payload.get('input_format', {})
    if isinstance(input_format, dict):
        result['input_format'] = {key: value for key, value in input_format.items()
                                  if isinstance(value, str) and (key, value) in {('date_order', 'DMY'), ('date_order', 'MDY'),
                                                     ('month', 'YYYY-MM'), ('decimal', '.')}}
    snapshot = payload.get('snapshot')
    if snapshot is not None:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('rows'), list):
            raise ActionError('invalid_saved_scenario')
        if type(snapshot.get('user_id')) is not int or snapshot['user_id'] != user.pk:
            raise ActionError('inconsistent_ownership', 409)
        allowed = {'key', 'label', 'native_amount', 'currency', 'amount', 'payment_date', 'reference_month',
                   'instrument', 'kind', 'installment', 'included', 'override', 'source_removed'}
        rows = [{key: value[:2000] if isinstance(value, str) else value for key, value in row.items()
                 if key in allowed and (value is None or type(value) in (str, bool, int))}
                for row in snapshot['rows'][:PAGE_SIZE] if isinstance(row, dict)]
        result['snapshot'] = {key: snapshot[key][:200] for key in
                              ('start_month', 'currency', 'month_basis', 'captured_at') if isinstance(snapshot.get(key), str)}
        result['snapshot'].update(rows=rows, has_more=len(snapshot['rows']) > len(rows), captured=True)
    return result
