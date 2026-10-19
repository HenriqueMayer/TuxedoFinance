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
import socket
import ssl
from threading import Timer
import time
from urllib import error, request

from django.conf import settings

from assistant.connections import service
from assistant.providers.base import (
    CancellationToken, ProviderError, ProviderEvent, ProviderUnavailable, _outside_transaction, valid_model,
)


MODELS_ENDPOINT = 'https://api.openai.com/v1/models'
RESPONSES_ENDPOINT = 'https://api.openai.com/v1/responses'
MAX_EVENT_BYTES = 512 * 1024
# Account catalogues include rich per-model metadata beyond the two UI fields.
# Keep that JSON bound separate from individual SSE events and request bodies.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ERROR_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 16000
READ_TIMEOUT = 15
TOTAL_TIMEOUT = 90
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
_ERROR_PARAMETERS = frozenset({'model', 'input', 'instructions', 'store', 'stream'})
_PROTOCOL_ERRORS = frozenset({'unexpected_content_type', 'invalid_json', 'invalid_schema', 'invalid_sse'})
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
                body_kind=None, response_error=None):
    safe = _safe_error(detail).get('error', {})
    response_error = _safe_error(response_error).get('error', {})
    code = safe.get('code', safe.get('type', 'unknown'))
    if isinstance(detail, str) and detail in _PROTOCOL_ERRORS:
        code = detail
    # No exception info, request IDs, identity, headers, body or arbitrary strings.
    message = 'OpenAI provider failure status=%s code=%s param=%s'
    fields = [status if type(status) is int and 100 <= status <= 599 else 0,
              code, safe.get('param', response_error.get('param', 'unknown'))]
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
    def __call__(self, method, url, *, access_token, data=None, stream=False, cancellation=None):
        _enabled()
        _outside_transaction()
        if (method, url, stream) not in {('GET', MODELS_ENDPOINT, False), ('POST', RESPONSES_ENDPOINT, True)}:
            raise ProviderError()
        cancellation = cancellation or CancellationToken()
        cancellation.raise_if_cancelled()
        if (not isinstance(access_token, str) or not access_token or len(access_token) > 16384
                or any(ord(char) < 33 or ord(char) > 126 for char in access_token)):
            raise ProviderError('unauthorized')
        deadline = time.monotonic() + TOTAL_TIMEOUT
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
                response = opener.open(request.Request(url, data=payload, headers=headers, method=method),
                                       timeout=READ_TIMEOUT)
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


class OpenAIProvider:
    available = True

    def __init__(self, user, connection_id, transport=None):
        self.user, self.connection_id = user, connection_id
        self.transport = transport or HTTPTransport()

    def __repr__(self):
        return 'OpenAIProvider()'

    def _call(self, method, url, cancellation, *, data=None, stream=False):
        _enabled()
        _outside_transaction()
        cancellation.raise_if_cancelled()
        try:
            token = service.get_authorized_access_token(self.user, self.connection_id)
            result = self.transport(method, url, access_token=token.value, data=data,
                                    stream=stream, cancellation=cancellation)
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
            result.append({'slug': slug, 'display_name': name})
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
        response = self._call('POST', RESPONSES_ENDPOINT, cancellation, data=body, stream=True)
        source = response.stream
        if source is None or not callable(getattr(source, 'readline', None)):
            _invalid_response('invalid_schema')
        unregister = cancellation.register_close(source.close)
        deadline = getattr(source, 'deadline', time.monotonic() + TOTAL_TIMEOUT)
        total = 0
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
                    event = json.loads(payload.decode('utf-8'))
                except (ValueError, UnicodeError, RecursionError):
                    _invalid_response('invalid_json')
                if not isinstance(event, dict):
                    _invalid_response('invalid_schema')
                kind = event.get('type')
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
                    yield ProviderEvent('done')
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
