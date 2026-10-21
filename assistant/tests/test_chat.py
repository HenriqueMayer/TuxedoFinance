# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic streaming lifecycle checks: no live account, token, or inference."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
import uuid

from django.core.cache import cache
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from assistant import chat
from assistant.context import sign_scope
from assistant.models import Conversation, GenerationRun, Message, ProviderConnection
from assistant.providers.base import ProviderEvent
from assistant.tests.support import make_finances, make_owner


class SyntheticProvider:
    available = True

    def __init__(self, events=None):
        self.events = events or [ProviderEvent('text', text='Synthetic answer.'), ProviderEvent('done')]
        self.requests, self.closed, self.catalog_calls = [], 0, 0

    def list_models(self):
        assert not connection.in_atomic_block
        self.catalog_calls += 1
        return [{'slug': 'synthetic-model', 'display_name': 'Synthetic model',
                 'reasoning_efforts': ['low', 'high'], 'default_reasoning_effort': 'low'},
                {'slug': 'another-model', 'display_name': 'Another model'}]

    def stream(self, request, cancellation):
        assert not connection.in_atomic_block
        self.requests.append(request)
        try:
            for event in self.events:
                assert not connection.in_atomic_block
                if isinstance(event, Exception):
                    raise event
                yield event
        finally:
            self.closed += 1


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
class StreamingChatTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.private = TemporaryDirectory(prefix='tuxedo-chat-vault.')
        self.addCleanup(self.private.cleanup)
        self.override = override_settings(ASSISTANT_PRIVATE_DIR=Path(self.private.name) / 'private')
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user, self.other = make_owner('chat-owner'), make_owner('chat-other')
        self.client.force_login(self.user)
        self.account = ProviderConnection.objects.create(
            user=self.user, issuer='https://auth.openai.com', subject='synthetic-owner',
            client_id='synthetic-registration', scopes=['chatgpt.tokens.use.direct', 'resource.invoke'],
            status=ProviderConnection.Status.READY, is_active=True)
        self.conversation = Conversation.objects.create(user=self.user, title='Synthetic chat')
        self.foreign = Conversation.objects.create(user=self.other, title='Foreign private chat')
        self.provider = SyntheticProvider()
        self.fake_provider = patch('assistant.chat.get_provider', return_value=self.provider)
        self.fake_provider.start()
        self.addCleanup(self.fake_provider.stop)
        no_network = patch('assistant.providers.openai.HTTPTransport.__call__',
                           side_effect=AssertionError('No real inference'))
        no_network.start()
        self.addCleanup(no_network.stop)

    def data(self, **overrides):
        data = {'content': 'Synthetic question', 'model': 'synthetic-model',
                'connection_id': str(self.account.pk), 'request_id': str(uuid.uuid4())}
        data.update(overrides)
        return data

    def send(self, data=None, conversation=None, stream=True):
        path = reverse('assistant:send', args=[(conversation or self.conversation).pk])
        return self.client.post(path, data or self.data(), HTTP_ACCEPT='text/event-stream' if stream else 'text/html')

    def events(self, response):
        self.assertEqual(response.status_code, 200)
        chunks = b''.join(response.streaming_content).decode()
        events = []
        for packet in chunks.strip().split('\n\n'):
            lines = packet.splitlines()
            events.append((lines[0].removeprefix('event: '), json.loads(lines[1].removeprefix('data: '))))
        return events

    def test_catalog_is_owned_cached_ordered_and_never_selects_an_invented_default(self):
        first = self.client.get(reverse('assistant:index'))
        self.assertEqual(first.context['provider_state'], 'ready')
        self.assertEqual(first.context['selected_model'], '')
        self.assertEqual(first.context['send_form'].fields['model'].choices[0][0], '')
        self.assertFalse(first.context['send_form'].initial.get('include_context', False))
        second = self.client.get(reverse('assistant:models')).json()
        self.assertEqual([item['slug'] for item in second['models']], ['synthetic-model', 'another-model'])
        self.assertEqual(self.provider.catalog_calls, 1)
        self.assertEqual(self.provider.requests, [])
        self.assertFalse((Path(self.private.name) / 'private').exists())
        self.client.get(reverse('assistant:models'), {'refresh': '1'})
        self.assertEqual(self.provider.catalog_calls, 2)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('assistant:models')).json()['models'], [])

    def test_selected_account_is_disabled_locally_without_becoming_disconnected(self):
        for auth, inference, code in [(False, True, 'auth_disabled'),
                                      (True, False, 'disabled'), (False, False, 'auth_disabled')]:
            with self.subTest(auth=auth, inference=inference), override_settings(
                    ASSISTANT_OPENAI_AUTH_ENABLED=auth, ASSISTANT_OPENAI_INFERENCE_ENABLED=inference), \
                    patch('assistant.chat.get_provider') as resolve:
                state = chat.composer_state(self.user)
                self.assertEqual(state, {'provider_state': 'disabled', 'error': code, 'models': [],
                                         'connection_id': str(self.account.pk)})
                response = self.client.get(reverse('assistant:index'), HTTP_ACCEPT_LANGUAGE='en',
                                           HTTP_X_TUXEDO_ASSISTANT='panel')
                self.assertContains(response, 'Chat disabled on this installation')
                self.assertNotContains(response, 'Provider not connected')
                self.assertNotContains(response, 'name="content"')
                self.assertEqual(self.client.get(reverse('assistant:models')).json()['provider_state'], 'disabled')
                rejected = self.send(self.data())
                self.assertEqual(rejected.status_code, 503)
                self.assertEqual(rejected.json()['error'], code)
                native = self.send(self.data(), stream=False)
                self.assertContains(native, 'Chat is disabled on this installation. No message was sent or saved.',
                                    status_code=503)
                self.assertNotContains(native, 'No AI provider is connected', status_code=503)
                resolve.assert_not_called()
        self.account.refresh_from_db()
        self.assertTrue(self.account.is_active)
        self.assertEqual(self.account.status, ProviderConnection.Status.READY)
        self.assertEqual(GenerationRun.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(self.provider.catalog_calls, 0)
        self.assertFalse((Path(self.private.name) / 'private').exists())

    def test_disabled_service_preserves_real_absence_reconnect_and_requested_owner_checks(self):
        with override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=False,
                               ASSISTANT_OPENAI_INFERENCE_ENABLED=False), \
                patch('assistant.chat.get_provider') as resolve:
            self.assertEqual(chat.composer_state(self.other)['provider_state'], 'disconnected')
            self.assertEqual(chat.composer_state(self.user, str(uuid.uuid4()))['provider_state'], 'reauth')
            self.account.status = ProviderConnection.Status.RECONNECT
            self.account.save(update_fields=['status'])
            state = chat.composer_state(self.user)
            self.assertEqual(state['provider_state'], 'reauth')
            self.assertEqual(state['connection_id'], str(self.account.pk))
            self.account.status = ProviderConnection.Status.DISCONNECTED
            self.account.is_active = False
            self.account.save(update_fields=['status', 'is_active'])
            self.assertEqual(chat.composer_state(self.user)['provider_state'], 'disconnected')
            resolve.assert_not_called()

    def test_catalogue_capabilities_are_bounded_and_legacy_cache_does_not_hide_efforts(self):
        legacy_key = f'assistant.models.v1:{self.user.pk}:{self.account.pk}:{self.account.updated_at.isoformat()}'
        cache.set(legacy_key, [{'slug': 'legacy-model', 'display_name': 'Stale model'}], 120)
        supplied = [{'slug': 'synthetic-model', 'display_name': 'Synthetic model',
                     'reasoning_efforts': ['high', 'low', 'high', {}, 'future'],
                     'default_reasoning_effort': 'low', 'private_metadata': 'not for client'},
                    {'slug': 'another-model', 'display_name': 'Another model',
                     'reasoning_efforts': ['none'], 'default_reasoning_effort': 'high'}]
        with patch.object(self.provider, 'list_models', return_value=supplied):
            state = self.client.get(reverse('assistant:models')).json()
        self.assertEqual(state['models'], [
            {'slug': 'synthetic-model', 'display_name': 'Synthetic model',
             'reasoning_efforts': ['high', 'low'], 'default_reasoning_effort': 'low'},
            {'slug': 'another-model', 'display_name': 'Another model', 'reasoning_efforts': ['none']},
        ])
        self.assertEqual(self.provider.requests, [])

    def test_model_default_omits_override_while_explicit_effort_is_persisted_and_replayed(self):
        default = self.data()
        self.events(self.send(default))
        self.assertEqual(self.provider.requests[-1].reasoning_effort, '')
        self.assertEqual(GenerationRun.objects.get(pk=default['request_id']).reasoning_effort, '')
        explicit = self.data(reasoning_effort='high')
        self.events(self.send(explicit))
        self.assertEqual(self.provider.requests[-1].reasoning_effort, 'high')
        self.assertEqual(GenerationRun.objects.get(pk=explicit['request_id']).reasoning_effort, 'high')
        self.events(self.send(explicit))
        self.assertEqual(len(self.provider.requests), 2)
        conflict = self.send({**explicit, 'reasoning_effort': 'low'})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['error'], 'request_conflict')

    def test_effort_is_validated_with_its_model_before_any_message_write(self):
        for fields in ({'reasoning_effort': 'invented'}, {'model': 'another-model', 'reasoning_effort': 'high'}):
            with self.subTest(fields=fields):
                response = self.send(self.data(**fields))
                self.assertEqual(response.status_code, 400)
                self.assertIn('reasoning_effort', response.context['send_form'].errors)
                self.assertEqual(response.context['send_form']['reasoning_effort'].value(), fields['reasoning_effort'])
        self.assertEqual(GenerationRun.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(self.provider.requests, [])

    def test_direct_start_run_cannot_bypass_effort_compatibility(self):
        for effort in ['unknown', None, ['high']]:
            with self.subTest(effort=effort), self.assertRaises(chat.ChatError) as invalid:
                chat.start_run(self.user, self.client.session.session_key,
                               self.data(reasoning_effort=effort), conversation=self.conversation)
            self.assertEqual(invalid.exception.code, 'invalid_reasoning_effort')
        with self.assertRaises(chat.ChatError) as incompatible:
            chat.start_run(self.user, self.client.session.session_key,
                           self.data(model='another-model', reasoning_effort='high'), conversation=self.conversation)
        self.assertEqual(incompatible.exception.code, 'invalid_reasoning_effort')
        self.assertEqual(GenerationRun.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(self.provider.requests, [])

    def test_native_effort_post_and_get_retain_the_validated_configuration(self):
        response = self.send(self.data(reasoning_effort='low'), stream=False)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('reasoning_effort=', response['Location'])
        self.assertNotIn('model=', response['Location'])
        self.account.refresh_from_db()
        self.assertEqual((self.account.last_model_slug, self.account.last_reasoning_effort),
                         ('synthetic-model', 'low'))
        page = self.client.get(response['Location'])
        self.assertEqual(page.context['selected_reasoning_effort'], 'low')
        self.assertEqual(page.context['send_form']['reasoning_effort'].value(), 'low')
        self.assertEqual(self.provider.requests[-1].reasoning_effort, 'low')
        invalid_get = self.client.get(reverse('assistant:index'), {
            'model': 'another-model', 'reasoning_effort': 'high'})
        self.assertEqual(invalid_get.context['send_form']['reasoning_effort'].value(), '')

    def test_empty_catalog_disables_composer_and_selected_account_has_its_own_cache(self):
        with patch.object(self.provider, 'list_models', return_value=[]):
            empty = self.client.get(reverse('assistant:models')).json()
        self.assertEqual(empty['provider_state'], 'error')
        self.assertEqual(empty['models'], [])
        ProviderConnection.objects.filter(pk=self.account.pk).update(is_active=False)
        alternate = ProviderConnection.objects.create(
            user=self.user, issuer=self.account.issuer, subject='other-account', client_id='other-registration',
            status='ready', is_active=True)
        active = self.client.get(reverse('assistant:models')).json()
        self.assertEqual(active['connection_id'], str(alternate.pk))
        self.assertEqual(active['models'][0]['slug'], 'synthetic-model')
        self.assertEqual(self.provider.catalog_calls, 1)

    def test_stream_has_owned_metadata_text_done_and_persists_both_messages(self):
        request = self.data()
        response = self.send(request)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Accel-Buffering'], 'no')
        events = self.events(response)
        self.assertEqual([kind for kind, _ in events], ['meta', 'text', 'done'])
        self.assertEqual(events[0][1]['owner'], str(self.user.pk))
        self.assertEqual(events[0][1]['run_id'], request['request_id'])
        run = GenerationRun.objects.get(pk=request['request_id'])
        self.assertEqual(run.status, GenerationRun.Status.COMPLETED)
        self.assertEqual(run.input_message.content, request['content'])
        self.assertEqual(run.output_message.content, 'Synthetic answer.')
        self.assertIsNotNone(run.completed_at)
        self.assertEqual(self.provider.closed, 1)
        self.assertEqual(self.provider.requests[0].model, 'synthetic-model')
        self.assertEqual(self.provider.requests[0].history[-1].content, request['content'])

    def test_real_openai_loop_runs_monthly_simulation_with_omitted_namespace_and_no_financial_writes(self):
        import io
        from decimal import Decimal

        from django.apps import apps

        from assistant.connections import service
        from assistant.models import ActionProposal
        from assistant.providers import openai
        from sandbox.models import ScenarioDraft
        from sandbox.services import CltScenario, calculate_clt

        make_finances(self.user, 'Owned monthly simulation')
        make_finances(self.other, 'Foreign monthly simulation')
        ScenarioDraft.objects.create(user=self.user, kind=ScenarioDraft.Kind.BUDGET,
            name='Existing private draft', payload={'gross_salary': '5000', 'private': 'KEEP THIS DRAFT'})
        question = 'Simule outubro de 2026 com salário bruto CLT de 6000 e desconto de 700.'
        Message.objects.create(conversation=self.conversation, role='user', content=question)
        Message.objects.create(conversation=self.conversation, role='assistant',
                               content='O desconto é em folha ou uma despesa adicional?')
        arguments = {'planning_month': '2026-10', 'gross_salary': '6000', 'clt_dependents': 0,
            'clt_pension': '0', 'clt_transport': '0', 'clt_food': '0', 'clt_health': '0',
            'clt_other': '700', 'extra_expenses': [], 'category_reductions': []}
        payroll = calculate_clt(CltScenario(Decimal('6000'), other_deductions=Decimal('700'))).ordinary
        self.assertEqual(payroll.net, Decimal('4273.39'))
        item = {'type': 'function_call', 'id': 'fc_synthetic_month', 'name': 'simulate_month',
            'call_id': 'call_synthetic_month', 'arguments': json.dumps(arguments), 'status': 'completed'}

        def sse(*events):
            return io.BytesIO(b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events))

        answer = 'Simulação local concluída sem salvar alterações.'
        sources = [sse({'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                       {'type': 'response.completed', 'response': {'output': []}}),
                   sse({'type': 'response.output_text.delta', 'delta': answer},
                       {'type': 'response.completed', 'response': {'output': []}})]
        requests = []

        def transport(method, url, *, access_token, data=None, stream=False, cancellation=None):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(access_token, 'SYNTHETIC-MONTH-TOKEN')
            if method == 'GET':
                self.assertEqual(url, openai.MODELS_ENDPOINT)
                self.assertFalse(stream)
                return openai.TransportResponse(200, body={'models': [{'slug': 'synthetic-model',
                    'display_name': 'Synthetic model', 'visibility': 'list'}]})
            self.assertEqual((method, url, stream), ('POST', openai.RESPONSES_ENDPOINT, True))
            if requests:
                self.assertTrue(sources[0].closed)
            requests.append(json.loads(json.dumps(data)))
            return openai.TransportResponse(200, stream=sources[len(requests) - 1])

        models = [model for model in apps.get_models() if model._meta.app_label in
                  {'accounts', 'banking', 'categories', 'investments', 'planning', 'sandbox', 'transactions'}]

        def financial_state():
            return {model._meta.label: list(model.objects.order_by('pk').values()) for model in models}

        original = financial_state()
        preference = ProviderConnection.objects.filter(pk=self.account.pk).values().get()
        data = self.data(content='Em folha.')
        provider = openai.OpenAIProvider(self.user, self.account.pk, transport=transport)
        with patch('assistant.chat.get_provider', return_value=provider), patch.object(
                service, 'get_authorized_access_token',
                return_value=service.AuthorizedAccessToken('SYNTHETIC-MONTH-TOKEN')), \
                CaptureQueriesContext(connection) as queries:
            run, stream = chat.start_run(self.user, self.client.session.session_key, data,
                                         conversation=self.conversation, language='pt-br')
            events = list(stream)

        self.assertEqual([kind for kind, _payload in events], ['meta', 'text', 'done'])
        self.assertEqual(events[1][1]['delta'], answer)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(source.closed for source in sources))
        first, continued = requests
        context = json.loads(first['input'][0]['content'].split('\n', 1)[1])
        self.assertEqual(context['application_access']['read'], 'all_owned_financial_workspaces')
        self.assertNotIn('metrics', context)
        self.assertIn(question, [turn.get('content') for turn in first['input']])
        self.assertEqual(first['input'][-1]['content'], 'Em folha.')
        self.assertIn('simulate_month', [tool['name'] for tool in first['tools'][0]['tools']])
        returned_call = next(row for row in continued['input'] if row.get('type') == 'function_call')
        self.assertEqual(returned_call, item)
        self.assertNotIn('namespace', returned_call)
        tool_output = continued['input'][-1]
        self.assertEqual((tool_output['type'], tool_output['call_id']), ('function_call_output', item['call_id']))
        calculated = json.loads(tool_output['output'])
        self.assertEqual(calculated['payroll']['net'], format(payroll.net, '.2f'))
        self.assertEqual(calculated['payroll']['deductions'], '700.00')
        self.assertEqual(calculated['forecast']['total'], '12.34')
        self.assertEqual(calculated['forecast']['count'], 1)
        self.assertEqual(calculated['budget'], {'net_income': '4273.39', 'registered_expenses': '12.34',
            'additional_expenses': '0.00', 'remaining': '4261.05'})
        self.assertTrue(calculated['complete'])
        self.assertIs(calculated['saved'], False)
        for request in requests:
            self.assertIs(request['store'], False)
            self.assertIs(request['stream'], True)
            self.assertNotIn('previous_response_id', request)
        run.refresh_from_db()
        self.assertEqual(run.status, GenerationRun.Status.COMPLETED)
        self.assertTrue(run.context_references['financial_tools_available'])
        self.assertEqual(run.output_message.content, answer)
        self.assertEqual(ActionProposal.objects.count(), 0)
        self.assertEqual(financial_state(), original)
        self.assertEqual(ProviderConnection.objects.filter(pk=self.account.pk).values().get(), preference)
        writes = [row['sql'] for row in queries if row['sql'].lstrip().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertTrue(writes)
        # Completion also issues the shared proposal-link UPDATE; this pure
        # simulation has no proposal rows, as independently asserted above.
        self.assertTrue(all(any(table in sql for table in ('assistant_conversation', 'assistant_message',
                              'assistant_generationrun', 'assistant_actionproposal')) for sql in writes), writes)
        self.assertFalse((Path(self.private.name) / 'private').exists())

    def test_repeated_uuid_replays_without_another_provider_call_and_conflicts_cannot_change_input(self):
        request = self.data()
        self.events(self.send(request))
        replay = self.events(self.send(request))
        self.assertEqual([kind for kind, _ in replay], ['meta', 'text', 'done'])
        self.assertEqual(len(self.provider.requests), 1)
        self.assertEqual(Message.objects.filter(conversation=self.conversation).count(), 2)
        conflict = self.send({**request, 'content': 'Changed question'})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['error'], 'request_conflict')

    def test_replay_rechecks_session_before_exposing_saved_text(self):
        request = self.data()
        self.events(self.send(request))
        response = self.send(request)
        iterator = iter(response.streaming_content)
        next(iterator)
        self.client.logout()
        remaining = b''.join(iterator).decode()
        self.assertIn('cancelled', remaining)
        self.assertNotIn('Synthetic answer', remaining)

    def test_stale_interrupted_run_does_not_permanently_occupy_conversation(self):
        first = self.data()
        abandoned = self.send(first)
        GenerationRun.objects.filter(pk=first['request_id']).update(
            created_at=timezone.now() - timedelta(seconds=chat.MAX_RUN_SECONDS + 1))
        self.events(self.send(self.data(content='New deliberate retry')))
        stale = GenerationRun.objects.get(pk=first['request_id'])
        self.assertEqual(stale.status, 'failed')
        self.assertEqual(stale.error_code, 'interrupted')
        abandoned.close()

    def test_concurrent_or_duplicate_running_send_has_one_run_and_one_input(self):
        request = self.data()
        pending = self.send(request)
        duplicate = self.send(request)
        another = self.send(self.data())
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(another.status_code, 409)
        self.assertEqual(GenerationRun.objects.count(), 1)
        self.assertEqual(Message.objects.filter(conversation=self.conversation).count(), 1)
        self.assertEqual(self.provider.requests, [])
        pending.close()
        self.assertEqual(GenerationRun.objects.get().status, GenerationRun.Status.CANCELLED)
        self.assertEqual(self.provider.requests, [])

    def test_partial_failure_is_labelled_and_new_uuid_retry_excludes_failed_history(self):
        self.provider.events = [ProviderEvent('text', text='Partial fixture'), RuntimeError('SECRET TRANSPORT')]
        request = self.data()
        events = self.events(self.send(request))
        self.assertEqual(events[-1][0], 'error')
        self.assertNotIn('SECRET', repr(events))
        failed = GenerationRun.objects.get(pk=request['request_id'])
        self.assertEqual(failed.status, GenerationRun.Status.FAILED)
        self.assertEqual(failed.output_message.content, 'Partial fixture')
        page = self.client.get(reverse('assistant:detail', args=[self.conversation.pk]))
        self.assertTrue(all(message.generation_status == 'failed' for message in page.context['chat_messages']))
        self.provider.events = [ProviderEvent('text', text='Successful retry'), ProviderEvent('done')]
        self.events(self.send(self.data(content='Retry question')))
        self.assertEqual([turn.content for turn in self.provider.requests[-1].history], ['Retry question'])

    def test_history_preserves_nineteen_completed_turns_and_bounds_each_to_four_thousand(self):
        Message.objects.bulk_create([Message(conversation=self.conversation, role='assistant',
                                             content=f'Legacy {number} ' + 'x' * 5000) for number in range(25)])
        self.events(self.send())
        history = self.provider.requests[0].history
        self.assertEqual(len(history), 20)
        self.assertTrue(history[0].content.startswith('Legacy 6 '))
        self.assertTrue(all(len(turn.content) <= 4000 for turn in history))

    def test_cancel_after_chunk_preserves_partial_and_closes_provider(self):
        self.provider.events = [ProviderEvent('text', text='First part'), ProviderEvent('text', text='Never shown'), ProviderEvent('done')]
        request = self.data()
        response = self.send(request)
        iterator = iter(response.streaming_content)
        next(iterator)
        next(iterator)
        cancelled = self.client.post(reverse('assistant:cancel-run', args=[request['request_id']]), HTTP_ACCEPT='application/json')
        self.assertEqual(cancelled.json()['status'], 'cancelled')
        remaining = b''.join(iterator).decode()
        self.assertIn('cancelled', remaining)
        self.assertNotIn('Never shown', remaining)
        run = GenerationRun.objects.get(pk=request['request_id'])
        self.assertEqual(run.status, 'cancelled')
        self.assertEqual(run.output_message.content, 'First part')
        self.assertEqual(self.provider.closed, 1)

    def test_aborted_response_preserves_partial_and_logout_prevents_next_chunk(self):
        request = self.data()
        response = self.send(request)
        iterator = iter(response.streaming_content)
        next(iterator)
        next(iterator)
        response.close()
        run = GenerationRun.objects.get(pk=request['request_id'])
        self.assertEqual(run.status, 'cancelled')
        self.assertEqual(run.output_message.content, 'Synthetic answer.')
        response = self.send(self.data())
        iterator = iter(response.streaming_content)
        next(iterator)
        self.client.logout()
        self.assertIn('cancelled', b''.join(iterator).decode())

    def test_switching_active_account_or_changing_session_cancels_without_next_text(self):
        request = self.data()
        response = self.send(request)
        iterator = iter(response.streaming_content)
        next(iterator)
        ProviderConnection.objects.filter(pk=self.account.pk).update(is_active=False)
        self.assertIn('cancelled', b''.join(iterator).decode())
        self.assertEqual(self.provider.requests, [])

    def test_native_post_drains_generation_and_redirects_with_persisted_history(self):
        response = self.send(self.data(location=''), stream=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(self.conversation.pk), response['Location'])
        self.assertNotIn('model=', response['Location'])
        self.account.refresh_from_db()
        self.assertEqual(self.account.last_model_slug, 'synthetic-model')
        self.assertEqual(GenerationRun.objects.get().status, 'completed')
        self.assertEqual(self.provider.closed, 1)

    def test_cancel_post_signals_blocked_transport_in_the_serving_process(self):
        waiting, closed = Event(), Event()
        class BlockingProvider(SyntheticProvider):
            def stream(provider, request, cancellation):
                unregister = cancellation.register_close(closed.set)
                try:
                    yield ProviderEvent('text', text='Partial before wait')
                    waiting.set()
                    self.assertTrue(closed.wait(3), 'Cancel did not close blocked transport')
                    cancellation.raise_if_cancelled()
                finally:
                    unregister()
        request = self.data()
        with patch('assistant.chat.get_provider', return_value=BlockingProvider()):
            response = self.send(request)
            def consume():
                close_old_connections()
                try:
                    return b''.join(response.streaming_content).decode()
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=1) as pool:
                consumer = pool.submit(consume)
                self.assertTrue(waiting.wait(3))
                refresh = GenerationRun.refresh_from_db
                def refresh_before_transport_release(run, *args, **kwargs):
                    self.assertFalse(closed.is_set(), 'Cancellation woke the stream before its final DB read')
                    return refresh(run, *args, **kwargs)
                with patch.object(GenerationRun, 'refresh_from_db', refresh_before_transport_release):
                    cancelled = self.client.post(reverse('assistant:cancel-run', args=[request['request_id']]),
                                                 HTTP_ACCEPT='application/json')
                self.assertEqual(cancelled.status_code, 200)
                self.assertTrue(closed.is_set())
                self.assertIn('cancelled', consumer.result(timeout=3))
        self.assertEqual(GenerationRun.objects.get(pk=request['request_id']).output_message.content, 'Partial before wait')

    def test_send_new_creates_conversation_only_after_validation_and_returns_detail_metadata(self):
        count = Conversation.objects.count()
        invalid = self.client.post(reverse('assistant:send-new'), self.data(model='invented'), HTTP_ACCEPT='text/event-stream')
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(Conversation.objects.count(), count)
        response = self.client.post(reverse('assistant:send-new'), self.data(), HTTP_ACCEPT='text/event-stream')
        events = self.events(response)
        self.assertEqual(Conversation.objects.count(), count + 1)
        self.assertIn(events[0][1]['conversation_id'], events[0][1]['detail_url'])

    def test_owner_session_csrf_method_and_server_model_boundaries(self):
        self.assertEqual(self.send(conversation=self.foreign).status_code, 404)
        self.assertEqual(self.client.get(reverse('assistant:send-new')).status_code, 405)
        self.assertEqual(self.client.post(reverse('assistant:models')).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(reverse('assistant:send-new'), self.data()).status_code, 403)
        for fields in ({'model': ''}, {'model': 'invented'}, {'content': 'x' * 4001}, {'request_id': 'invalid'},
                       {'connection_id': str(uuid.uuid4())}):
            response = self.send(self.data(**fields))
            self.assertIn(response.status_code, (400, 503))
        self.assertEqual(GenerationRun.objects.count(), 0)
        request = self.data()
        response = self.send(request)
        foreign_client = Client()
        foreign_client.force_login(self.other)
        self.assertEqual(foreign_client.post(reverse('assistant:cancel-run', args=[request['request_id']])).status_code, 404)
        other_session = Client()
        other_session.force_login(self.user)
        self.assertEqual(other_session.post(reverse('assistant:cancel-run', args=[request['request_id']])).status_code, 403)
        response.close()

    def test_context_is_metadata_by_default_opt_in_is_explicit_and_never_writes_finances(self):
        make_finances(self.user)
        token = sign_scope(self.user, '/dashboard/')
        with patch('assistant.context_request.collect_context', side_effect=AssertionError('No financial collection')):
            self.events(self.send(self.data(scope=token)))
        first = json.loads(self.provider.requests[0].context_json)
        self.assertNotIn('metrics', first)
        self.assertIn('current_page', first)
        with CaptureQueriesContext(connection) as queries:
            self.events(self.send(self.data(scope=token, include_context='on')))
        second = json.loads(self.provider.requests[1].context_json)
        self.assertIn('metrics', second)
        writes = [row['sql'] for row in queries if row['sql'].lstrip().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertFalse(any(any(table in sql for table in ('banking_', 'transactions_', 'investments_', 'planning_')) for sql in writes))
        run = GenerationRun.objects.order_by('-created_at').first()
        self.assertTrue(run.context_references['include_financial'])
        self.assertNotIn('metrics', run.context_references)

    def test_empty_early_eof_timeout_and_large_output_do_not_fabricate_completion(self):
        cases = [([], 'interrupted'), ([ProviderEvent('done')], 'incomplete'),
                 ([ProviderEvent('text', text='x' * 4000)] * 5 + [ProviderEvent('done')], 'limit_exceeded')]
        for events, code in cases:
            self.provider.events = events
            request = self.data()
            result = self.events(self.send(request))
            self.assertEqual(result[-1][0], 'error')
            self.assertEqual(result[-1][1]['code'], code)
            self.assertNotEqual(GenerationRun.objects.get(pk=request['request_id']).status, 'completed')
        request = self.data()
        response = self.send(request)
        with patch('assistant.chat.time.monotonic', return_value=10**12):
            result = self.events(response)
        self.assertEqual(result[-1][1]['code'], 'timeout')

    def test_disabled_inference_keeps_unavailable_no_write_and_transaction_guard(self):
        with override_settings(ASSISTANT_OPENAI_INFERENCE_ENABLED=False):
            response = self.send({'content': 'No pretend generation'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(GenerationRun.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        with transaction.atomic():
            response = self.send(self.data())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(GenerationRun.objects.count(), 0)
