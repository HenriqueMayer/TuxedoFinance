# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic signed identities and fake HTTP only; never access a real account."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
import hashlib
from unittest.mock import patch
from urllib import error
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
from django.http import QueryDict
from django.test import SimpleTestCase, override_settings
import jwt

from assistant.connections import oauth


CALLBACK = 'http://127.0.0.1:8765/assistant/connections/callback/'
CLIENT = 'oaiapp_synthetic_client'
HOST = 'urn:uuid:synthetic-host'
REVOKE = oauth.ISSUER + '/api/accounts/oauth/revoke'


class FakeTransport:
    def __init__(self, tokens=None, jwks=None):
        self.calls = []
        self.responses = {
            oauth.TOKEN_ENDPOINT: oauth.OAuthResponse(200, tokens or {}),
            oauth.DISCOVERY_ENDPOINT: oauth.OAuthResponse(200, {
                'issuer': oauth.ISSUER, 'authorization_endpoint': oauth.AUTHORIZATION_ENDPOINT,
                'token_endpoint': oauth.TOKEN_ENDPOINT, 'jwks_uri': oauth.JWKS_ENDPOINT,
                'revocation_endpoint': REVOKE,
            }),
            oauth.JWKS_ENDPOINT: oauth.OAuthResponse(200, jwks or {}),
            REVOKE: oauth.OAuthResponse(200),
        }

    def __call__(self, method, url, *, data=None):
        self.calls.append((method, url, deepcopy(data)))
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return result


class ConnectionOAuthTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key(), as_dict=True)
        cls.public_jwk.update(kid='synthetic-key', alg='RS256', use='sig')

    def setUp(self):
        self.attempt = oauth.new_attempt(CALLBACK, HOST)
        self.callback = {'state': self.attempt['state'], 'code': 'synthetic-code', 'client_id': CLIENT}

    def identity(self, **changes):
        now = int(datetime.now(timezone.utc).timestamp())
        claims = {'iss': oauth.ISSUER, 'sub': 'synthetic-subject', 'aud': CLIENT,
                  'iat': now, 'exp': now + 3600, 'nonce': self.attempt['nonce'],
                  'email': 'synthetic@example.test'}
        claims.update(changes)
        return claims

    def tokens(self, claims=None, key=None, headers=None, **changes):
        tokens = {
            'id_token': jwt.encode(claims or self.identity(), key or self.key,
                                   algorithm='RS256', headers=headers or {'kid': 'synthetic-key'}),
            'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
            'token_type': 'Bearer', 'expires_in': 3600, 'scope': ' '.join(oauth.REQUESTED_SCOPES),
        }
        tokens.update(changes)
        return tokens

    def transport(self, tokens=None):
        return FakeTransport(tokens=tokens or self.tokens(), jwks={'keys': [deepcopy(self.public_jwk)]})

    def exchange(self, tokens=None, transport=None):
        return oauth.exchange_code(self.attempt, self.callback, transport=transport or self.transport(tokens))

    def assert_code(self, code, action):
        with self.assertRaises(oauth.OAuthError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        self.assertNotIn('synthetic-', repr(caught.exception))

    def test_new_attempt_has_fresh_protocol_values_and_fixed_loopback_callback(self):
        another = oauth.new_attempt(CALLBACK, HOST)
        for name in ('state', 'nonce', 'code_verifier'):
            self.assertNotEqual(self.attempt[name], another[name])
            self.assertGreaterEqual(len(self.attempt[name]), 43)
        self.assertEqual(self.attempt['client_id'], oauth.DYNAMIC_CLIENT_ID)
        for uri in ('https://127.0.0.1:8765/assistant/connections/callback/',
                    'http://localhost:8765/assistant/connections/callback/',
                    'http://127.0.0.2:8765/assistant/connections/callback/',
                    'http://127.0.0.1:8765/callback/', CALLBACK + '?next=evil', CALLBACK + '#fragment',
                    'http://user:pass@127.0.0.1:8765/assistant/connections/callback/',
                    'http://127.0.0.1:0/assistant/connections/callback/',
                    'http://127.0.0.1:65536/assistant/connections/callback/',
                    'http://127.0.0.1:8765/assistant/connections/callback/%2e%2e/',
                    CALLBACK + '\n'):
            with self.subTest(uri=uri):
                self.assert_code('invalid_redirect', lambda: oauth.new_attempt(uri, HOST))
        self.assertEqual(oauth.new_attempt(CALLBACK.replace(':8765', ':1455'), HOST)['host_id'], HOST)

    def test_authorization_request_is_official_public_client_pkce_and_plan_scopes(self):
        with patch.object(oauth.request, 'build_opener') as opener:
            url = oauth.authorization_url(self.attempt)
        opener.assert_not_called()
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme + '://' + parsed.netloc + parsed.path, oauth.AUTHORIZATION_ENDPOINT)
        params = parse_qs(parsed.query)
        expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(
            self.attempt['code_verifier'].encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(params['code_challenge'], [expected_challenge])
        self.assertEqual(params['code_challenge_method'], ['S256'])
        self.assertEqual(params['redirect_uri'], [CALLBACK])
        self.assertEqual(params['agent_name_hint'], ['Tuxedo Finance'])
        self.assertEqual(params['ext_agent_host_id'], [HOST])
        self.assertEqual(params['nonce'], [self.attempt['nonce']])
        self.assertEqual(params['resource'], [oauth.RESOURCE])
        self.assertEqual(params['scope'][0].split(), list(oauth.REQUESTED_SCOPES))
        self.assertNotIn('client_secret', params)

    def test_returning_attempt_reuses_issued_client_and_associated_hints(self):
        credentials = self.exchange()
        returning = oauth.new_attempt(CALLBACK.replace(':8765', ':54321'), HOST, credentials)
        params = parse_qs(urlsplit(oauth.authorization_url(returning)).query)
        self.assertEqual(params['client_id'], [CLIENT])
        self.assertEqual(params['id_token_hint'], [credentials['id_token']])
        self.assertEqual(params['login_hint'], [credentials['email']])
        self.assertNotIn('agent_name_hint', params)
        self.assertEqual(returning['subject'], credentials['subject'])
        for change in ({'issuer': 'https://evil.test'}, {'client_id': 'dynamic_agent_client'},
                       {'subject': ''}, {'host_id': 'different-host'}):
            with self.subTest(change=change):
                with self.assertRaises(oauth.OAuthError):
                    oauth.new_attempt(CALLBACK, HOST, {**credentials, **change})

    def test_exchange_verifies_synthetic_signature_and_uses_issued_callback_client(self):
        transport = self.transport()
        credentials = self.exchange(transport=transport)
        self.assertEqual(credentials['issuer'], oauth.ISSUER)
        self.assertEqual(credentials['subject'], 'synthetic-subject')
        self.assertEqual(credentials['client_id'], CLIENT)
        self.assertEqual(credentials['host_id'], HOST)
        self.assertEqual(credentials['capability'], 'plan_authorized')
        self.assertEqual(credentials['scopes'], sorted(oauth.REQUESTED_SCOPES))
        self.assertEqual(credentials['identity_nonce'], self.attempt['nonce'])
        self.assertGreater(datetime.fromisoformat(credentials['expires_at']), datetime.now(timezone.utc))
        self.assertEqual(transport.calls[0], ('POST', oauth.TOKEN_ENDPOINT, {
            'grant_type': 'authorization_code', 'client_id': CLIENT, 'code': 'synthetic-code',
            'redirect_uri': CALLBACK, 'code_verifier': self.attempt['code_verifier'], 'resource': oauth.RESOURCE,
        }))
        self.assertEqual([call[1] for call in transport.calls[1:]],
                         [oauth.DISCOVERY_ENDPOINT, oauth.JWKS_ENDPOINT])

    def test_state_is_compared_constant_time_before_errors_or_code_exchange(self):
        transport = self.transport()
        with patch.object(oauth.hmac, 'compare_digest', wraps=oauth.hmac.compare_digest) as compare:
            self.assert_code('invalid_state', lambda: oauth.exchange_code(
                self.attempt, {**self.callback, 'state': 'wrong-state', 'error': 'access_denied'}, transport))
        compare.assert_called_once()
        self.assertEqual(transport.calls, [])
        for state in (None, '', ['array']):
            self.assert_code('invalid_state', lambda: oauth.exchange_code(
                self.attempt, {**self.callback, 'state': state}, transport))
        self.assert_code('access_denied', lambda: oauth.exchange_code(
            self.attempt, {**self.callback, 'error': 'access_denied'}, transport))
        self.assert_code('authorization_error', lambda: oauth.exchange_code(
            self.attempt, {**self.callback, 'error': 'synthetic-secret-provider-message'}, transport))
        self.assertEqual(transport.calls, [])

    def test_callback_requires_issued_initial_client_and_rejects_duplicate_parameters(self):
        transport = self.transport()
        for client in (None, '', 'dynamic_agent_client', '../unexpected', ['array']):
            self.assert_code('invalid_client', lambda: oauth.exchange_code(
                self.attempt, {**self.callback, 'client_id': client}, transport))
        duplicate = QueryDict('', mutable=True)
        duplicate.update(self.callback)
        duplicate.appendlist('state', self.attempt['state'])
        self.assert_code('invalid_callback', lambda: oauth.exchange_code(self.attempt, duplicate, transport))
        self.assertEqual(transport.calls, [])

    def test_returning_callback_may_omit_client_but_cannot_change_client_or_identity(self):
        credentials = self.exchange()
        self.attempt = oauth.new_attempt(CALLBACK, HOST, credentials)
        self.callback = {'state': self.attempt['state'], 'code': 'returning-code'}
        self.assertEqual(self.exchange()['client_id'], CLIENT)
        self.assert_code('client_mismatch', lambda: oauth.exchange_code(
            self.attempt, {**self.callback, 'client_id': 'oaiapp_other'}, self.transport()))
        self.assert_code('identity_mismatch', lambda: self.exchange(self.tokens(
            self.identity(sub='other-subject', email=credentials['email']))))

    def test_invalid_identity_signature_issuer_audience_expiry_subject_iat_and_nonce_fail(self):
        now = int(datetime.now(timezone.utc).timestamp())
        cases = [({'iss': 'https://evil.test'}, 'invalid_id_token'),
                 ({'aud': 'oaiapp_other'}, 'invalid_id_token'),
                 ({'exp': now - 30}, 'invalid_id_token'),
                 ({'iat': now + 3600}, 'invalid_id_token'),
                 ({'sub': ''}, 'invalid_id_token'), ({'sub': 42}, 'invalid_id_token'),
                 ({'nonce': 'wrong-nonce'}, 'invalid_nonce'),
                 ({'nonce': None}, 'invalid_nonce'),
                 ({'aud': [CLIENT, 'other']}, 'invalid_id_token'),
                 ({'azp': 'other'}, 'invalid_id_token'), ({'email': ['bad']}, 'invalid_id_token')]
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.assert_code(code, lambda: self.exchange(self.tokens(self.identity(**changes))))
        for missing in ('iss', 'aud', 'exp', 'iat', 'sub'):
            claims = self.identity()
            del claims[missing]
            self.assert_code('invalid_id_token', lambda: self.exchange(self.tokens(claims)))
        self.assert_code('invalid_id_token', lambda: self.exchange(self.tokens(key=self.wrong_key)))
        self.assert_code('invalid_id_token', lambda: self.exchange(self.tokens(id_token='malformed')))
        claims = self.identity(aud=[CLIENT, 'other'], azp=CLIENT)
        self.assertEqual(self.exchange(self.tokens(claims))['subject'], claims['sub'])

    def test_unknown_ambiguous_kid_and_symmetric_or_unsigned_jwt_are_rejected(self):
        self.assert_code('invalid_id_token', lambda: self.exchange(
            self.tokens(headers={'kid': 'unknown'})))
        for changes in ({'use': 'enc'}, {'kty': 'oct'}, {'alg': 'HS256'}, {'key_ops': ['sign']},
                        {'key_ops': 'verify'}):
            transport = self.transport()
            transport.responses[oauth.JWKS_ENDPOINT] = oauth.OAuthResponse(200, {
                'keys': [{**self.public_jwk, **changes}]})
            self.assert_code('invalid_id_token', lambda: self.exchange(transport=transport))
        transport = self.transport()
        transport.responses[oauth.JWKS_ENDPOINT] = oauth.OAuthResponse(200, {
            'keys': [self.public_jwk, self.public_jwk]})
        self.assert_code('invalid_id_token', lambda: self.exchange(transport=transport))
        for algorithm, key in (('HS256', 'synthetic-secret-for-test-only-value'), ('none', None)):
            encoded = jwt.encode(self.identity(), key, algorithm=algorithm, headers={'kid': 'synthetic-key'})
            transport = self.transport(self.tokens(id_token=encoded))
            self.assert_code('invalid_id_token', lambda: self.exchange(transport=transport))
            self.assertEqual(len(transport.calls), 1)

    def test_discovery_cannot_redirect_verification_or_trust_to_another_endpoint(self):
        changes = ({'issuer': 'https://evil.test'}, {'jwks_uri': 'https://evil.test/jwks'},
                   {'jwks_uri': oauth.JWKS_ENDPOINT + '?key=unexpected'},
                   {'authorization_endpoint': 'https://evil.test/authorize'},
                   {'token_endpoint': 'https://evil.test/token'})
        for change in changes:
            transport = self.transport()
            document = transport.responses[oauth.DISCOVERY_ENDPOINT].body
            transport.responses[oauth.DISCOVERY_ENDPOINT] = oauth.OAuthResponse(200, {**document, **change})
            with self.subTest(change=change):
                self.assert_code('invalid_discovery', lambda: self.exchange(transport=transport))
                self.assertEqual(len(transport.calls), 2)

    def test_identity_only_and_missing_scopes_never_gain_plan_permission(self):
        identity_only = self.tokens(scope='openid profile email')
        for name in ('access_token', 'refresh_token', 'token_type', 'expires_in'):
            identity_only.pop(name)
        credentials = self.exchange(identity_only)
        self.assertEqual(credentials['capability'], 'identity_only')
        self.assertEqual(credentials['access_token'], '')
        self.assertEqual(credentials['refresh_token'], '')
        self.assertEqual(credentials['scopes'], ['email', 'openid', 'profile'])
        for scope in ('openid email', 'chatgpt.tokens.use.direct', 'resource.invoke', ''):
            self.assertEqual(self.exchange(self.tokens(scope=scope))['capability'], 'identity_only')
        tokens = self.tokens()
        del tokens['scope']
        self.assertEqual(self.exchange(tokens)['scopes'], [])
        self.assertEqual(self.exchange(tokens)['capability'], 'identity_only')
        # A callback's scope is untrusted presentation data, not the token grant.
        self.callback['scope'] = ' '.join(oauth.REQUESTED_SCOPES)
        self.assertEqual(self.exchange(identity_only)['capability'], 'identity_only')

    def test_invalid_token_values_and_scope_shapes_fail_without_raw_provider_data(self):
        for scope in (['openid'], {'openid': True}, 'openid\nemail', 'openid unknown', 'x' * 2049):
            self.assert_code('invalid_scopes', lambda: self.exchange(self.tokens(scope=scope)))
        for change in ({'expires_in': -1}, {'expires_in': True}, {'expires_in': '3600'},
                       {'access_token': ['secret']}, {'token_type': 'mac'}, {'refresh_token': ['secret']}):
            with self.subTest(change=change):
                self.assert_code('invalid_response', lambda: self.exchange(self.tokens(**change)))
        for response in (oauth.OAuthResponse(400, {'error': 'invalid_grant', 'error_description': 'synthetic-secret'}),
                         oauth.OAuthResponse(500, {'error': 'synthetic-secret'})):
            transport = self.transport()
            transport.responses[oauth.TOKEN_ENDPOINT] = response
            self.assert_code('invalid_grant' if response.status == 400 else 'token_error',
                             lambda: self.exchange(transport=transport))
        transport = self.transport()
        transport.responses[oauth.TOKEN_ENDPOINT] = TimeoutError('synthetic-secret')
        self.assert_code('network_error', lambda: self.exchange(transport=transport))

    def test_refresh_rotates_credentials_together_and_retains_grant_when_scope_omitted(self):
        credentials = self.exchange()
        snapshot = deepcopy(credentials)
        transport = self.transport({'access_token': 'synthetic-new-access', 'refresh_token': 'synthetic-new-refresh',
                                    'token_type': 'Bearer', 'expires_in': 1800})
        replacement = oauth.refresh_credentials(credentials, transport)
        self.assertEqual(credentials, snapshot)
        self.assertEqual(replacement['refresh_token'], 'synthetic-new-refresh')
        self.assertEqual(replacement['id_token'], credentials['id_token'])
        self.assertEqual(replacement['subject'], credentials['subject'])
        self.assertEqual(replacement['scopes'], credentials['scopes'])
        self.assertEqual(transport.calls, [('POST', oauth.TOKEN_ENDPOINT, {
            'grant_type': 'refresh_token', 'client_id': CLIENT,
            'refresh_token': 'synthetic-refresh', 'resource': oauth.RESOURCE,
        })])
        self.assertNotIn('scope', transport.calls[0][2])

    def test_refresh_verifies_any_replacement_id_token_and_cannot_switch_account(self):
        credentials = self.exchange()
        claims = self.identity()
        del claims['nonce']
        transport = self.transport(self.tokens(claims))
        self.assertEqual(oauth.refresh_credentials(credentials, transport)['subject'], credentials['subject'])
        for change, code in (({'sub': 'other-subject'}, 'identity_mismatch'),
                             ({'nonce': 'different-nonce'}, 'invalid_nonce'),
                             ({'iss': 'https://evil.test'}, 'invalid_id_token')):
            transport = self.transport(self.tokens(self.identity(**change)))
            self.assert_code(code, lambda: oauth.refresh_credentials(credentials, transport))
        self.assert_code('invalid_id_token', lambda: oauth.refresh_credentials(
            credentials, self.transport(self.tokens(id_token='malformed'))))

    def test_refresh_errors_do_not_replace_existing_credentials_and_grants_can_be_reduced(self):
        credentials = self.exchange()
        snapshot = deepcopy(credentials)
        for status, error_code, expected in ((400, 'invalid_grant', 'invalid_grant'),
                                             (503, 'raw-synthetic-secret', 'token_error')):
            transport = self.transport()
            transport.responses[oauth.TOKEN_ENDPOINT] = oauth.OAuthResponse(status, {'error': error_code})
            self.assert_code(expected, lambda: oauth.refresh_credentials(credentials, transport))
            self.assertEqual(credentials, snapshot)
        transport = self.transport(self.tokens(scope='openid email'))
        replacement = oauth.refresh_credentials(credentials, transport)
        self.assertEqual(replacement['capability'], 'identity_only')
        self.assertEqual(replacement['scopes'], ['email', 'openid'])
        self.assert_code('reauth_required', lambda: oauth.refresh_credentials(
            {**credentials, 'refresh_token': ''}, self.transport()))

    def test_revocation_uses_discovery_and_never_claims_confirmation_on_failure(self):
        credentials = self.exchange()
        transport = self.transport()
        self.assertTrue(oauth.revoke_credentials(credentials, transport))
        self.assertEqual(transport.calls[-1], ('POST', REVOKE, {
            'token': credentials['refresh_token'], 'token_type_hint': 'refresh_token', 'client_id': CLIENT,
        }))
        for status in (204, 400, 500):
            transport.responses[REVOKE] = oauth.OAuthResponse(status)
            self.assertFalse(oauth.revoke_credentials(credentials, transport))
        transport.responses[REVOKE] = OSError('synthetic-secret')
        self.assert_code('network_error', lambda: oauth.revoke_credentials(credentials, transport))

    def test_revocation_rejects_untrusted_or_unrelated_discovered_endpoints(self):
        credentials = self.exchange()
        for endpoint in ('http://auth.openai.com/oauth/revoke', 'https://evil.test/oauth/revoke',
                         'https://auth.openai.com:443/oauth/revoke', 'https://user@auth.openai.com/oauth/revoke',
                         REVOKE + '?token=secret', REVOKE + '#fragment', oauth.AUTHORIZATION_ENDPOINT):
            transport = self.transport()
            document = transport.responses[oauth.DISCOVERY_ENDPOINT].body
            transport.responses[oauth.DISCOVERY_ENDPOINT] = oauth.OAuthResponse(200, {
                **document, 'revocation_endpoint': endpoint})
            with self.subTest(endpoint=endpoint):
                self.assert_code('invalid_discovery', lambda: oauth.revoke_credentials(credentials, transport))
                self.assertEqual(len(transport.calls), 1)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=False)
    def test_real_transport_fails_closed_before_any_network_when_gate_is_disabled(self):
        credentials = self.exchange()
        with patch.object(oauth.request, 'build_opener') as opener:
            self.assert_code('auth_disabled', lambda: oauth.exchange_code(self.attempt, self.callback))
            self.assert_code('auth_disabled', lambda: oauth.refresh_credentials(credentials))
            self.assert_code('auth_disabled', lambda: oauth.revoke_credentials(credentials))
        opener.assert_not_called()


class FakeHTTPResponse:
    def __init__(self, status=200, body=b'', content_type='application/json'):
        self.status, self.body = status, body
        self.headers = Message()
        self.headers['Content-Type'] = content_type
        self.read_size = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        self.read_size = size
        return self.body[:size]


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True)
class OAuthHTTPTransportTests(SimpleTestCase):
    def test_transport_form_encoding_timeout_no_proxies_and_no_redirects(self):
        response = FakeHTTPResponse(body=b'{"scope":"openid"}')
        with patch.object(oauth.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            result = oauth.HTTPTransport()('POST', oauth.TOKEN_ENDPOINT, data={'code': 'synthetic code'})
        self.assertEqual(result, oauth.OAuthResponse(200, {'scope': 'openid'}))
        self.assertEqual(response.read_size, oauth.MAX_RESPONSE_BYTES + 1)
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[1], oauth._NoRedirects)
        called_request = build.return_value.open.call_args.args[0]
        self.assertEqual(called_request.data, b'code=synthetic+code')
        self.assertEqual(called_request.headers['Content-type'], 'application/x-www-form-urlencoded')
        self.assertEqual(build.return_value.open.call_args.kwargs, {'timeout': oauth.HTTP_TIMEOUT})
        self.assertIsNone(oauth._NoRedirects().redirect_request(None, None, 302, '', {}, 'https://evil.test'))

    def test_transport_rejects_non_json_large_bodies_and_unsafe_endpoints(self):
        cases = (FakeHTTPResponse(body=b'[]'), FakeHTTPResponse(body=b'invalid'),
                 FakeHTTPResponse(body=b'{}', content_type='text/html'),
                 FakeHTTPResponse(body=b'x' * (oauth.MAX_RESPONSE_BYTES + 1)))
        for response in cases:
            with self.subTest(response=response), patch.object(oauth.request, 'build_opener') as build:
                build.return_value.open.return_value = response
                with self.assertRaises(oauth.OAuthError) as caught:
                    oauth.HTTPTransport()('GET', oauth.DISCOVERY_ENDPOINT)
                self.assertEqual(caught.exception.code, 'invalid_response')
        for endpoint in ('https://api.openai.com/v1/responses', 'http://auth.openai.com/oauth/revoke',
                         'https://evil.test/token', oauth.TOKEN_ENDPOINT + '?key=secret'):
            with patch.object(oauth.request, 'build_opener') as build:
                with self.assertRaises(oauth.OAuthError):
                    oauth.HTTPTransport()('POST', endpoint, data={'token': 'synthetic-secret'})
                build.assert_not_called()

    def test_transport_returns_empty_revocation_and_sanitizes_network_failures(self):
        with patch.object(oauth.request, 'build_opener') as build:
            build.return_value.open.return_value = FakeHTTPResponse()
            self.assertEqual(oauth.HTTPTransport()('POST', REVOKE, data={}), oauth.OAuthResponse(200))
            build.return_value.open.side_effect = error.URLError('synthetic-secret')
            with self.assertRaises(oauth.OAuthError) as caught:
                oauth.HTTPTransport()('GET', oauth.DISCOVERY_ENDPOINT)
        self.assertEqual(str(caught.exception), 'network_error')
        self.assertNotIn('synthetic-secret', str(caught.exception))

    def test_oauth_response_repr_does_not_contain_body_secrets(self):
        self.assertNotIn('synthetic-secret', repr(oauth.OAuthResponse(200, {'access_token': 'synthetic-secret'})))
        self.assertEqual(str(oauth.OAuthError('synthetic-secret-provider-code')), 'protocol_error')
