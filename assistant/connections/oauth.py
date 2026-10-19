# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Public-client Sign in with ChatGPT protocol, without model API access.

Tests inject a callable ``transport(method, url, *, data=None)`` returning an
``OAuthResponse``. ``data`` is a form dictionary; the response body is an already
decoded JSON dictionary or ``None`` for an empty response. Only HTTPTransport
opens sockets, and its separate setting is disabled by default. Transaction
ownership, expiration, one-time consumption and serialized refresh belong to
the connection service, not this stateless protocol module.
"""
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import ssl
from urllib import error, request
from urllib.parse import urlencode, urlsplit

from django.conf import settings
import jwt


ISSUER = 'https://auth.openai.com'
AUTHORIZATION_ENDPOINT = ISSUER + '/api/accounts/authorize'
TOKEN_ENDPOINT = ISSUER + '/api/accounts/oauth/token'
DISCOVERY_ENDPOINT = ISSUER + '/.well-known/openid-configuration'
JWKS_ENDPOINT = ISSUER + '/.well-known/jwks.json'
RESOURCE = 'https://api.openai.com/v1'
CALLBACK_PATH = '/assistant/connections/callback/'
DYNAMIC_CLIENT_ID = 'dynamic_agent_client'
REQUESTED_SCOPES = ('openid', 'profile', 'email', 'offline_access',
                    'resource.invoke', 'chatgpt.tokens.use.direct')
ALLOWED_ALGORITHMS = ('RS256',)
MAX_RESPONSE_BYTES = 256 * 1024
HTTP_TIMEOUT = 10
_SAFE_ERRORS = frozenset({'access_denied', 'invalid_grant', 'invalid_client',
                          'invalid_scope', 'temporarily_unavailable', 'server_error',
                          'login_required', 'interaction_required', 'consent_required'})
_ERROR_CODES = _SAFE_ERRORS | frozenset({
    'auth_disabled', 'invalid_discovery', 'invalid_endpoint', 'invalid_response',
    'network_error', 'invalid_host', 'invalid_redirect', 'invalid_registration',
    'invalid_attempt', 'discovery_error', 'invalid_id_token', 'jwks_error',
    'invalid_nonce', 'invalid_scopes', 'invalid_callback', 'invalid_state',
    'authorization_error', 'client_mismatch', 'token_error', 'identity_mismatch',
    'reauth_required', 'protocol_error',
})


class OAuthError(Exception):
    """A stable machine code; never include provider bodies or token values."""

    def __init__(self, code):
        self.code = code if isinstance(code, str) and code in _ERROR_CODES else 'protocol_error'
        super().__init__(self.code)


@dataclass(frozen=True)
class OAuthResponse:
    status: int
    body: dict | None = field(default=None, repr=False)


class _NoRedirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _trusted_endpoint(url, *, revocation=False):
    if not isinstance(url, str) or len(url) > 512:
        raise OAuthError('invalid_discovery')
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise OAuthError('invalid_discovery') from None
    if (parsed.scheme != 'https' or parsed.netloc != 'auth.openai.com'
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise OAuthError('invalid_discovery')
    if revocation:
        # Discovery is authoritative for this endpoint, but cannot send a token
        # to an unrelated origin or to a general-purpose application URL.
        if parsed.path not in {'/api/accounts/oauth/revoke', '/oauth/revoke',
                                '/api/accounts/oauth/revocation', '/oauth/revocation'}:
            raise OAuthError('invalid_discovery')
    elif url not in {DISCOVERY_ENDPOINT, JWKS_ENDPOINT, TOKEN_ENDPOINT}:
        raise OAuthError('invalid_discovery')
    return url


class HTTPTransport:
    """Bounded HTTPS only; no redirect, proxy, model endpoint or implicit enable."""

    def __call__(self, method, url, *, data=None):
        if getattr(settings, 'ASSISTANT_OPENAI_AUTH_ENABLED', False) is not True:
            raise OAuthError('auth_disabled')
        _trusted_endpoint(url, revocation=url not in {
            DISCOVERY_ENDPOINT, JWKS_ENDPOINT, TOKEN_ENDPOINT})
        if (method == 'GET' and url not in {DISCOVERY_ENDPOINT, JWKS_ENDPOINT}
                or method == 'POST' and url in {DISCOVERY_ENDPOINT, JWKS_ENDPOINT}
                or method not in {'GET', 'POST'}):
            raise OAuthError('invalid_endpoint')
        headers = {'Accept': 'application/json'}
        payload = None
        if data is not None:
            payload = urlencode(data).encode('ascii')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        try:
            opener = request.build_opener(request.ProxyHandler({}), _NoRedirects(),
                                          request.HTTPSHandler(context=ssl.create_default_context()))
            http_request = request.Request(url, data=payload, headers=headers, method=method)
            try:
                response = opener.open(http_request, timeout=HTTP_TIMEOUT)
            except error.HTTPError as rejected:
                response = rejected
            with response:
                status = response.status
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise OAuthError('invalid_response')
                if not body:
                    return OAuthResponse(status)
                if response.headers.get_content_type() != 'application/json':
                    raise OAuthError('invalid_response')
                try:
                    decoded = json.loads(body.decode('utf-8'))
                except (ValueError, UnicodeError):
                    raise OAuthError('invalid_response') from None
                if not isinstance(decoded, dict):
                    raise OAuthError('invalid_response')
                return OAuthResponse(status, decoded)
        except OAuthError:
            raise
        except (OSError, ValueError, error.URLError):
            raise OAuthError('network_error') from None


def _text(value, code, *, maximum=16384, allow_empty=False):
    if (not isinstance(value, str) or len(value) > maximum
            or (not value and not allow_empty) or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise OAuthError(code)
    return value


def _client_id(value):
    value = _text(value, 'invalid_client', maximum=255)
    if value == DYNAMIC_CLIENT_ID or not re.fullmatch(r'[A-Za-z0-9._~-]+', value):
        raise OAuthError('invalid_client')
    return value


def _redirect_uri(value):
    value = _text(value, 'invalid_redirect', maximum=255)
    match = re.fullmatch(r'http://127\.0\.0\.1(?::([0-9]{1,5}))?'
                         + re.escape(CALLBACK_PATH), value)
    if not match or (match.group(1) and not 1 <= int(match.group(1)) <= 65535):
        raise OAuthError('invalid_redirect')
    return value


def _same(left, right):
    return (isinstance(left, str) and isinstance(right, str)
            and hmac.compare_digest(left.encode('utf-8'), right.encode('utf-8')))


def new_attempt(redirect_uri, host_id, registration=None):
    """Create fresh protocol values; the service persists them only privately."""
    attempt = {
        'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32),
        'code_verifier': secrets.token_urlsafe(64),
        'redirect_uri': _redirect_uri(redirect_uri),
        'host_id': _text(host_id, 'invalid_host', maximum=255),
        'client_id': DYNAMIC_CLIENT_ID,
    }
    if registration is not None:
        if not isinstance(registration, dict) or registration.get('issuer') != ISSUER:
            raise OAuthError('invalid_registration')
        attempt.update(client_id=_client_id(registration.get('client_id')), issuer=ISSUER,
                       subject=_text(registration.get('subject'), 'invalid_registration', maximum=255))
        if registration.get('host_id') not in {None, host_id}:
            raise OAuthError('invalid_host')
        hint = registration.get('id_token') or registration.get('id_token_hint')
        if hint:
            attempt['id_token_hint'] = _text(hint, 'invalid_registration')
        if registration.get('email'):
            attempt['login_hint'] = _text(registration['email'], 'invalid_registration', maximum=320)
    return attempt


def _validate_attempt(attempt):
    if not isinstance(attempt, dict):
        raise OAuthError('invalid_attempt')
    _redirect_uri(attempt.get('redirect_uri'))
    _text(attempt.get('host_id'), 'invalid_host', maximum=255)
    for key in ('state', 'nonce', 'code_verifier'):
        if not re.fullmatch(r'[A-Za-z0-9_~.\-]{43,128}',
                            _text(attempt.get(key), 'invalid_attempt', maximum=128)):
            raise OAuthError('invalid_attempt')
    if attempt.get('client_id') != DYNAMIC_CLIENT_ID:
        _client_id(attempt.get('client_id'))
        if attempt.get('issuer') != ISSUER:
            raise OAuthError('invalid_registration')
        _text(attempt.get('subject'), 'invalid_registration', maximum=255)


def authorization_url(attempt):
    _validate_attempt(attempt)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(
        attempt['code_verifier'].encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    params = {
        'client_id': attempt['client_id'], 'ext_agent_host_id': attempt['host_id'],
        'response_type': 'code', 'redirect_uri': attempt['redirect_uri'],
        'scope': ' '.join(REQUESTED_SCOPES), 'resource': RESOURCE,
        'state': attempt['state'], 'nonce': attempt['nonce'],
        'code_challenge_method': 'S256', 'code_challenge': challenge,
    }
    if attempt['client_id'] == DYNAMIC_CLIENT_ID:
        params['agent_name_hint'] = 'Tuxedo Finance'
    else:
        for hint in ('id_token_hint', 'login_hint'):
            if attempt.get(hint):
                params[hint] = _text(attempt[hint], 'invalid_registration')
    return AUTHORIZATION_ENDPOINT + '?' + urlencode(params)


def _call(transport, method, url, data=None):
    try:
        result = transport(method, url, data=data)
    except OAuthError:
        raise
    except Exception:
        raise OAuthError('network_error') from None
    if (not isinstance(result, OAuthResponse) or type(result.status) is not int
            or not 100 <= result.status <= 599
            or result.body is not None and not isinstance(result.body, dict)):
        raise OAuthError('invalid_response')
    return result


def _json_success(response, fallback):
    if response.status != 200:
        code = response.body.get('error') if isinstance(response.body, dict) else None
        raise OAuthError(code if isinstance(code, str) and code in _SAFE_ERRORS else fallback)
    if not isinstance(response.body, dict):
        raise OAuthError('invalid_response')
    return response.body


def _discovery(transport):
    document = _json_success(_call(transport, 'GET', DISCOVERY_ENDPOINT), 'discovery_error')
    if (document.get('issuer') != ISSUER
            or document.get('authorization_endpoint') != AUTHORIZATION_ENDPOINT
            or document.get('token_endpoint') != TOKEN_ENDPOINT
            or document.get('jwks_uri') != JWKS_ENDPOINT):
        raise OAuthError('invalid_discovery')
    return document


def _identity(id_token, client_id, transport, *, nonce=None, refresh_nonce=None):
    _text(id_token, 'invalid_id_token')
    try:
        header = jwt.get_unverified_header(id_token)
        if header.get('alg') not in ALLOWED_ALGORITHMS or header.get('crit'):
            raise OAuthError('invalid_id_token')
        kid = _text(header.get('kid'), 'invalid_id_token', maximum=255)
        document = _discovery(transport)
        key_set = _json_success(_call(transport, 'GET', document['jwks_uri']), 'jwks_error')
        keys = key_set.get('keys')
        if not isinstance(keys, list) or not 1 <= len(keys) <= 32:
            raise OAuthError('invalid_id_token')
        matches = [key for key in keys if isinstance(key, dict) and key.get('kid') == kid]
        if len(matches) != 1:
            raise OAuthError('invalid_id_token')
        key = matches[0]
        if (key.get('kty') != 'RSA' or key.get('use', 'sig') != 'sig'
                or key.get('alg', header['alg']) != header['alg']
                or 'key_ops' in key and (not isinstance(key['key_ops'], list)
                                         or 'verify' not in key['key_ops'])):
            raise OAuthError('invalid_id_token')
        verification_key = jwt.PyJWK.from_dict(key, algorithm=header['alg']).key
        if verification_key.key_size < 2048:
            raise OAuthError('invalid_id_token')
        claims = jwt.decode(id_token, verification_key, algorithms=list(ALLOWED_ALGORITHMS),
                            audience=client_id, issuer=ISSUER, leeway=5,
                            options={'require': ['iss', 'aud', 'sub', 'exp', 'iat']})
        _text(claims.get('sub'), 'invalid_id_token', maximum=255)
        # Multi-audience tokens require an explicit authorized party for this client.
        if ('azp' in claims and claims['azp'] != client_id
                or isinstance(claims['aud'], list) and len(claims['aud']) > 1
                and claims.get('azp') != client_id):
            raise OAuthError('invalid_id_token')
        if nonce is not None and not _same(claims.get('nonce'), nonce):
            raise OAuthError('invalid_nonce')
        if nonce is None and 'nonce' in claims and not _same(claims['nonce'], refresh_nonce):
            raise OAuthError('invalid_nonce')
        if claims.get('email') is not None:
            _text(claims['email'], 'invalid_id_token', maximum=320)
        return claims
    except OAuthError:
        raise
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, OverflowError):
        raise OAuthError('invalid_id_token') from None


def _scopes(response, previous=None):
    if 'scope' not in response:
        return list(previous or [])
    value = response['scope']
    if (not isinstance(value, str) or len(value) > 2048
            or not re.fullmatch(r'[A-Za-z0-9._: -]*', value)):
        raise OAuthError('invalid_scopes')
    scopes = value.split()
    if any(scope not in REQUESTED_SCOPES for scope in scopes):
        raise OAuthError('invalid_scopes')
    return sorted(set(scopes))


def _credentials(tokens, identity, client_id, host_id, *, previous=None, nonce=None):
    previous = previous or {}
    access = _text(tokens.get('access_token', ''), 'invalid_response', allow_empty=True)
    if access and str(tokens.get('token_type', '')).lower() != 'bearer':
        raise OAuthError('invalid_response')
    refresh = _text(tokens.get('refresh_token', previous.get('refresh_token', '')),
                    'invalid_response', allow_empty=True)
    scopes = _scopes(tokens, previous.get('scopes'))
    expires_in = tokens.get('expires_in')
    if access:
        if type(expires_in) is not int or not 0 < expires_in <= 366 * 86400:
            raise OAuthError('invalid_response')
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    elif identity is not None:
        expires_at = datetime.fromtimestamp(identity['exp'], timezone.utc)
    else:
        raise OAuthError('invalid_response')
    result = {
        'issuer': ISSUER, 'subject': identity['sub'] if identity else previous['subject'],
        'client_id': client_id, 'host_id': host_id,
        'email': (identity.get('email') or '') if identity else previous.get('email', ''),
        'scopes': scopes, 'access_token': access, 'refresh_token': refresh,
        'id_token': tokens.get('id_token', previous.get('id_token', '')),
        'expires_at': expires_at.isoformat(),
        'identity_nonce': nonce if nonce is not None else previous.get('identity_nonce'),
    }
    # A valid identity alone never grants use of a ChatGPT plan. Inference has
    # its own application gate and is deliberately absent from this module.
    result['capability'] = ('plan_authorized' if access and
                            {'chatgpt.tokens.use.direct', 'resource.invoke'} <= set(scopes)
                            else 'identity_only')
    return result


def _parameter(params, name):
    if hasattr(params, 'getlist') and len(params.getlist(name)) > 1:
        raise OAuthError('invalid_callback')
    return params.get(name)


def exchange_code(attempt, callback_params, transport=None):
    _validate_attempt(attempt)
    if not hasattr(callback_params, 'get'):
        raise OAuthError('invalid_callback')
    state = _parameter(callback_params, 'state')
    if not _same(state, attempt['state']):
        raise OAuthError('invalid_state')
    oauth_error = _parameter(callback_params, 'error')
    if oauth_error is not None:
        raise OAuthError(oauth_error if isinstance(oauth_error, str) and oauth_error in _SAFE_ERRORS
                         else 'authorization_error')
    code = _text(_parameter(callback_params, 'code'), 'invalid_callback', maximum=4096)
    callback_client = _parameter(callback_params, 'client_id')
    if attempt['client_id'] == DYNAMIC_CLIENT_ID:
        client_id = _client_id(callback_client)
    else:
        client_id = attempt['client_id']
        if callback_client is not None and not _same(callback_client, client_id):
            raise OAuthError('client_mismatch')
    tokens = _json_success(_call(transport or HTTPTransport(), 'POST', TOKEN_ENDPOINT, {
        'grant_type': 'authorization_code', 'code': code, 'client_id': client_id,
        'code_verifier': attempt['code_verifier'], 'redirect_uri': attempt['redirect_uri'],
        'resource': RESOURCE,
    }), 'token_error')
    identity = _identity(tokens.get('id_token'), client_id, transport or HTTPTransport(), nonce=attempt['nonce'])
    if attempt.get('issuer') and (identity['iss'] != attempt['issuer']
                                  or identity['sub'] != attempt['subject']):
        raise OAuthError('identity_mismatch')
    return _credentials(tokens, identity, client_id, attempt['host_id'], nonce=attempt['nonce'])


def _registration(credentials):
    if not isinstance(credentials, dict) or credentials.get('issuer') != ISSUER:
        raise OAuthError('invalid_registration')
    _client_id(credentials.get('client_id'))
    _text(credentials.get('subject'), 'invalid_registration', maximum=255)
    _text(credentials.get('host_id'), 'invalid_host', maximum=255)
    _text(credentials.get('refresh_token'), 'reauth_required')


def refresh_credentials(credentials, transport=None):
    _registration(credentials)
    transport = transport or HTTPTransport()
    tokens = _json_success(_call(transport, 'POST', TOKEN_ENDPOINT, {
        'grant_type': 'refresh_token', 'client_id': credentials['client_id'],
        'refresh_token': credentials['refresh_token'], 'resource': RESOURCE,
    }), 'token_error')
    identity = None
    if 'id_token' in tokens:
        identity = _identity(tokens['id_token'], credentials['client_id'], transport,
                             refresh_nonce=credentials.get('identity_nonce'))
        if identity['iss'] != credentials['issuer'] or identity['sub'] != credentials['subject']:
            raise OAuthError('identity_mismatch')
    return _credentials(tokens, identity, credentials['client_id'], credentials['host_id'],
                        previous=credentials)


def revoke_credentials(credentials, transport=None):
    """Return confirmation only; local clearing is always the service's duty."""
    _registration(credentials)
    transport = transport or HTTPTransport()
    discovery = _discovery(transport)
    endpoint = _trusted_endpoint(discovery.get('revocation_endpoint'), revocation=True)
    response = _call(transport, 'POST', endpoint, {
        'token': credentials['refresh_token'], 'token_type_hint': 'refresh_token',
        'client_id': credentials['client_id'],
    })
    return response.status == 200
