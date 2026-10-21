# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bounded ChatGPT-plan model catalogue and Responses SSE; no fallback/retry.

Injected transports accept ``(method, url, *, access_token, data=None,
stream=False, cancellation=None)`` and return TransportResponse. Stream bodies
provide ``readline(limit) -> bytes`` and ``close()``. Credentials remain on this
server, and tests supply synthetic data without opening sockets.
"""
from dataclasses import dataclass, field
import json
import logging
import re
import socket
import ssl
from threading import Timer
import time
from urllib import error, request

from django.conf import settings

from assistant.connections import service
from assistant.providers.base import (
    CancellationToken, ProviderError, ProviderEvent, ProviderUnavailable, _outside_transaction,
    reasoning_efforts, valid_model,
)


MODELS_ENDPOINT = 'https://api.openai.com/v1/models'
RESPONSES_ENDPOINT = 'https://api.openai.com/v1/responses'
MAX_EVENT_BYTES = 512 * 1024
# Account catalogues include rich per-model metadata beyond the UI capabilities.
# Keep that JSON bound separate from individual SSE events and request bodies.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ERROR_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 16000
READ_TIMEOUT = 15
TOTAL_TIMEOUT = 90
MAX_TOOL_ROUNDS = 5
MAX_TOOL_CALLS = 10
MAX_TOOL_BYTES = 16 * 1024
MAX_TOOL_HISTORY_BYTES = 384 * 1024
logger = logging.getLogger(__name__)

# Provider messages/detail can echo submitted private text. Only these exact
# machine values may survive the transport boundary or enter diagnostics.
_ERROR_CODE_MAP = {
    'missing_required_parameter': 'request_rejected',
    'invalid_value': 'request_rejected',
    'invalid_type': 'request_rejected',
    'unsupported_parameter': 'request_rejected',
    'unsupported_value': 'request_rejected',
    'unknown_parameter': 'request_rejected',
    'model_not_found': 'invalid_model',
    'subscription_sharing_user_not_eligible': 'permission_denied',
    'subscription_sharing_usage_limit_exceeded': 'rate_limited',
    'subscription_sharing_usage_unavailable': 'unavailable',
    'subscription_sharing_unsupported_capability': 'request_rejected',
    'subscription_sharing_route_not_supported': 'permission_denied',
    'subscription_sharing_invalid_user': 'unauthorized',
    'chatpass_v2_scope_not_authorized': 'permission_denied',
    'chatpass_v2_invalid_authorization_context': 'permission_denied',
    'subscription_sharing_user_unavailable': 'unavailable',
}
_ERROR_TYPES = frozenset({'invalid_request_error', 'authentication_error', 'permission_error',
                          'rate_limit_error', 'server_error'})
_ERROR_PARAMETERS = frozenset({'model', 'input', 'instructions', 'store', 'stream', 'reasoning', 'reasoning.effort',
                               'tools', 'include'})
_PROTOCOL_ERRORS = frozenset({'unexpected_content_type', 'invalid_json', 'invalid_schema', 'invalid_sse'})
_PROTOCOL_STAGES = frozenset({'tool_namespace', 'tool_name', 'tool_call_id', 'tool_status',
                              'tool_arguments', 'tool_output', 'tool_result', 'response_output',
                              'stream_item', 'response_output_shape', 'response_output_conflict',
                              'response_output_missing', 'response_completion'})
_CONTENT_TYPES = frozenset({'text/plain', 'application/json', 'application/octet-stream', 'text/event-stream'})
_BODY_KINDS = frozenset({'sse_prefix', 'response_object', 'error_object', 'other'})


def _safe_error(body):
    detail = body.get('error') if isinstance(body, dict) else None
    if not isinstance(detail, dict):
        return {}
    result = {}
    for key, allowed in [('code', _ERROR_CODE_MAP), ('type', _ERROR_TYPES), ('param', _ERROR_PARAMETERS)]:
        value = detail.get(key)
        if isinstance(value, str) and value in allowed:
            result[key] = value
    return {'error': result} if result else {}


def _diagnostic(status, detail, *, expected_content_type=None, actual_content_type=None,
                body_kind=None, response_error=None, protocol_stage=None):
    safe = _safe_error(detail).get('error', {})
    response_error = _safe_error(response_error).get('error', {})
    code = safe.get('code', safe.get('type', 'unknown'))
    if isinstance(detail, str) and detail in _PROTOCOL_ERRORS:
        code = detail
    # No exception info, request IDs, identity, headers, body or arbitrary strings.
    message = 'OpenAI provider failure status=%s code=%s param=%s'
    fields = [status if type(status) is int and 100 <= status <= 599 else 0,
              code, safe.get('param', response_error.get('param', 'unknown'))]
    if protocol_stage is not None:
        message += ' stage=%s'
        fields.append(protocol_stage if protocol_stage in _PROTOCOL_STAGES else 'other')
    if expected_content_type is not None or actual_content_type is not None:
        message += ' expected_content_type=%s actual_content_type=%s'
        fields.extend([expected_content_type if expected_content_type in _CONTENT_TYPES else 'other',
                       actual_content_type if actual_content_type in _CONTENT_TYPES | {'missing'} else 'other'])
    if body_kind is not None:
        message += ' body_kind=%s response_error_code=%s response_error_type=%s'
        fields.extend([body_kind if body_kind in _BODY_KINDS else 'other',
                       response_error.get('code', 'unknown'), response_error.get('type', 'unknown')])
    logger.warning(message, *fields)


def _invalid_response(reason, **content_types):
    _diagnostic(200, reason, **content_types)
    raise ProviderError('invalid_response') from None


def _unexpected_body(source, cancellation, deadline, prefix=None):
    # This is classification, never an alternate success parser. A first SSE
    # line is enough to diagnose a mislabeled stream without draining it.
    prefix = source.readline(MAX_ERROR_BYTES) if prefix is None else prefix
    cancellation.raise_if_cancelled()
    if time.monotonic() >= deadline:
        raise ProviderError('timeout')
    if prefix.lstrip().startswith((b'data:', b'event:', b':')):
        return 'sse_prefix', {}
    if len(prefix) < MAX_ERROR_BYTES:
        prefix += source.read(MAX_ERROR_BYTES - len(prefix))
        cancellation.raise_if_cancelled()
        if time.monotonic() >= deadline:
            raise ProviderError('timeout')
    try:
        body = json.loads(prefix.decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError):
        return 'other', {}
    if not isinstance(body, dict):
        return 'other', {}
    safe = _safe_error(body)
    if body.get('object') == 'response':
        return 'response_object', safe
    if isinstance(body.get('error'), dict):
        return 'error_object', safe
    return 'other', safe


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: dict | None = field(default=None, repr=False)
    stream: object = field(default=None, repr=False)


class _NoRedirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _enabled():
    if (getattr(settings, 'ASSISTANT_OPENAI_AUTH_ENABLED', False) is not True
            or getattr(settings, 'ASSISTANT_OPENAI_INFERENCE_ENABLED', False) is not True):
        raise ProviderUnavailable()


class _HTTPStream:
    def __init__(self, response, cancellation, deadline):
        self.response = response
        self.deadline = deadline
        self.closed = False
        self._prefix = b''
        self._timer = Timer(max(0, deadline - time.monotonic()), self.close)
        self._timer.daemon = True
        self._unregister = cancellation.register_close(self.close)
        if not self.closed:
            self._timer.start()

    def readline(self, limit):
        if time.monotonic() >= self.deadline:
            raise ProviderError('timeout')
        if self._prefix:
            newline = self._prefix.find(b'\n', 0, limit)
            end = newline + 1 if newline >= 0 else min(limit, len(self._prefix))
            prefix, self._prefix = self._prefix[:end], self._prefix[end:]
            if newline >= 0 or len(prefix) == limit:
                return prefix
            return prefix + self.response.readline(limit - len(prefix))
        return self.response.readline(limit)

    def read(self, limit):
        if time.monotonic() >= self.deadline:
            raise ProviderError('timeout')
        if self._prefix:
            prefix, self._prefix = self._prefix[:limit], self._prefix[limit:]
            return prefix + self.response.read(limit - len(prefix))
        return self.response.read(limit)

    def prepend_line(self, line):
        self._prefix = line + self._prefix

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._prefix = b''
        if hasattr(self, '_timer'):
            self._timer.cancel()
        if hasattr(self, '_unregister'):
            self._unregister()
        # Shutdown interrupts a concurrent blocked socket read before buffered
        # response.close() waits for its lock. The read timeout remains a bound.
        raw_socket = getattr(getattr(getattr(self.response, 'fp', None), 'raw', None), '_sock', None)
        try:
            if raw_socket:
                raw_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.response.close()
        except Exception:
            pass


class HTTPTransport:
    def __call__(self, method, url, *, access_token, data=None, stream=False, cancellation=None, deadline=None):
        _enabled()
        _outside_transaction()
        if (method, url, stream) not in {('GET', MODELS_ENDPOINT, False), ('POST', RESPONSES_ENDPOINT, True)}:
            raise ProviderError()
        cancellation = cancellation or CancellationToken()
        cancellation.raise_if_cancelled()
        if (not isinstance(access_token, str) or not access_token or len(access_token) > 16384
                or any(ord(char) < 33 or ord(char) > 126 for char in access_token)):
            raise ProviderError('unauthorized')
        deadline = time.monotonic() + TOTAL_TIMEOUT if deadline is None else deadline
        response_stream = None
        try:
            payload = None if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if payload is not None and len(payload) > 512 * 1024:
                raise ProviderError('limit_exceeded')
            headers = {'Authorization': 'Bearer ' + access_token,
                       'Accept': 'text/event-stream' if stream else 'application/json'}
            if payload is not None:
                headers['Content-Type'] = 'application/json'
            opener = request.build_opener(request.ProxyHandler({}), _NoRedirects(),
                                          request.HTTPSHandler(context=ssl.create_default_context()))
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderError('timeout')
                response = opener.open(request.Request(url, data=payload, headers=headers, method=method),
                                       timeout=min(READ_TIMEOUT, remaining))
            except error.HTTPError as rejected:
                response = rejected
            response_stream = _HTTPStream(response, cancellation, deadline)
            if response.status != 200:
                # Errors may be JSON, HTML or a direct-admission detail string.
                # Discard all free text before passing anything to the provider.
                body = {}
                if response.headers.get_content_type() == 'application/json':
                    raw = response_stream.read(MAX_ERROR_BYTES + 1)
                    cancellation.raise_if_cancelled()
                    if time.monotonic() >= deadline:
                        raise ProviderError('timeout')
                    if len(raw) <= MAX_ERROR_BYTES:
                        try:
                            body = _safe_error(json.loads(raw.decode('utf-8')))
                        except (ValueError, UnicodeError, RecursionError):
                            pass
                return TransportResponse(response.status, body=body)
            expected = 'text/event-stream' if stream else 'application/json'
            missing_content_type = response.headers.get('Content-Type') is None
            first_line = None
            if stream and missing_content_type:
                # The subscription route can omit Content-Type on a valid SSE
                # response. Replay this bounded line through the same parser;
                # all JSON schemas, frame limits and completion rules still run.
                first_line = response_stream.readline(MAX_ERROR_BYTES)
                cancellation.raise_if_cancelled()
                if time.monotonic() >= deadline:
                    raise ProviderError('timeout')
                if (first_line.startswith((b'data:', b'event:', b':'))
                        and (len(first_line) < MAX_ERROR_BYTES or first_line.endswith(b'\n'))):
                    response_stream.prepend_line(first_line)
                    result = TransportResponse(response.status, stream=response_stream)
                    response_stream = None
                    return result
            if missing_content_type or response.headers.get_content_type() != expected:
                body_kind, safe_error = _unexpected_body(response_stream, cancellation, deadline, first_line)
                _invalid_response('unexpected_content_type', expected_content_type=expected,
                    actual_content_type=response.headers.get_content_type()
                    if not missing_content_type else 'missing',
                    body_kind=body_kind, response_error=safe_error)
            if stream:
                result = TransportResponse(response.status, stream=response_stream)
                response_stream = None
                return result
            body = response_stream.read(MAX_RESPONSE_BYTES + 1)
            cancellation.raise_if_cancelled()
            if time.monotonic() >= deadline:
                raise ProviderError('timeout')
            if len(body) > MAX_RESPONSE_BYTES:
                raise ProviderError('limit_exceeded')
            try:
                decoded = json.loads(body.decode('utf-8'))
            except (ValueError, UnicodeError, RecursionError):
                _invalid_response('invalid_json')
            if not isinstance(decoded, dict):
                _invalid_response('invalid_schema')
            return TransportResponse(response.status, body=decoded)
        except ProviderError:
            raise
        except (TimeoutError, socket.timeout):
            cancellation.raise_if_cancelled()
            raise ProviderError('timeout') from None
        except Exception:
            cancellation.raise_if_cancelled()
            if time.monotonic() >= deadline:
                raise ProviderError('timeout') from None
            raise ProviderError('transport_error') from None
        finally:
            if response_stream is not None:
                response_stream.close()


def _status(response):
    if (not isinstance(response, TransportResponse) or type(response.status) is not int
            or not 100 <= response.status <= 599):
        _invalid_response('invalid_schema')
    if response.status == 200:
        return
    detail = _safe_error(response.body)
    _diagnostic(response.status, detail)
    # Status takes precedence for admission failures and temporary infrastructure.
    code = {400: 'request_rejected', 401: 'unauthorized', 403: 'permission_denied',
            422: 'request_rejected', 429: 'rate_limited', 502: 'unavailable',
            503: 'unavailable', 504: 'unavailable'}.get(response.status, 'provider_error')
    if response.status in {400, 404, 422}:
        code = _ERROR_CODE_MAP.get(detail.get('error', {}).get('code'), code)
    raise ProviderError(code)


def _error_code(event):
    nested = event.get('response', {}).get('error', {}) if isinstance(event.get('response'), dict) else {}
    detail = event.get('error') if isinstance(event.get('error'), dict) else nested
    if not detail:
        detail = event
    safe = _safe_error({'error': detail})
    _diagnostic(200, safe)
    return _ERROR_CODE_MAP.get(safe.get('error', {}).get('code'), 'provider_error')


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate tool parameter.')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite tool parameter.')


def _bounded_tool_json(value, limit):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        size = len(encoded.encode('utf-8'))
    except (TypeError, ValueError, RecursionError, UnicodeError):
        _invalid_response('invalid_schema')
    if size > limit:
        raise ProviderError('limit_exceeded')
    return encoded


def _remember_done_item(event, done_items):
    index, item = event.get('output_index'), event.get('item')
    if (type(index) is not int or not 0 <= index < 32 or index in done_items
            or not isinstance(item, dict) or item.get('status', 'completed') != 'completed'):
        _invalid_response('invalid_schema', protocol_stage='stream_item')
    identifier = item.get('id')
    if 'id' in item and (not isinstance(identifier, str) or not identifier or len(identifier) > 200):
        _invalid_response('invalid_schema', protocol_stage='stream_item')
    if identifier is not None and any(row.get('id') == identifier for row in done_items.values()):
        _invalid_response('invalid_schema', protocol_stage='stream_item')
    done_items[index] = item
    _bounded_tool_json(list(done_items.values()), MAX_TOOL_HISTORY_BYTES)


def _completed_output(response, done_items, observed_items, function_indexes, unindexed_output):
    if (not isinstance(response, dict) or response.get('status', 'completed') != 'completed'
            or response.get('error') is not None or response.get('incomplete_details') is not None):
        _invalid_response('invalid_schema', protocol_stage='response_completion')
    items = response.get('output', [])
    if not isinstance(items, list) or len(items) > 32 or not all(isinstance(item, dict) for item in items):
        _invalid_response('invalid_schema', protocol_stage='response_output_shape')
    if items:
        # A repeated final snapshot must agree with completed SSE items. Never
        # execute both copies, or silently prefer a conflicting set of calls.
        if any(index >= len(items) or item != items[index] for index, item in done_items.items()):
            _invalid_response('invalid_schema', protocol_stage='response_output_conflict')
    elif done_items:
        # output_item.done is the complete item (including opaque reasoning).
        # A compact response.completed need not repeat it. No partial/add/delta
        # event is executable, and every observed output slot must be closed.
        if (unindexed_output or set(done_items) != set(range(len(done_items)))
                or not set(observed_items).issubset(done_items)
                or any(index not in done_items or done_items[index].get('type') != 'function_call'
                       for index in function_indexes)):
            _invalid_response('invalid_schema', protocol_stage='response_output_missing')
        items = [done_items[index] for index in range(len(done_items))]
    for index, identity in observed_items.items():
        if (index >= len(items) or any(items[index].get(key) != value for key, value in identity.items())):
            _invalid_response('invalid_schema', protocol_stage='response_output_conflict')
    if any(index >= len(items) or items[index].get('type') != 'function_call' for index in function_indexes):
        _invalid_response('invalid_schema', protocol_stage='response_output_missing')
    return items


class OpenAIProvider:
    available = True

    def __init__(self, user, connection_id, transport=None):
        self.user, self.connection_id = user, connection_id
        self.transport = transport or HTTPTransport()

    def __repr__(self):
        return 'OpenAIProvider()'

    def _call(self, method, url, cancellation, *, data=None, stream=False, deadline=None):
        _enabled()
        _outside_transaction()
        cancellation.raise_if_cancelled()
        try:
            token = service.get_authorized_access_token(self.user, self.connection_id)
            # Preserve injected transports' signature; the native transport also
            # applies the shared turn deadline to its socket and stream closer.
            extra = {'deadline': deadline} if deadline is not None and isinstance(self.transport, HTTPTransport) else {}
            result = self.transport(method, url, access_token=token.value, data=data,
                                    stream=stream, cancellation=cancellation, **extra)
            try:
                _status(result)
            except ProviderError:
                source = getattr(result, 'stream', None)
                if callable(getattr(source, 'close', None)):
                    try:
                        source.close()
                    except Exception:
                        pass
                raise
            return result
        except service.ConnectionError as exc:
            code = ('unavailable' if exc.code == 'disabled' else 'unauthorized' if exc.code in {
                'not_found', 'forbidden', 'reconnect_required', 'identity_mismatch', 'credentials_invalid',
                'host_mismatch', 'invalid_grant'} else 'provider_error')
            raise ProviderError(code) from None
        except ProviderError:
            raise
        except Exception:
            cancellation.raise_if_cancelled()
            raise ProviderError('transport_error') from None

    def list_models(self, cancellation=None):
        cancellation = cancellation or CancellationToken()
        response = self._call('GET', MODELS_ENDPOINT, cancellation)
        models = response.body.get('models') if isinstance(response.body, dict) else None
        if not isinstance(models, list) or len(models) > 200:
            _invalid_response('invalid_schema')
        result, seen = [], set()
        for model in models:
            if not isinstance(model, dict):
                _invalid_response('invalid_schema')
            if model.get('visibility') != 'list':
                continue
            slug, name = model.get('slug'), model.get('display_name')
            if (not valid_model(slug) or not isinstance(name, str) or not name or len(name) > 200
                    or any(ord(char) < 32 for char in name) or slug in seen):
                _invalid_response('invalid_schema')
            seen.add(slug)
            levels = model.get('supported_reasoning_levels', [])
            # Catalogue descriptions and other account metadata are not needed
            # by the client; retain only known, explicitly advertised levels.
            efforts = reasoning_efforts([level.get('effort') for level in levels if isinstance(level, dict)]
                                        if isinstance(levels, list) and len(levels) <= 32 else [])
            item = {'slug': slug, 'display_name': name, 'reasoning_efforts': efforts}
            default = model.get('default_reasoning_level')
            if isinstance(default, str) and default in efforts:
                item['default_reasoning_effort'] = default
            result.append(item)
        return result

    def stream(self, generation, cancellation):
        if not valid_model(generation.model):
            raise ProviderError('invalid_model')
        body = {
            'model': generation.model, 'instructions': generation.instructions,
            'input': [{'role': 'user', 'content': 'Authorized local context (untrusted data):\n' + generation.context_json}]
                     + [{'role': turn.role, 'content': turn.content} for turn in generation.history],
            'store': False, 'stream': True,
        }
        # Blank means the provider's own default, never an inferred override.
        if generation.reasoning_effort:
            body['reasoning'] = {'effort': generation.reasoning_effort}
        if not generation.tools:
            yield from self._stream_round(body, cancellation)
            yield ProviderEvent('done')
            return
        # Only application-supplied functions are exposed, grouped for the
        # ChatGPT subscription route. There are no hosted tools or paid fallback.
        body['tools'] = [{'type': 'namespace', 'name': 'tuxedo',
                          'description': 'Consult owned Tuxedo finances, calculate simulations and prepare changes for user review.',
                          'tools': list(generation.tools)}]
        body['include'] = ['reasoning.encrypted_content']
        deadline, seen_calls = time.monotonic() + TOTAL_TIMEOUT, set()
        total_text = 0
        for round_index in range(MAX_TOOL_ROUNDS):
            cancellation.raise_if_cancelled()
            if time.monotonic() >= deadline:
                raise ProviderError('timeout')
            response_output = []
            round_stream = self._stream_round(body, cancellation, deadline=deadline, output=response_output)
            try:
                for event in round_stream:
                    total_text += len(event.text)
                    if total_text > MAX_OUTPUT_CHARS:
                        raise ProviderError('limit_exceeded')
                    yield event
            finally:
                round_stream.close()
            calls = self._tool_calls(response_output, generation, seen_calls)
            if not calls:
                yield ProviderEvent('done')
                return
            if round_index == MAX_TOOL_ROUNDS - 1 or len(seen_calls) + len(calls) > MAX_TOOL_CALLS:
                raise ProviderError('limit_exceeded')
            results = []
            for call_id, name, arguments in calls:
                cancellation.raise_if_cancelled()
                if time.monotonic() >= deadline:
                    raise ProviderError('timeout')
                _outside_transaction()
                # The owning service rechecks the session, run and record scope.
                # This callback prepares proposals; generation never saves money.
                try:
                    result = generation.tool_runner(name, arguments)
                except ProviderError:
                    raise
                except Exception:
                    raise ProviderError('provider_error') from None
                cancellation.raise_if_cancelled()
                if time.monotonic() >= deadline:
                    raise ProviderError('timeout')
                _outside_transaction()
                if not isinstance(result, dict):
                    _invalid_response('invalid_schema', protocol_stage='tool_result')
                encoded = _bounded_tool_json(result, MAX_TOOL_BYTES)
                seen_calls.add(call_id)
                results.append({'type': 'function_call_output', 'call_id': call_id, 'output': encoded})
            # Stateless continuation requires every returned reasoning/call item,
            # followed by its results. Never use previous_response_id here.
            next_input = [*body['input'], *response_output, *results]
            _bounded_tool_json(next_input, MAX_TOOL_HISTORY_BYTES)
            body = {**body, 'input': next_input}

    @staticmethod
    def _tool_calls(output, generation, seen_calls):
        allowed = {tool['name'] for tool in generation.tools}
        calls, current = [], set()
        for item in output:
            kind = item.get('type')
            if kind == 'function_call':
                call_id, name, arguments = item.get('call_id'), item.get('name'), item.get('arguments')
                # Responses declares namespace optional, including output calls.
                # With one namespace and unique advertised names, an omitted
                # namespace is unambiguous; an explicit foreign/null one is not.
                if 'namespace' in item and item['namespace'] != 'tuxedo':
                    _invalid_response('invalid_schema', protocol_stage='tool_namespace')
                if not isinstance(name, str) or name not in allowed:
                    _invalid_response('invalid_schema', protocol_stage='tool_name')
                if (not isinstance(call_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', call_id)
                        or call_id in seen_calls or call_id in current):
                    _invalid_response('invalid_schema', protocol_stage='tool_call_id')
                if item.get('status', 'completed') != 'completed':
                    _invalid_response('invalid_schema', protocol_stage='tool_status')
                if not isinstance(arguments, str):
                    _invalid_response('invalid_schema', protocol_stage='tool_arguments')
                if len(arguments.encode('utf-8')) > MAX_TOOL_BYTES:
                    raise ProviderError('limit_exceeded')
                try:
                    parsed = json.loads(arguments, object_pairs_hook=_unique_pairs,
                                        parse_constant=_reject_constant)
                except (ValueError, RecursionError):
                    _invalid_response('invalid_json', protocol_stage='tool_arguments')
                if not isinstance(parsed, dict):
                    _invalid_response('invalid_schema', protocol_stage='tool_arguments')
                _bounded_tool_json(parsed, MAX_TOOL_BYTES)
                current.add(call_id)
                calls.append((call_id, name, parsed))
            elif kind == 'reasoning':
                if not isinstance(item.get('summary', []), list):
                    _invalid_response('invalid_schema', protocol_stage='tool_output')
            elif kind == 'message':
                if item.get('role') != 'assistant' or not isinstance(item.get('content'), list):
                    _invalid_response('invalid_schema', protocol_stage='tool_output')
            else:
                _invalid_response('invalid_schema', protocol_stage='tool_output')
        return calls

    def _stream_round(self, body, cancellation, *, deadline=None, output=None):
        response = self._call('POST', RESPONSES_ENDPOINT, cancellation, data=body, stream=True, deadline=deadline)
        source = response.stream
        if source is None or not callable(getattr(source, 'readline', None)):
            _invalid_response('invalid_schema')
        unregister = cancellation.register_close(source.close)
        deadline = (getattr(source, 'deadline', time.monotonic() + TOTAL_TIMEOUT) if deadline is None
                    else min(deadline, getattr(source, 'deadline', deadline)))
        total = 0
        saw_function = False
        done_items, observed_items, function_indexes = {}, {}, set()
        unindexed_output = False
        try:
            event_data, size = [], 0
            while True:
                cancellation.raise_if_cancelled()
                if time.monotonic() >= deadline:
                    raise ProviderError('timeout')
                line = source.readline(MAX_EVENT_BYTES + 1)
                cancellation.raise_if_cancelled()
                if time.monotonic() >= deadline:
                    raise ProviderError('timeout')
                if not isinstance(line, bytes):
                    _invalid_response('invalid_sse')
                if not line:
                    raise ProviderError('interrupted')
                size += len(line)
                if size > MAX_EVENT_BYTES:
                    raise ProviderError('limit_exceeded')
                line = line.rstrip(b'\r\n')
                if line:
                    if line.startswith(b'data:'):
                        event_data.append(line[5:].lstrip(b' '))
                    continue
                if not event_data:
                    size = 0
                    continue
                payload = b'\n'.join(event_data)
                event_data, size = [], 0
                if payload == b'[DONE]':
                    raise ProviderError('interrupted')
                try:
                    event = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_pairs,
                                       parse_constant=_reject_constant)
                except (ValueError, UnicodeError, RecursionError):
                    _invalid_response('invalid_json')
                if not isinstance(event, dict):
                    _invalid_response('invalid_schema')
                kind = event.get('type')
                if (isinstance(kind, str) and kind.startswith('response.function_call_arguments.')
                        or kind in {'response.output_item.added', 'response.output_item.done'}
                        and isinstance(event.get('item'), dict) and event['item'].get('type') == 'function_call'):
                    saw_function = True
                    index = event.get('output_index')
                    if type(index) is int and 0 <= index < 32:
                        function_indexes.add(index)
                    else:
                        unindexed_output = True
                if output is not None and kind == 'response.output_item.added':
                    index, item = event.get('output_index'), event.get('item')
                    if type(index) is int and 0 <= index < 32 and isinstance(item, dict):
                        identity = {key: item[key] for key in ('type', 'id') if key in item}
                        if index in observed_items and observed_items[index] != identity:
                            _invalid_response('invalid_schema', protocol_stage='stream_item')
                        observed_items[index] = identity
                    else:
                        unindexed_output = True
                if output is not None and kind == 'response.output_item.done':
                    _remember_done_item(event, done_items)
                if kind == 'response.output_text.delta':
                    delta = event.get('delta')
                    if not isinstance(delta, str):
                        _invalid_response('invalid_schema')
                    total += len(delta)
                    if total > MAX_OUTPUT_CHARS:
                        raise ProviderError('limit_exceeded')
                    for offset in range(0, len(delta), 4000):
                        yield ProviderEvent('text', text=delta[offset:offset + 4000])
                elif kind == 'response.completed':
                    completed = event.get('response', {})
                    items = _completed_output(completed, done_items, observed_items,
                                              function_indexes, unindexed_output)
                    if saw_function and not any(item.get('type') == 'function_call' for item in items):
                        _invalid_response('invalid_schema', protocol_stage='response_output_missing')
                    if output is None:
                        if any(item.get('type') == 'function_call' for item in items):
                            _invalid_response('invalid_schema', protocol_stage='response_output')
                    else:
                        _bounded_tool_json(items, MAX_TOOL_HISTORY_BYTES)
                        output.extend(items)
                    return
                elif kind == 'response.incomplete':
                    raise ProviderError('incomplete')
                elif kind in {'response.failed', 'error'}:
                    raise ProviderError(_error_code(event))
        except ProviderError:
            raise
        except (TimeoutError, socket.timeout):
            cancellation.raise_if_cancelled()
            raise ProviderError('timeout') from None
        except Exception:
            cancellation.raise_if_cancelled()
            if time.monotonic() >= deadline:
                raise ProviderError('timeout') from None
            raise ProviderError('transport_error') from None
        finally:
            unregister()
            try:
                source.close()
            except Exception:
                pass
