# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Expiring owned page scopes and bounded read-only financial evidence.

The collector never calls page views, projection services or get_or_create.
Current page hints contain only resolved routes and their supported GET filters.
"""
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.apps import apps
from django.core import signing
from django.db.models import Q
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_noop

from accounts.models import UserPreference
from banking.models import BankAccount
from banking.services import account_balance
from core.currencies import CURRENCIES, DEFAULT_CURRENCY
from core.navigation import safe_local_url


SCOPE_SALT = 'assistant.page-scope.v1'
SCOPE_MAX_AGE = 3600
MAX_LOCATION = 2048
MAX_ROWS = 20

_ROUTES = {
    'analytics': {'index', 'investments'},
    'dashboard': {'index', 'reports'},
    'transactions': {'list', 'create', 'update', 'split'},
    'categories': {'list', 'create', 'update'},
    'banking': {'list', 'detail', 'invoices', 'card_invoices', 'invoice_detail',
                'account_create', 'account_update', 'credit_card_create', 'credit_card_update',
                'debit_card_create', 'debit_card_update', 'exchange_rates'},
    'investments': {'list', 'operations', 'charts', 'prices', 'settings', 'position_detail',
                    'position_update', 'guided_create', 'create', 'update', 'create_asset',
                    'update_asset', 'create_product', 'update_product'},
    'planning': {'index', 'tools', 'budgets', 'budget_create', 'budget_update', 'goals',
                 'goal_create', 'goal_detail', 'goal_update', 'signals', 'signals_settings'},
    'sandbox': {'index', 'simulation', 'drafts', 'draft_detail'},
    'ingestion': {'history', 'detail'},
    'accounts': {'settings'},
}
_LABELS = {'analytics': gettext_noop('Analytics'), 'dashboard': gettext_noop('Home'), 'transactions': gettext_noop('Transactions'),
           'categories': gettext_noop('Categories'), 'banking': gettext_noop('Accounts'),
           'investments': gettext_noop('Investments'), 'planning': gettext_noop('Plan'),
           'sandbox': gettext_noop('Simulations'), 'ingestion': gettext_noop('Reviewed statements'),
           'accounts': gettext_noop('Settings')}
_MONTHS = {'month', 'instrument_month', 'installment_month'}
_DATES = {'date', 'date_from', 'date_to', 'start', 'end'}
_RECORD_FILTERS = {'bank': 'banking.Bank', 'account': 'banking.BankAccount',
                   'credit_card': 'banking.CreditCard', 'debit_card': 'banking.DebitCard',
                   'category': 'categories.Category', 'product': 'investments.InvestmentProduct',
                   'asset': 'investments.Asset', 'parent': 'categories.Category'}
_FILTERS = {
    'analytics': {'month', 'charts_offset', 'instrument_month', 'installment_month',
                  'scope', 'total_offset', 'flow_offset'},
    'dashboard': {'month', 'charts_offset', 'instrument_month', 'installment_month'},
    'transactions': {'q', 'month', 'date', 'type', 'category', 'recurrence', 'sort', 'page',
                     'account', 'credit_card', 'debit_card', 'transaction_type'},
    'categories': {'q', 'level', 'type', 'page', 'parent'},
    'banking': {'q', 'month', 'bank', 'status', 'page', 'account', 'date_from', 'date_to',
                'from_currency', 'to_currency'},
    'investments': {'q', 'section', 'scope', 'bank', 'product', 'asset', 'date_from', 'date_to',
                    'currency', 'kind', 'page'},
    'planning': {'month', 'q', 'page', 'archived', 'reviewed'},
    'sandbox': {'draft', 'page'},
    'ingestion': {'q', 'page'},
    'accounts': set(),
}
_ROUTE_FILTERS = {
    'analytics:index': {'month', 'charts_offset', 'instrument_month', 'installment_month'},
    'analytics:investments': {'scope', 'total_offset', 'flow_offset'},
}
_ENUMS = {
    ('analytics', 'scope'): {'portfolio', 'cash', 'all'},
    ('transactions', 'type'): {'INCOME', 'EXPENSE'},
    ('transactions', 'transaction_type'): {'INCOME', 'EXPENSE'},
    ('transactions', 'recurrence'): {'fixed', 'installment', 'oneoff'},
    ('transactions', 'sort'): {'newest', 'oldest', 'updated', 'highest', 'lowest'},
    ('categories', 'level'): {'top', 'sub'},
    ('categories', 'type'): {'INCOME', 'EXPENSE', 'unclassified'},
    ('banking', 'status'): {'SCHEDULED', 'PARTIAL', 'PAID', 'OVERDUE'},
    ('investments', 'section'): {'portfolio', 'cash', 'all'},
    ('investments', 'scope'): {'portfolio', 'cash', 'all'},
    ('investments', 'kind'): {'DEPOSIT', 'WITHDRAWAL', 'YIELD'},
    ('planning', 'archived'): {'0', '1'},
    ('planning', 'reviewed'): {'0', '1'},
}


class ScopeError(ValueError):
    pass


def _owned(user, model, identifier):
    try:
        key = int(identifier)
    except (ValueError, TypeError):
        raise ScopeError(_('Invalid assistant context.')) from None
    if str(key) != str(identifier) or not 1 <= key <= 9223372036854775807:
        raise ScopeError(_('Invalid assistant context.'))
    instance = apps.get_model(model).objects.filter(user=user, pk=key).first()
    if instance is None:
        raise ScopeError(_('This assistant context is no longer available.'))
    return instance


def _route_ownership(user, match):
    route, values = match.view_name, match.kwargs
    if not values:
        return
    mappings = {
        'transactions:update': 'transactions.Transaction', 'transactions:split': 'transactions.Transaction',
        'categories:update': 'categories.Category', 'banking:detail': 'banking.Bank',
        'banking:account_update': 'banking.BankAccount', 'banking:credit_card_update': 'banking.CreditCard',
        'banking:debit_card_update': 'banking.DebitCard', 'banking:invoice_detail': 'banking.CardInvoice',
        'investments:update': 'investments.Investment', 'investments:update_asset': 'investments.Asset',
        'investments:update_product': 'investments.InvestmentProduct',
        'planning:budget_update': 'planning.CategoryBudget', 'planning:goal_detail': 'planning.FinancialGoal',
        'planning:goal_update': 'planning.FinancialGoal', 'sandbox:draft_detail': 'sandbox.ScenarioDraft',
        'ingestion:detail': 'ingestion.ImportBatch',
    }
    if route in mappings:
        item = _owned(user, mappings[route], values['pk'])
        if route == 'ingestion:detail' and item.status not in {'CONFIRMED', 'UNDONE'}:
            raise ScopeError(_('This assistant context is no longer available.'))
    elif route == 'banking:card_invoices':
        _owned(user, 'banking.CreditCard', values['card_pk'])
    elif route in {'investments:position_detail', 'investments:position_update'}:
        _owned(user, 'investments.InvestmentProduct', values['product_pk'])
        _owned(user, 'investments.Asset', values['asset_pk'])
    else:
        raise ScopeError(_('Invalid assistant context.'))


def normalize_location(user, location):
    if not user.is_authenticated or not isinstance(location, str) or not location or len(location) > MAX_LOCATION:
        raise ScopeError(_('Invalid assistant context.'))
    if '\\' in location or any(ord(char) < 32 or ord(char) == 127 for char in location):
        raise ScopeError(_('Invalid assistant context.'))
    parsed = urlsplit(location)
    if parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith('/') or parsed.path.startswith('//'):
        raise ScopeError(_('Invalid assistant context.'))
    try:
        match = resolve(parsed.path)
    except Resolver404:
        raise ScopeError(_('Invalid assistant context.')) from None
    if match.namespace not in _ROUTES or match.url_name not in _ROUTES[match.namespace]:
        raise ScopeError(_('Assistant context is unavailable on this page.'))
    _route_ownership(user, match)
    filters, seen = {}, set()
    for key, value in parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=30):
        if key in seen:
            raise ScopeError(_('Invalid assistant context.'))
        seen.add(key)
        if key == 'next':
            if value and not safe_local_url(value):
                raise ScopeError(_('Invalid assistant context.'))
            continue  # Navigation origins never widen the financial context.
        allowed_filters = _ROUTE_FILTERS.get(match.view_name, _FILTERS[match.namespace])
        if key not in allowed_filters or len(value) > 160:
            raise ScopeError(_('Unsupported assistant context filter.'))
        if not value:
            continue
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ScopeError(_('Invalid assistant context filter.'))
        if key in _RECORD_FILTERS:
            _owned(user, _RECORD_FILTERS[key], value)
        elif key == 'draft':
            _owned(user, 'sandbox.ScenarioDraft', value)
        elif key in _MONTHS:
            if value != 'ALL' or key == 'month':
                try:
                    if len(value) != 7 or date.fromisoformat(value + '-01').strftime('%Y-%m') != value:
                        raise ValueError
                except ValueError:
                    raise ScopeError(_('Invalid assistant context date.')) from None
        elif key in _DATES:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                raise ScopeError(_('Invalid assistant context date.')) from None
        elif key in {'page', 'charts_offset', 'total_offset', 'flow_offset'}:
            try:
                number = int(value)
                is_offset = key in {'charts_offset', 'total_offset', 'flow_offset'}
                if str(number) != value or not (-1200 <= number <= 1200 if is_offset else 1 <= number <= 10000):
                    raise ValueError
            except ValueError:
                raise ScopeError(_('Invalid assistant context filter.')) from None
        elif key in {'currency', 'from_currency', 'to_currency'} and value not in CURRENCIES:
            raise ScopeError(_('Invalid assistant context currency.'))
        elif (match.namespace, key) in _ENUMS and value not in _ENUMS[match.namespace, key]:
            raise ScopeError(_('Invalid assistant context filter.'))
        filters[key] = value
    query = urlencode(sorted(filters.items()))
    return {'location': parsed.path + ('?' + query if query else ''), 'route': match.view_name,
            'namespace': match.namespace, 'kwargs': match.kwargs, 'filters': filters}


def sign_scope(user, location):
    scope = normalize_location(user, location)
    return sign_normalized_scope(user, scope)


def sign_normalized_scope(user, scope):
    """Sign a scope already authorized by normalize_location/read_scope."""
    return signing.dumps({'v': 1, 'user': user.pk, 'location': scope['location']}, salt=SCOPE_SALT, compress=True)


def read_scope(user, token, *, location=None):
    if not isinstance(token, str) or not token or len(token) > 4096:
        raise ScopeError(_('Open the assistant again from an available workspace.'))
    try:
        payload = signing.loads(token, salt=SCOPE_SALT, max_age=SCOPE_MAX_AGE)
    except signing.BadSignature:
        raise ScopeError(_('This assistant context expired or is invalid. Open it again from the workspace.')) from None
    if not isinstance(payload, dict) or payload.get('v') != 1 or payload.get('user') != user.pk:
        raise ScopeError(_('This assistant context belongs to another session.'))
    return normalize_location(user, payload.get('location') if location is None else location)


def scope_label(scope):
    label = _(_LABELS[scope['namespace']])
    month = scope['filters'].get('month')
    return f'{label} · {month}' if month else label


def _bounded(queryset, snapshot):
    rows = list(queryset[:MAX_ROWS + 1])
    if len(rows) > MAX_ROWS:
        snapshot['warnings'].append(_('Only the first %(limit)s matching sources are shown.') % {'limit': MAX_ROWS})
    return rows[:MAX_ROWS]


def collect_context(user, scope):
    """Serialize bounded stored evidence, never refresh projections or contact a provider."""
    captured_at = timezone.now()
    today = timezone.localdate(captured_at)
    currency = UserPreference.objects.filter(user=user).values_list('base_currency', flat=True).first() or DEFAULT_CURRENCY
    snapshot = {'captured_at': captured_at.isoformat(), 'cutoff': today.isoformat(), 'currency': currency,
                'workspace_label': scope_label(scope), 'metrics': [], 'warnings': [], 'sources': []}
    namespace, filters, route = scope['namespace'], scope['filters'], scope['route']
    snapshot['warnings'].append(_('Stored records only. Financial projections were not refreshed.'))
    snapshot['sources'].append({'label': scope_label(scope), 'url': scope['location']})
    if namespace in {'dashboard', 'banking'}:
        accounts = BankAccount.objects.filter(user=user, bank__user=user).select_related('bank').order_by('pk')
        if namespace == 'banking' and route == 'banking:detail':
            accounts = accounts.filter(bank_id=scope['kwargs']['pk'])
        if filters.get('bank'):
            accounts = accounts.filter(bank_id=filters['bank'])
        if filters.get('account'):
            accounts = accounts.filter(pk=filters['account'])
        # Invoice/report filters describe a different economic scope; do not
        # pretend current cash is their scoped total.
        if route not in {'dashboard:index', 'banking:list', 'banking:detail'} or filters:
            snapshot['warnings'].append(_('Detailed calculations for this filtered page are not included in this context.'))
        else:
            for account in _bounded(accounts, snapshot):
                # Malformed legacy ownership must not let another user's row
                # enter the otherwise canonical account balance calculation.
                if account.movements.exclude(user=user).exists():
                    snapshot['warnings'].append(_('An account balance was omitted because its stored ownership is inconsistent.'))
                    continue
                snapshot['metrics'].append({'label': account.name[:100], 'value': format(account_balance(account, as_of=today), '.2f'), 'currency': account.currency})
                snapshot['sources'].append({'label': account.name[:100], 'url': reverse('banking:detail', args=[account.bank_id]) + f'#account-row-{account.pk}'})
                if account.opening_balance and account.opening_date is None:
                    snapshot['warnings'].append(_('An account has an unknown opening date.'))
    elif namespace == 'transactions':
        from transactions.models import Transaction
        records = Transaction.objects.filter(user=user).select_related('bank_account', 'debit_card__account', 'credit_card__account').order_by('-date', '-pk')
        if scope['kwargs'].get('pk'):
            records = records.filter(pk=scope['kwargs']['pk'])
        if filters or route == 'transactions:create':
            snapshot['warnings'].append(_('Detailed calculations for this filtered page are not included in this context.'))
        else:
            owned_instrument = (Q(bank_account__user=user, bank_account__bank__user=user)
                | Q(debit_card__user=user, debit_card__account__user=user, debit_card__account__bank__user=user)
                | Q(credit_card__user=user, credit_card__account__user=user, credit_card__account__bank__user=user))
            for item in _bounded(records.filter(owned_instrument), snapshot):
                meaning = (_('Recurring template') if item.is_fixed else
                           _('Installment source') if item.installments > 1 else _('Dated source'))
                if item.date > today:
                    meaning = _('%(meaning)s; future date') % {'meaning': meaning}
                snapshot['metrics'].append({'label': _('%(type)s source: %(title)s · %(date)s · %(meaning)s') % {
                                                'type': item.get_transaction_type_display(), 'title': item.display_title[:100],
                                                'date': item.date.isoformat(), 'meaning': meaning},
                                            'value': str(item.amount), 'currency': item.native_currency})
                if not item.reward_redemption_id:
                    snapshot['sources'].append({'label': item.display_title[:100], 'url': reverse('transactions:update', args=[item.pk])})
            snapshot['warnings'].append(_('Source amounts are not realized cash flows, category split totals, account balances or installment-month totals.'))
    else:
        snapshot['warnings'].append(_('This page is available as an owned source. Its detailed figures are not automatically copied.'))
    if snapshot['metrics']:
        snapshot['warnings'].append(_('Amounts retain their native currencies; no currency conversion was performed.'))
    return snapshot
