# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic provider protocol and disposable credentials; no real API access."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone

from assistant.connections import oauth, service
from assistant.connections.vault import CredentialVault
from assistant.models import ProviderConnection
from assistant.providers import get_provider
from assistant.providers.base import (
    CancellationToken, ChatTurn, DisconnectedProvider, GenerationRequest, ProviderError, ProviderEvent, stream_response,
)
from assistant.providers import openai
from assistant.tests.support import make_owner


def sse(*events):
    return b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events)


class FakeStream(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.was_closed = False

    def close(self):
        self.was_closed = True
        super().close()


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
class OpenAIProviderTests(SimpleTestCase):
    def setUp(self):
        self.token_patch = patch.object(service, 'get_authorized_access_token',
                                        return_value=service.AuthorizedAccessToken('SYNTHETIC-TOKEN'))
        self.authorize = self.token_patch.start()
        self.addCleanup(self.token_patch.stop)
        self.calls = []
        self.source = FakeStream(sse({'type': 'response.completed'}))
        self.response = openai.TransportResponse(200, stream=self.source)

        def transport(method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            return self.response
        self.provider = openai.OpenAIProvider(object(), 'synthetic-connection', transport=transport)
        self.request = GenerationRequest('{"bounded":"synthetic"}',
                                         history=(ChatTurn('user', 'Synthetic question'),), model='synthetic-model')

    def events(self):
        return list(stream_response(self.provider, self.request, CancellationToken()))

    def test_models_filter_visibility_preserve_server_order_and_do_not_hardcode(self):
        self.response = openai.TransportResponse(200, body={'models': [
            {'slug': 'second-model', 'display_name': 'Second', 'visibility': 'list'},
            {'slug': 'hidden-model', 'display_name': 'Hidden', 'visibility': 'hidden'},
            {'slug': 'first-model', 'display_name': 'First', 'visibility': 'list'},
        ]})
        self.assertEqual(self.provider.list_models(), [
            {'slug': 'second-model', 'display_name': 'Second', 'reasoning_efforts': []},
            {'slug': 'first-model', 'display_name': 'First', 'reasoning_efforts': []},
        ])
        self.assertEqual(self.calls[0][:2], ('GET', openai.MODELS_ENDPOINT))
        self.assertEqual(self.calls[0][2]['access_token'], 'SYNTHETIC-TOKEN')
        self.assertIsNone(self.calls[0][2]['data'])

    def test_catalogue_retains_only_advertised_known_efforts_and_matching_defaults(self):
        self.response = openai.TransportResponse(200, body={'models': [
            {'slug': 'reasoning-model', 'display_name': 'Reasoning', 'visibility': 'list',
             'default_reasoning_level': 'medium',
             'supported_reasoning_levels': [
                 {'effort': 'high', 'description': 'Private description not needed by UI'},
                 {'effort': 'medium'}, {'effort': 'high'}, {'effort': 'unknown-future'},
                 {'effort': ['invalid']}, None]},
            {'slug': 'unknown-model', 'display_name': 'Unknown', 'visibility': 'list',
             'default_reasoning_level': 'high', 'supported_reasoning_levels': {'high': True}},
            {'slug': 'oversized-model', 'display_name': 'Oversized', 'visibility': 'list',
             'supported_reasoning_levels': [{'effort': 'low'}] * 33},
        ]})
        models = self.provider.list_models()
        self.assertEqual(models, [
            {'slug': 'reasoning-model', 'display_name': 'Reasoning', 'reasoning_efforts': ['high', 'medium'],
             'default_reasoning_effort': 'medium'},
            {'slug': 'unknown-model', 'display_name': 'Unknown', 'reasoning_efforts': []},
            {'slug': 'oversized-model', 'display_name': 'Oversized', 'reasoning_efforts': []},
        ])
        self.assertNotIn('Private description', json.dumps(models))

    def test_explicit_reasoning_effort_enters_only_the_supported_request_object(self):
        self.request = GenerationRequest('{}', model='synthetic-model', reasoning_effort='low')
        self.assertEqual(self.events(), [ProviderEvent('done')])
        body = self.calls[0][2]['data']
        self.assertEqual(body['reasoning'], {'effort': 'low'})
        self.assertFalse(body['store'])
        self.assertTrue(body['stream'])
        self.assertNotIn('reasoning_effort', body)

    def test_responses_request_has_only_supported_fields_context_and_explicit_selected_model(self):
        self.assertEqual(self.events(), [ProviderEvent('done')])
        method, url, request = self.calls[0]
        self.assertEqual((method, url), ('POST', openai.RESPONSES_ENDPOINT))
        body = request['data']
        self.assertEqual(set(body), {'model', 'instructions', 'input', 'store', 'stream'})
        self.assertEqual(body['model'], self.request.model)
        self.assertFalse(body['store'])
        self.assertTrue(body['stream'])
        self.assertEqual(body['instructions'], self.request.instructions)
        self.assertIn(self.request.context_json, body['input'][0]['content'])
        self.assertEqual(body['input'][1], {'role': 'user', 'content': 'Synthetic question'})
        self.assertTrue(all(item['role'] in {'user', 'assistant'} for item in body['input']))
        self.assertTrue(self.source.was_closed)
        self.assertNotIn('SYNTHETIC-TOKEN', repr(self.provider))
        self.assertNotIn('SYNTHETIC-TOKEN', repr(self.response))

    def test_deltas_stream_and_only_explicit_completion_is_success(self):
        self.source = FakeStream(sse({'type': 'response.output_text.delta', 'delta': 'First '},
                                    {'type': 'response.output_text.delta', 'delta': 'second'},
                                    {'type': 'response.completed'}))
        self.response = openai.TransportResponse(200, stream=self.source)
        self.assertEqual(self.events(), [ProviderEvent('text', text='First '),
                                       ProviderEvent('text', text='second'), ProviderEvent('done')])
        for payload in [b'', b'data: [DONE]\n\n', sse({'type': 'response.output_text.delta', 'delta': 'Partial'})]:
            self.source = FakeStream(payload)
            self.response = openai.TransportResponse(200, stream=self.source)
            self.assertEqual(self.events()[-1], ProviderEvent('error', code='interrupted'))
            self.assertTrue(self.source.was_closed)

    def test_failure_incomplete_usage_limits_and_http_errors_are_safe_terminal_errors(self):
        for event, code in [({'type': 'response.failed', 'response': {'error': {
                'code': 'subscription_sharing_usage_limit_exceeded', 'message': 'SECRET'}}}, 'rate_limited'),
                ({'type': 'response.failed', 'response': {'error': {
                    'code': 'subscription_sharing_usage_unavailable'}}}, 'unavailable'),
                ({'type': 'error', 'message': 'SECRET'}, 'provider_error'),
                ({'type': 'response.incomplete'}, 'incomplete')]:
            self.response = openai.TransportResponse(200, stream=FakeStream(sse(event)))
            events = self.events()
            self.assertEqual(events, [ProviderEvent('error', code=code)])
            self.assertNotIn('SECRET', repr(events))
        for status, code in [(400, 'request_rejected'), (401, 'unauthorized'), (403, 'permission_denied'),
                             (422, 'request_rejected'), (429, 'rate_limited'), (500, 'provider_error'),
                             (502, 'unavailable'), (503, 'unavailable'), (504, 'unavailable')]:
            self.response = openai.TransportResponse(status, body={'error': 'SECRET'})
            self.assertEqual(self.events(), [ProviderEvent('error', code=code)])

    def test_event_and_output_limits_close_transport_and_never_synthesize_completion(self):
        for payload in [b'data:' + b'x' * openai.MAX_EVENT_BYTES + b'\n\n',
                        sse({'type': 'response.output_text.delta', 'delta': 'x' * 16001})]:
            self.source = FakeStream(payload)
            self.response = openai.TransportResponse(200, stream=self.source)
            self.assertEqual(self.events(), [ProviderEvent('error', code='limit_exceeded')])
            self.assertTrue(self.source.was_closed)
        self.source = FakeStream(sse({'type': 'response.output_text.delta', 'delta': 'x' * 16000},
                                    {'type': 'response.completed'}))
        self.response = openai.TransportResponse(200, stream=self.source)
        events = self.events()
        self.assertEqual(sum(len(event.text) for event in events), 16000)
        self.assertEqual(events[-1], ProviderEvent('done'))

    def test_cancel_and_abandonment_close_open_transport_and_precancel_sends_nothing(self):
        self.source = FakeStream(sse({'type': 'response.output_text.delta', 'delta': 'First'},
                                    {'type': 'response.completed'}))
        self.response = openai.TransportResponse(200, stream=self.source)
        token = CancellationToken()
        stream = stream_response(self.provider, self.request, token)
        self.assertEqual(next(stream).kind, 'text')
        token.cancel()
        self.assertTrue(self.source.was_closed)
        self.assertEqual(list(stream), [ProviderEvent('error', code='cancelled')])
        calls = len(self.calls)
        self.assertEqual(list(stream_response(self.provider, self.request, token)),
                         [ProviderEvent('error', code='cancelled')])
        self.assertEqual(len(self.calls), calls)

    def test_invalid_model_catalogues_stream_json_and_selected_model_fail_closed(self):
        for body in [{}, {'models': {}}, {'models': [{'visibility': 'list', 'slug': '../unsafe', 'display_name': 'X'}]},
                     {'models': [{'visibility': 'list', 'slug': 'valid', 'display_name': ''}]}]:
            self.response = openai.TransportResponse(200, body=body)
            with self.assertRaises(ProviderError):
                self.provider.list_models()
        for payload in [b'data: not-json\n\n', sse({'type': 'response.output_text.delta', 'delta': ['SECRET']})]:
            self.response = openai.TransportResponse(200, stream=FakeStream(payload))
            self.assertEqual(self.events(), [ProviderEvent('error', code='invalid_response')])
        events = list(stream_response(self.provider, GenerationRequest('{}'), CancellationToken()))
        self.assertEqual(events, [ProviderEvent('error', code='invalid_model')])

    def test_structured_rejections_keep_only_known_codes_and_top_level_parameters(self):
        for error, expected in [({'code': 'missing_required_parameter', 'param': 'input'}, 'request_rejected'),
                ({'code': 'invalid_value', 'param': 'model'}, 'request_rejected'),
                ({'code': 'unsupported_parameter', 'param': 'stream'}, 'request_rejected'),
                ({'code': 'subscription_sharing_unsupported_capability', 'param': 'instructions'}, 'request_rejected'),
                ({'code': 'model_not_found', 'param': 'model'}, 'invalid_model'),
                ({'code': None, 'type': 'invalid_request_error', 'param': 'store'}, 'request_rejected')]:
            self.response = openai.TransportResponse(400, body={'error': {
                **error, 'message': 'SYNTHETIC-SECRET-BODY', 'detail': 'PRIVATE-TEXT'}})
            with self.assertLogs(openai.logger, level='WARNING') as logs:
                self.assertEqual(self.events(), [ProviderEvent('error', code=expected)])
            output = '\n'.join(logs.output)
            self.assertIn('status=400', output)
            self.assertIn('code=' + (error['code'] or error['type']), output)
            self.assertIn('param=' + error['param'], output)
            self.assertNotIn('SYNTHETIC-SECRET', output)
            self.assertNotIn('PRIVATE', output)
        self.response = openai.TransportResponse(500, body={'error': {
            'code': 'SECRET-CODE\nforged=log', 'param': 'input[0].SECRET',
            'type': ['SYNTHETIC-TOKEN'], 'message': 'PRIVATE-TEXT'}, 'detail': 'SECRET'})
        with self.assertLogs(openai.logger, level='WARNING') as logs:
            self.assertEqual(self.events(), [ProviderEvent('error', code='provider_error')])
        self.assertEqual(logs.records[0].getMessage(),
                         'OpenAI provider failure status=500 code=unknown param=unknown')

    def test_structured_stream_failures_use_same_safe_recovery_and_log_allowlist(self):
        for code, expected in [('subscription_sharing_user_not_eligible', 'permission_denied'),
                ('subscription_sharing_invalid_user', 'unauthorized'),
                ('subscription_sharing_user_unavailable', 'unavailable'),
                ('model_not_found', 'invalid_model')]:
            self.response = openai.TransportResponse(200, stream=FakeStream(sse({
                'type': 'response.failed', 'response': {'error': {'code': code,
                    'param': 'model', 'message': 'SYNTHETIC-SECRET'}}})))
            with self.assertLogs(openai.logger, level='WARNING') as logs:
                self.assertEqual(self.events(), [ProviderEvent('error', code=expected)])
            self.assertNotIn('SYNTHETIC-SECRET', '\n'.join(logs.output))

    def test_disabled_gate_and_authorization_failure_never_open_inference_transport(self):
        with override_settings(ASSISTANT_OPENAI_INFERENCE_ENABLED=False):
            self.assertEqual(self.events(), [ProviderEvent('error', code='unavailable')])
        self.assertEqual(self.calls, [])
        self.authorize.side_effect = service.ConnectionError('reconnect_required')
        self.assertEqual(self.events(), [ProviderEvent('error', code='unauthorized')])
        self.assertEqual(self.calls, [])

    def test_timeout_and_unknown_transport_exceptions_are_sanitized(self):
        self.provider.transport = lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError('SECRET'))
        events = self.events()
        self.assertEqual(events, [ProviderEvent('error', code='transport_error')])
        self.assertNotIn('SECRET', repr(events))

    def test_total_deadline_is_checked_after_each_read_and_closes_stream(self):
        with patch.object(openai.time, 'monotonic', side_effect=[0, 0, 91]):
            self.assertEqual(self.events(), [ProviderEvent('error', code='timeout')])
        self.assertTrue(self.source.was_closed)

    def test_cancellation_interrupts_a_blocked_transport_read(self):
        entered, release = Event(), Event()
        class BlockingStream:
            closed = False

            def readline(self, limit):
                entered.set()
                release.wait(3)
                return b''

            def close(self):
                self.closed = True
                release.set()
        source = BlockingStream()
        self.response = openai.TransportResponse(200, stream=source)
        token = CancellationToken()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(lambda: list(stream_response(self.provider, self.request, token)))
            self.assertTrue(entered.wait(2))
            token.cancel()
            self.assertTrue(source.closed)
            self.assertEqual(pending.result(timeout=2), [ProviderEvent('error', code='cancelled')])


class BaseCompletionTests(SimpleTestCase):
    def test_bare_eof_cannot_finish_and_total_output_limit_applies_to_every_provider(self):
        class EarlyEOF:
            def stream(self, request, cancellation):
                yield ProviderEvent('text', text='Partial')
        self.assertEqual(list(stream_response(EarlyEOF(), GenerationRequest('{}'), CancellationToken())),
                         [ProviderEvent('text', text='Partial'), ProviderEvent('error', code='interrupted')])
        class Excessive:
            def stream(self, request, cancellation):
                for _ in range(5):
                    yield ProviderEvent('text', text='x' * 4000)
        self.assertEqual(list(stream_response(Excessive(), GenerationRequest('{}'), CancellationToken()))[-1],
                         ProviderEvent('error', code='limit_exceeded'))
        self.assertEqual(len(ChatTurn('assistant', 'x' * 16000).content), 16000)
        with self.assertRaises(ValueError):
            ChatTurn('assistant', 'x' * 16001)


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
class AuthorizedProviderTests(TransactionTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='tuxedo-provider-credentials.')
        self.addCleanup(self.temp.cleanup)
        override = override_settings(ASSISTANT_PRIVATE_DIR=Path(self.temp.name) / 'private')
        override.enable()
        self.addCleanup(override.disable)
        self.user, self.other = make_owner('provider-owner'), make_owner('provider-other')
        self.vault = CredentialVault()
        self.vault.initialize()
        no_network = patch.object(oauth.HTTPTransport, '__call__', side_effect=AssertionError('No real OAuth'))
        no_network.start()
        self.addCleanup(no_network.stop)
        self.connection = ProviderConnection.objects.create(user=self.user, issuer='https://auth.openai.com',
            subject='synthetic-subject', client_id='synthetic-client', scopes=['resource.invoke', 'chatgpt.tokens.use.direct'],
            status='ready', is_active=True)
        self.credentials = {'issuer': self.connection.issuer, 'subject': self.connection.subject,
            'client_id': self.connection.client_id, 'host_id': self.vault.host_id(), 'email': '',
            'scopes': self.connection.scopes, 'capability': 'plan_authorized',
            'expires_at': (timezone.now() + timedelta(hours=1)).isoformat(),
            'access_token': 'SYNTHETIC-ACCESS', 'refresh_token': 'SYNTHETIC-REFRESH'}
        self.vault.write(self.connection.pk, self.credentials)

    def test_provider_resolution_and_token_read_require_selected_owner_and_both_gates(self):
        self.assertIsInstance(get_provider(), DisconnectedProvider)
        self.assertIsInstance(get_provider(AnonymousUser()), DisconnectedProvider)
        self.assertIsInstance(get_provider(self.other, self.connection.pk), DisconnectedProvider)
        self.assertIsInstance(get_provider(self.user, self.connection.pk), openai.OpenAIProvider)
        token = service.get_authorized_access_token(self.user, self.connection.pk)
        self.assertEqual(token.value, 'SYNTHETIC-ACCESS')
        self.assertNotIn('SYNTHETIC', repr(token))
        self.assertNotIn('SYNTHETIC', str(token))
        with override_settings(ASSISTANT_OPENAI_INFERENCE_ENABLED=False):
            self.assertIsInstance(get_provider(self.user), DisconnectedProvider)
            with self.assertRaises(service.ConnectionError):
                service.get_authorized_access_token(self.user, self.connection.pk)

    def test_token_helper_rejects_inactive_mismatched_identity_and_insufficient_grant(self):
        for change in [{'is_active': False}, {'status': 'identity_only'}]:
            ProviderConnection.objects.filter(pk=self.connection.pk).update(**change)
            with self.assertRaises(service.ConnectionError):
                service.get_authorized_access_token(self.user, self.connection.pk)
            ProviderConnection.objects.filter(pk=self.connection.pk).update(is_active=True, status='ready')
        for changes in [{'subject': 'foreign-subject'}, {'scopes': ['openid']}]:
            self.vault.write(self.connection.pk, {**self.credentials, **changes})
            with self.assertRaises(service.ConnectionError):
                service.get_authorized_access_token(self.user, self.connection.pk)

    def test_token_helper_refreshes_expiring_credentials_then_reads_rotated_token(self):
        self.vault.write(self.connection.pk, {
            **self.credentials, 'expires_at': (timezone.now() + timedelta(seconds=30)).isoformat()})
        rotated = {**self.credentials, 'access_token': 'SYNTHETIC-ROTATED', 'refresh_token': 'SYNTHETIC-ROTATED-REFRESH'}
        with patch.object(oauth, 'refresh_credentials', return_value=rotated) as refresh:
            token = service.get_authorized_access_token(self.user, self.connection.pk)
        self.assertEqual(token.value, 'SYNTHETIC-ROTATED')
        refresh.assert_called_once()


class ProviderHTTPTransportTests(SimpleTestCase):
    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_missing_sse_content_type_preserves_first_event_and_uses_existing_parser(self):
        expected = [ProviderEvent('text', text='First preserved'), ProviderEvent('done')]
        for first_line in [b'', b'event: response.output_text.delta\n', b': heartbeat\n\n']:
            response = io.BytesIO(first_line + sse(
                {'type': 'response.output_text.delta', 'delta': 'First preserved'},
                {'type': 'response.completed'}))
            response.status, response.headers = 200, Message()
            with patch.object(openai.request, 'build_opener') as build, \
                    patch.object(service, 'get_authorized_access_token',
                                 return_value=service.AuthorizedAccessToken('SYNTHETIC-OAUTH')):
                build.return_value.open.return_value = response
                events = list(stream_response(openai.OpenAIProvider(object(), 'synthetic'),
                                             GenerationRequest('{}', model='synthetic'), CancellationToken()))
            self.assertEqual(events, expected)
            self.assertTrue(response.closed)
            self.assertEqual(build.return_value.open.call_count, 1)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_missing_sse_content_type_keeps_eof_incomplete_and_invalid_frame_failures(self):
        for payload, expected in [
                (sse({'type': 'response.output_text.delta', 'delta': 'Partial'}),
                 [ProviderEvent('text', text='Partial'), ProviderEvent('error', code='interrupted')]),
                (sse({'type': 'response.output_text.delta', 'delta': 'Partial'}, {'type': 'response.incomplete'}),
                 [ProviderEvent('text', text='Partial'), ProviderEvent('error', code='incomplete')]),
                (b'data: [DONE]\n\n', [ProviderEvent('error', code='interrupted')]),
                (b'data: {PRIVATE-TEXT}\n\n', [ProviderEvent('error', code='invalid_response')])]:
            response = io.BytesIO(payload)
            response.status, response.headers = 200, Message()
            with patch.object(openai.request, 'build_opener') as build, \
                    patch.object(service, 'get_authorized_access_token',
                                 return_value=service.AuthorizedAccessToken('SYNTHETIC-OAUTH')):
                build.return_value.open.return_value = response
                events = list(stream_response(openai.OpenAIProvider(object(), 'synthetic'),
                                             GenerationRequest('{}', model='synthetic'), CancellationToken()))
            self.assertEqual(events, expected)
            self.assertTrue(response.closed)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_missing_header_non_sse_and_explicit_wrong_mime_remain_rejected_without_output(self):
        for content_type, payload, stream in [
                (None, b'{"object":"response","output":[{"text":"PRIVATE-TEXT"}]}', True),
                (None, b'<html>PRIVATE-TEXT</html>', True),
                (None, b' data: {"type":"response.completed"}\n\n', True),
                (None, b'data: ' + b'x' * openai.MAX_ERROR_BYTES, True),
                ('text/plain', sse({'type': 'response.completed'}), True),
                ('', sse({'type': 'response.completed'}), True),
                (None, b'{"models":[]}', False)]:
            response = io.BytesIO(payload)
            response.status, response.headers = 200, Message()
            if content_type is not None:
                response.headers['Content-Type'] = content_type
            with patch.object(openai.request, 'build_opener') as build, \
                    patch.object(service, 'get_authorized_access_token',
                                 return_value=service.AuthorizedAccessToken('SYNTHETIC-OAUTH')), \
                    self.assertLogs(openai.logger, level='WARNING') as logs:
                build.return_value.open.return_value = response
                provider = openai.OpenAIProvider(object(), 'synthetic')
                if stream:
                    events = list(stream_response(provider, GenerationRequest('{}', model='synthetic'), CancellationToken()))
                    self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                else:
                    with self.assertRaises(ProviderError) as caught:
                        provider.list_models()
                    self.assertEqual(caught.exception.code, 'invalid_response')
            self.assertNotIn('PRIVATE-TEXT', '\n'.join(logs.output))
            self.assertTrue(response.closed)
            self.assertEqual(build.return_value.open.call_count, 1)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_http_error_json_is_sanitized_before_return_and_diagnostic_logging(self):
        payload = io.BytesIO(json.dumps({'error': {'code': None, 'type': 'invalid_request_error',
            'param': 'input', 'message': 'SYNTHETIC-PRIVATE-QUESTION',
            'detail': 'Bearer SYNTHETIC-TOKEN'}, 'request_id': 'PRIVATE-ID'}).encode())
        headers = Message()
        headers['Content-Type'] = 'application/json'
        rejected = openai.error.HTTPError(openai.RESPONSES_ENDPOINT, 400, 'PRIVATE-REASON', headers, payload)
        with patch.object(openai.request, 'build_opener') as build:
            build.return_value.open.side_effect = rejected
            response = openai.HTTPTransport()('POST', openai.RESPONSES_ENDPOINT, stream=True,
                access_token='SYNTHETIC-TOKEN', data={'model': 'synthetic', 'input': [], 'store': False, 'stream': True})
        self.assertEqual(response.body, {'error': {'type': 'invalid_request_error', 'param': 'input'}})
        self.assertEqual(build.return_value.open.call_count, 1)
        self.assertTrue(payload.closed)
        with self.assertLogs(openai.logger, level='WARNING') as logs, self.assertRaises(ProviderError) as caught:
            openai._status(response)
        self.assertEqual(caught.exception.code, 'request_rejected')
        self.assertEqual(str(caught.exception), 'request_rejected')
        self.assertEqual(logs.records[0].getMessage(),
                         'OpenAI provider failure status=400 code=invalid_request_error param=input')
        self.assertNotIn('SYNTHETIC', repr(response) + repr(caught.exception) + '\n'.join(logs.output))
        self.assertNotIn('PRIVATE', repr(response) + repr(caught.exception) + '\n'.join(logs.output))

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_nonstandard_or_oversized_error_body_is_bounded_discarded_and_never_logged(self):
        class BoundedResponse(io.BytesIO):
            def read(self, limit):
                self.read_limits.append(limit)
                return super().read(limit)
        for content_type, payload in [
                ('text/html', b'<html>PRIVATE-ERROR Bearer SYNTHETIC-TOKEN</html>'),
                ('application/json', b'{not-json PRIVATE-ERROR'),
                ('application/json', b'{"detail":"PRIVATE-ERROR"}'),
                ('application/json', json.dumps({'error': {'code': 'PRIVATE-ERROR',
                    'param': 'input[0].PRIVATE-ERROR', 'message': 'SYNTHETIC-TOKEN'}}).encode()),
                ('application/json', json.dumps({'error': {'code': 'model_not_found', 'param': 'model',
                    'message': 'PRIVATE-ERROR' + 'x' * openai.MAX_ERROR_BYTES}}).encode())]:
            response = BoundedResponse(payload)
            response.status, response.read_limits = 400, []
            response.headers = Message()
            response.headers['Content-Type'] = content_type
            with patch.object(openai.request, 'build_opener') as build:
                build.return_value.open.return_value = response
                result = openai.HTTPTransport()('POST', openai.RESPONSES_ENDPOINT, stream=True,
                                               access_token='SYNTHETIC-TOKEN')
            self.assertEqual(result.body, {})
            self.assertTrue(response.closed)
            self.assertEqual(response.read_limits, [openai.MAX_ERROR_BYTES + 1]
                             if content_type == 'application/json' else [])
            self.assertEqual(build.return_value.open.call_count, 1)
            with self.assertLogs(openai.logger, level='WARNING') as logs, self.assertRaises(ProviderError) as caught:
                openai._status(result)
            self.assertEqual(caught.exception.code, 'request_rejected')
            self.assertEqual(logs.records[0].getMessage(),
                             'OpenAI provider failure status=400 code=unknown param=unknown')

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_success_with_wrong_content_type_invalid_json_or_schema_has_safe_protocol_diagnostic(self):
        for content_type, payload, stream, reason in [
                ('text/html; private=SYNTHETIC-TOKEN', b'PRIVATE-ERROR', False, 'unexpected_content_type'),
                ('application/json', b'PRIVATE-ERROR', True, 'unexpected_content_type'),
                ('application/json', b'{PRIVATE-ERROR', False, 'invalid_json'),
                ('application/json', b'[]', False, 'invalid_schema')]:
            response = io.BytesIO(payload)
            response.status, response.headers = 200, Message()
            response.headers['Content-Type'] = content_type
            with patch.object(openai.request, 'build_opener') as build, \
                    self.assertLogs(openai.logger, level='WARNING') as logs, self.assertRaises(ProviderError) as caught:
                build.return_value.open.return_value = response
                openai.HTTPTransport()('POST' if stream else 'GET',
                    openai.RESPONSES_ENDPOINT if stream else openai.MODELS_ENDPOINT,
                    access_token='SYNTHETIC-TOKEN', stream=stream)
            self.assertEqual(caught.exception.code, 'invalid_response')
            expected = 'OpenAI provider failure status=200 code=' + reason + ' param=unknown'
            if reason == 'unexpected_content_type':
                expected += (' expected_content_type=' + ('text/event-stream' if stream else 'application/json')
                             + ' actual_content_type=' + ('application/json' if stream else 'other')
                             + ' body_kind=other response_error_code=unknown response_error_type=unknown')
            self.assertEqual(logs.records[0].getMessage(), expected)
            self.assertNotIn('PRIVATE', '\n'.join(logs.output) + repr(caught.exception))
            self.assertNotIn('SYNTHETIC', '\n'.join(logs.output) + repr(caught.exception))
            self.assertTrue(response.closed)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_unexpected_mime_body_classification_is_bounded_safe_and_never_becomes_output(self):
        class TrackedResponse(io.BytesIO):
            def read(self, limit):
                self.read_sizes.append(limit)
                result = super().read(limit)
                self.consumed += len(result)
                return result

            def readline(self, limit):
                self.read_sizes.append(limit)
                result = super().readline(limit)
                self.consumed += len(result)
                return result
        cases = [
            ('text/plain', b'event: response.created\n' + b'PRIVATE-TEXT' * 10000, 'sse_prefix', 'text/plain'),
            ('application/json', json.dumps({'object': 'response', 'id': 'PRIVATE-ID',
                'output': [{'text': 'PRIVATE-TEXT'}]}, indent=2).encode(), 'response_object', 'application/json'),
            ('application/octet-stream', json.dumps({'error': {'code': 'unsupported_parameter',
                'type': 'invalid_request_error', 'param': 'input', 'message': 'Bearer PRIVATE-TOKEN'}}).encode(),
                'error_object', 'application/octet-stream'),
            ('text/plain', json.dumps({'error': {'code': 'PRIVATE-CODE', 'param': 'input[PRIVATE-ID]',
                'message': 'PRIVATE-TEXT'}}).encode(), 'error_object', 'text/plain'),
            ('custom/PRIVATE-HEADER', b'not-sse\n' + b'PRIVATE-TEXT' * 10000, 'other', 'other'),
            (None, b'PRIVATE-TEXT', 'other', 'missing'),
        ]
        for content_type, payload, kind, actual in cases:
            response = TrackedResponse(payload)
            response.status, response.headers = 200, Message()
            response.read_sizes, response.consumed = [], 0
            if content_type is not None:
                response.headers['Content-Type'] = content_type
            with patch.object(openai.request, 'build_opener') as build, \
                    self.assertLogs(openai.logger, level='WARNING') as logs, self.assertRaises(ProviderError) as caught:
                build.return_value.open.return_value = response
                openai.HTTPTransport()('POST', openai.RESPONSES_ENDPOINT, stream=True, access_token='SYNTHETIC-OAUTH')
            self.assertEqual(caught.exception.code, 'invalid_response')
            message = logs.records[0].getMessage()
            self.assertIn('expected_content_type=text/event-stream actual_content_type=' + actual, message)
            self.assertIn('body_kind=' + kind, message)
            self.assertNotIn('PRIVATE', message + repr(caught.exception))
            if content_type == 'application/octet-stream':
                self.assertIn('param=input', message)
                self.assertIn('response_error_code=unsupported_parameter response_error_type=invalid_request_error', message)
            else:
                self.assertIn('param=unknown', message)
                self.assertIn('response_error_code=unknown response_error_type=unknown', message)
            self.assertLessEqual(response.consumed, openai.MAX_ERROR_BYTES)
            self.assertTrue(all(0 < size <= openai.MAX_ERROR_BYTES for size in response.read_sizes))
            self.assertTrue(response.closed)
            self.assertEqual(build.return_value.open.call_count, 1)
            if kind == 'sse_prefix':
                self.assertEqual(response.read_sizes, [openai.MAX_ERROR_BYTES])
                self.assertEqual(response.consumed, len(b'event: response.created\n'))

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_sse_mime_case_and_charset_are_normalized_and_catalogue_mismatch_is_distinct(self):
        for content_type in ['text/event-stream', 'Text/Event-Stream; charset=utf-8']:
            response = io.BytesIO(sse({'type': 'response.completed'}))
            response.status, response.headers = 200, Message()
            response.headers['Content-Type'] = content_type
            with patch.object(openai.request, 'build_opener') as build, \
                    patch.object(service, 'get_authorized_access_token',
                                 return_value=service.AuthorizedAccessToken('SYNTHETIC-OAUTH')):
                build.return_value.open.return_value = response
                events = list(stream_response(openai.OpenAIProvider(object(), 'synthetic'),
                                             GenerationRequest('{}', model='synthetic'), CancellationToken()))
            self.assertEqual(events, [ProviderEvent('done')])
            self.assertTrue(response.closed)
        response = io.BytesIO(sse({'type': 'response.completed'}))
        response.status, response.headers = 200, Message()
        response.headers['Content-Type'] = 'text/event-stream'
        with patch.object(openai.request, 'build_opener') as build, \
                self.assertLogs(openai.logger, level='WARNING') as logs, self.assertRaises(ProviderError):
            build.return_value.open.return_value = response
            openai.HTTPTransport()('GET', openai.MODELS_ENDPOINT, access_token='SYNTHETIC-OAUTH')
        self.assertIn('expected_content_type=application/json actual_content_type=text/event-stream body_kind=sse_prefix',
                      logs.records[0].getMessage())

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_paid_api_key_environment_never_replaces_oauth_or_retries_subscription_failure(self):
        response = io.BytesIO(json.dumps({'error': {'code': 'subscription_sharing_usage_limit_exceeded',
                                                   'message': 'PRIVATE-TEXT'}}).encode())
        response.status, response.headers = 429, Message()
        response.headers['Content-Type'] = 'application/json'
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'SYNTHETIC-PAID-KEY'}), \
                patch.object(openai.request, 'build_opener') as build, \
                patch.object(service, 'get_authorized_access_token',
                             return_value=service.AuthorizedAccessToken('SYNTHETIC-OAUTH')), \
                self.assertLogs(openai.logger, level='WARNING') as logs:
            build.return_value.open.return_value = response
            events = list(stream_response(openai.OpenAIProvider(object(), 'synthetic'),
                                         GenerationRequest('{}', model='synthetic'), CancellationToken()))
        self.assertEqual(events, [ProviderEvent('error', code='rate_limited')])
        self.assertEqual(build.return_value.open.call_count, 1)
        outgoing = build.return_value.open.call_args.args[0]
        self.assertEqual(outgoing.full_url, openai.RESPONSES_ENDPOINT)
        self.assertEqual(outgoing.headers['Authorization'], 'Bearer SYNTHETIC-OAUTH')
        self.assertNotIn('SYNTHETIC-PAID-KEY', repr(outgoing.headers) + repr(outgoing.data) + '\n'.join(logs.output))

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_rich_model_catalogue_above_512_kib_preserves_visible_order_within_two_mib(self):
        models = [{'slug': 'synthetic-' + str(index), 'display_name': 'Synthetic ' + str(index),
                   'visibility': 'list' if index < 7 else 'hidden',
                   'metadata': {'description': 'x' * 70000}}
                  for index in range(9)]
        payload = json.dumps({'models': models}).encode()
        self.assertGreater(len(payload), 512 * 1024)
        self.assertLess(len(payload), 2 * 1024 * 1024)
        response = io.BytesIO(payload)
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'application/json'
        with patch.object(openai.request, 'build_opener') as build, \
                patch.object(service, 'get_authorized_access_token',
                             return_value=service.AuthorizedAccessToken('SYNTHETIC-TOKEN')):
            build.return_value.open.return_value = response
            selected = openai.OpenAIProvider(object(), 'synthetic-connection').list_models()
        self.assertEqual(selected, [{'slug': 'synthetic-' + str(index), 'display_name': 'Synthetic ' + str(index),
                                     'reasoning_efforts': []}
                                    for index in range(7)])
        self.assertTrue(response.closed)
        self.assertEqual(openai.MAX_EVENT_BYTES, 512 * 1024)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_model_catalogue_above_two_mib_is_rejected_and_closed_without_retry(self):
        payload = json.dumps({'models': [{'slug': 'synthetic', 'display_name': 'Synthetic',
                                         'visibility': 'list', 'metadata': {'description': 'x' * (2 * 1024 * 1024)}}]}).encode()
        response = io.BytesIO(payload)
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'application/json'
        with patch.object(openai.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            with self.assertRaises(ProviderError) as caught:
                openai.HTTPTransport()('GET', openai.MODELS_ENDPOINT, access_token='SYNTHETIC-TOKEN')
        self.assertEqual(caught.exception.code, 'limit_exceeded')
        self.assertEqual(build.return_value.open.call_count, 1)
        self.assertTrue(response.closed)

    @override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
    def test_http_transport_pins_endpoints_and_sends_bearer_only_in_header_without_retries(self):
        response = io.BytesIO(b'{"models":[]}')
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'application/json'
        with patch.object(openai.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            result = openai.HTTPTransport()('GET', openai.MODELS_ENDPOINT, access_token='SYNTHETIC-TOKEN')
        self.assertEqual(result.body, {'models': []})
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[1], openai._NoRedirects)
        self.assertEqual(build.return_value.open.call_count, 1)
        self.assertEqual(build.return_value.open.call_args.kwargs, {'timeout': 15})
        outgoing = build.return_value.open.call_args.args[0]
        self.assertEqual(outgoing.headers['Authorization'], 'Bearer SYNTHETIC-TOKEN')
        self.assertIsNone(outgoing.data)
        with patch.object(openai.request, 'build_opener') as build:
            for url in ['https://evil.test/v1/models', 'https://api.openai.com/v1/responses?token=SECRET',
                        'https://chatgpt.com/backend-api/models']:
                with self.assertRaises(ProviderError):
                    openai.HTTPTransport()('GET', url, access_token='SYNTHETIC-TOKEN')
            build.assert_not_called()

    @override_settings(ASSISTANT_OPENAI_INFERENCE_ENABLED=False)
    def test_disabled_transport_opens_no_socket(self):
        with patch.object(openai.request, 'build_opener') as build:
            with self.assertRaises(ProviderError):
                openai.HTTPTransport()('GET', openai.MODELS_ENDPOINT, access_token='SYNTHETIC-TOKEN')
            build.assert_not_called()
