# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Minimize one authorized request; never collect finances without its opt-in."""
from html import unescape
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.utils import timezone, translation
from django.utils.html import strip_tags

from banking.models import BankAccount
from core.currencies import CURRENCIES

from .context import MAX_ROWS, ScopeError, collect_context, normalize_location, scope_label


MAX_CONTEXT_CHARACTERS = 32000
_PERIOD_FILTERS = frozenset({'month', 'instrument_month', 'installment_month',
                             'date', 'date_from', 'date_to', 'start', 'end', 'charts_offset'})
_TRUNCATION_WARNING = 'Some context was omitted or shortened to keep this request within its size limit.'
_REFERENCE_WARNING = 'Some unavailable source references were omitted.'


def _text(value, limit):
    if not isinstance(value, str):
        return ''
    # Record labels are data. Removing markup/control characters limits the
    # copied surface without pretending to solve prompt injection by escaping.
    plain = strip_tags(unescape(value[:4096]))
    plain = ''.join(char if ord(char) >= 32 and ord(char) != 127 else ' ' for char in plain)
    return ' '.join(plain.split())[:limit]


def _periods(scope):
    return {key: value for key, value in sorted(scope['filters'].items()) if key in _PERIOD_FILTERS}


def _reference_url(user, value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ScopeError('Invalid assistant source reference.')
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or '\\' in value or any(ord(char) < 32 for char in value):
        raise ScopeError('Invalid assistant source reference.')
    pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=30)
    query = urlencode(sorted((key, item) for key, item in pairs if key in _PERIOD_FILTERS))
    location = parsed.path + ('?' + query if query else '')
    verified = normalize_location(user, location)
    if parsed.fragment:
        anchor = re.fullmatch(r'account-row-([1-9][0-9]{0,18})', parsed.fragment)
        if (verified['route'] != 'banking:detail' or not anchor
                or not BankAccount.objects.filter(user=user, bank__user=user,
                                                  bank_id=verified['kwargs']['pk'], pk=int(anchor[1])).exists()):
            raise ScopeError('Invalid assistant source reference.')
    return verified['location'] + ('#' + parsed.fragment if parsed.fragment else '')


def _warning(result, value):
    if value and value not in result['warnings']:
        result['warnings'].append(value)


def _fit(result):
    """Bound the default JSON form, including Unicode escapes and whitespace.

    Compact transport serialization is smaller. Remove complete trailing rows
    before touching evidence warnings; the stable warning makes any loss explicit.
    """
    def size():
        return len(json.dumps(result, ensure_ascii=True, allow_nan=False))

    if size() <= MAX_CONTEXT_CHARACTERS:
        return result
    _warning(result, _TRUNCATION_WARNING)
    while size() > MAX_CONTEXT_CHARACTERS:
        if result['metrics']:
            result['metrics'].pop()
        elif len(result['references']) > 1:
            result['references'].pop()
        else:
            candidates = [(len(value), -index, index) for index, value in enumerate(result['warnings'])
                          if value != _TRUNCATION_WARNING and len(value) > 32]
            if not candidates:
                # Header/reference fields are independently bounded. This is a
                # last-resort safeguard if their contract grows in the future.
                result['references'].clear()
                result['warnings'] = [_TRUNCATION_WARNING]
                break
            _, _, index = max(candidates)
            warning = result['warnings'][index]
            result['warnings'][index] = warning[:max(32, len(warning) // 2)]
    return result


def build_context(user, scope, include_financial=False):
    """Return bounded page metadata, optionally adding the existing financial slice.

    ``scope`` is a normalized/read_scope dictionary or None. Re-resolving its
    location rechecks ownership; caller-supplied labels, route IDs or metrics are
    never authoritative. No scope remains finance-free even when opt-in is true.
    ``json.dumps(result)`` is at most 32,000 characters; compact JSON is supported.
    """
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        raise ScopeError('Invalid assistant context owner.')
    if type(include_financial) is not bool:
        raise ScopeError('Invalid assistant context selection.')
    captured_at = timezone.now()
    result = {'captured_at': captured_at.isoformat(), 'cutoff': timezone.localdate(captured_at).isoformat(),
              'language': 'pt-br' if (translation.get_language() or '').lower().startswith('pt') else 'en'}
    if scope is None:
        return result
    if not isinstance(scope, dict) or not isinstance(scope.get('location'), str):
        raise ScopeError('Invalid assistant page context.')
    verified = normalize_location(user, scope['location'])
    result['current_page'] = {'label': scope_label(verified), 'route': verified['route'], 'filters': _periods(verified)}
    if not include_financial:
        return result

    snapshot = collect_context(user, verified)
    result.update(captured_at=snapshot['captured_at'], cutoff=snapshot['cutoff'],
                  metrics=[], warnings=[], references=[])
    if snapshot.get('currency') in CURRENCIES:
        result['currency'] = snapshot['currency']
    kind = ('source_amount' if verified['namespace'] == 'transactions' else
            'stored_account_balance' if verified['namespace'] in {'dashboard', 'banking'} else 'stored_metric')
    metrics = snapshot.get('metrics', [])
    for metric in metrics[:MAX_ROWS]:
        if not isinstance(metric, dict):
            _warning(result, _TRUNCATION_WARNING)
            continue
        value, currency = metric.get('value'), metric.get('currency')
        if (not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', value)
                or not isinstance(currency, str) or currency not in CURRENCIES):
            _warning(result, _TRUNCATION_WARNING)
            continue
        label = _text(metric.get('label'), 240)
        result['metrics'].append({'label': label, 'value': value, 'currency': currency, 'kind': kind})
        if isinstance(metric.get('label'), str) and len(metric['label']) > 240:
            _warning(result, _TRUNCATION_WARNING)
    warnings = snapshot.get('warnings', [])
    for warning in warnings[:32]:
        cleaned = _text(warning, 240)
        _warning(result, cleaned)
        if isinstance(warning, str) and len(warning) > 240:
            _warning(result, _TRUNCATION_WARNING)
    sources = snapshot.get('sources', [])
    seen = set()
    for source in sources[:MAX_ROWS + 1]:
        if not isinstance(source, dict):
            _warning(result, _REFERENCE_WARNING)
            continue
        try:
            url = _reference_url(user, source.get('url'))
        except (ScopeError, ValueError):
            _warning(result, _REFERENCE_WARNING)
            continue
        if url in seen:
            continue
        seen.add(url)
        result['references'].append({'label': _text(source.get('label'), 160), 'url': url})
        if isinstance(source.get('label'), str) and len(source['label']) > 160:
            _warning(result, _TRUNCATION_WARNING)
    if len(metrics) > MAX_ROWS or len(sources) > MAX_ROWS + 1 or len(warnings) > 32:
        _warning(result, _TRUNCATION_WARNING)
    return _fit(result)
