# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owner-scoped local chat preferences; catalogue fixtures never use a live account."""
from unittest.mock import patch
import uuid

from django.core.cache import cache
from django.db import DatabaseError, connection
from django.http import QueryDict
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from assistant.models import Conversation, GenerationRun, Message, ProviderConnection
from assistant.providers.base import ProviderEvent
from assistant.tests.support import make_owner


MODELS = [
    {'slug': 'synthetic-model', 'display_name': 'Synthetic model', 'reasoning_efforts': ['low', 'high']},
    {'slug': 'another-model', 'display_name': 'Another model', 'reasoning_efforts': []},
]


def cache_catalogue(account, models=MODELS):
    cache.set(f'assistant.models.v2:{account.user_id}:{account.pk}:{account.updated_at.isoformat()}', models, 120)


def make_connection(user, subject, **fields):
    return ProviderConnection.objects.create(
        user=user, issuer='https://auth.openai.com', subject=subject, client_id='synthetic-registration',
        scopes=['chatgpt.tokens.use.direct', 'resource.invoke'], status=ProviderConnection.Status.READY,
        **fields)


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
class ChatPreferencesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user, cls.other = make_owner('preference-owner'), make_owner('preference-other')
        cls.account = make_connection(cls.user, 'synthetic-owner', is_active=True)
        cls.second = make_connection(cls.user, 'synthetic-second', last_model_slug='another-model')
        cls.foreign = make_connection(cls.other, 'synthetic-foreign', is_active=True,
                                      last_model_slug='another-model')

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        cache_catalogue(self.account)
        cache_catalogue(self.foreign)
        self.client.force_login(self.user)
        self.path = reverse('assistant:preferences')
        self.provider = patch('assistant.chat.get_provider', side_effect=AssertionError('No external request'))
        self.provider.start()
        self.addCleanup(self.provider.stop)

    def data(self, **changes):
        return {'connection_id': str(self.account.pk), 'model': 'synthetic-model', 'reasoning_effort': 'high',
                **changes}

    def assert_saved(self, model='', effort='', account=None):
        account = account or self.account
        account.refresh_from_db()
        self.assertEqual((account.last_model_slug, account.last_reasoning_effort), (model, effort))

    def save(self, **changes):
        return self.client.post(self.path, self.data(**changes))

    def test_selection_is_saved_locally_for_the_owned_account_without_touching_catalogue_version(self):
        before = self.account.updated_at
        response = self.save()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.data())
        self.assertIn('private', response.headers['Cache-Control'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assert_saved('synthetic-model', 'high')
        self.assertEqual(self.account.updated_at, before)
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(Message.objects.exists())
        self.assertFalse(GenerationRun.objects.exists())

    def test_storage_failure_returns_a_private_structured_error_without_saving(self):
        with patch('assistant.views._save_chat_settings', side_effect=DatabaseError('Synthetic storage failure')):
            response = self.save()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'error': 'storage_unavailable'})
        self.assertIn('private', response.headers['Cache-Control'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertNotContains(response, 'Synthetic storage failure', status_code=503)
        self.assert_saved()
        self.assertFalse(GenerationRun.objects.exists())

    def test_last_selection_prefills_page_panel_and_new_conversation_but_never_context_consent(self):
        self.assertEqual(self.save().status_code, 200)
        for headers in [{}, {'HTTP_X_TUXEDO_ASSISTANT': 'panel'}]:
            with self.subTest(headers=headers):
                response = self.client.get(reverse('assistant:index'), **headers)
                self.assertEqual(response.context['selected_model'], 'synthetic-model')
                self.assertEqual(response.context['selected_reasoning_effort'], 'high')
                self.assertEqual(response.context['send_form'].initial['model'], 'synthetic-model')
                self.assertEqual(response.context['send_form'].initial['reasoning_effort'], 'high')
                self.assertFalse(response.context['send_form'].initial.get('include_context', False))
        created = self.client.post(reverse('assistant:create'), {'title': 'Another local chat'})
        following = self.client.get(created.url)
        self.assertEqual(following.context['selected_model'], 'synthetic-model')
        self.assertEqual(following.context['selected_reasoning_effort'], 'high')

    def test_explicit_model_default_and_explicit_clear_are_saved(self):
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(self.save(reasoning_effort='').status_code, 200)
        self.assert_saved('synthetic-model')
        self.assertEqual(self.save(model='', reasoning_effort='').status_code, 200)
        self.assert_saved()
        response = self.client.get(reverse('assistant:index'))
        self.assertEqual(response.context['selected_model'], '')
        self.assertEqual(response.context['selected_reasoning_effort'], '')

    def test_explicit_get_choices_and_empty_values_override_saved_defaults_without_mutation(self):
        self.save()
        for params, model, effort in [({'model': 'another-model'}, 'another-model', ''),
                                      ({'model': '', 'reasoning_effort': ''}, '', ''),
                                      ({'model': 'synthetic-model', 'reasoning_effort': 'low'},
                                       'synthetic-model', 'low')]:
            with self.subTest(params=params):
                response = self.client.get(reverse('assistant:index'), params)
                self.assertEqual(response.context['selected_model'], model)
                self.assertEqual(response.context['selected_reasoning_effort'], effort)
                self.assert_saved('synthetic-model', 'high')

    def test_bound_invalid_send_keeps_its_choices_and_does_not_save_them(self):
        self.save()
        response = self.client.post(reverse('assistant:send-new'), {
            **self.data(model='another-model', reasoning_effort=''), 'request_id': uuid.uuid4(), 'content': '',
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.context['send_form'].is_bound)
        self.assertEqual(response.context['send_form']['model'].value(), 'another-model')
        self.assertEqual(response.context['selected_model'], 'another-model')
        self.assertEqual(response.context['selected_reasoning_effort'], '')
        self.assert_saved('synthetic-model', 'high')
        self.assertFalse(GenerationRun.objects.exists())

    def test_unknown_models_unsupported_efforts_and_effort_without_model_never_save(self):
        for fields in [{'model': 'not-listed'}, {'model': 'another-model'},
                       {'reasoning_effort': 'future'}, {'model': ''}]:
            with self.subTest(fields=fields):
                self.assertEqual(self.save(**fields).status_code, 400)
                self.assert_saved()

    def test_removed_catalogue_model_or_effort_is_not_silently_reused_or_rewritten_on_get(self):
        self.save()
        cache_catalogue(self.account, [MODELS[1]])
        missing = self.client.get(reverse('assistant:index'))
        self.assertEqual(missing.context['selected_model'], '')
        self.assertEqual(missing.context['selected_reasoning_effort'], '')
        self.assertEqual(self.save().status_code, 400)
        self.assert_saved('synthetic-model', 'high')
        cache_catalogue(self.account, [{**MODELS[0], 'reasoning_efforts': ['low']}])
        narrowed = self.client.get(reverse('assistant:index'))
        self.assertEqual(narrowed.context['selected_model'], 'synthetic-model')
        self.assertEqual(narrowed.context['selected_reasoning_effort'], '')
        self.assertEqual(self.save().status_code, 400)
        self.assert_saved('synthetic-model', 'high')

    def test_foreign_inactive_and_unknown_connections_are_rejected_without_changes(self):
        for identifier in [self.foreign.pk, self.second.pk, uuid.uuid4()]:
            with self.subTest(identifier=identifier):
                response = self.save(connection_id=str(identifier))
                self.assertEqual(response.status_code, 409)
                self.assert_saved()
                self.assert_saved('another-model', account=self.second)
                self.assert_saved('another-model', account=self.foreign)

    def test_account_switch_and_user_switch_keep_preferences_separate(self):
        self.save()
        ProviderConnection.objects.filter(pk=self.account.pk).update(is_active=False)
        ProviderConnection.objects.filter(pk=self.second.pk).update(is_active=True)
        cache_catalogue(self.second)
        self.assertEqual(self.save().status_code, 409)
        switched = self.client.get(reverse('assistant:index'))
        self.assertEqual(switched.context['selected_model'], 'another-model')
        self.assertEqual(switched.context['selected_reasoning_effort'], '')
        self.client.force_login(self.other)
        self.assertEqual(self.save().status_code, 409)
        foreign = self.client.get(reverse('assistant:index'))
        self.assertEqual(foreign.context['selected_model'], 'another-model')
        self.assertEqual(foreign.context['selected_reasoning_effort'], '')
        self.assert_saved('synthetic-model', 'high')

    def test_disabled_or_ineligible_account_never_saves_or_resolves_a_provider(self):
        for flag in ['ASSISTANT_OPENAI_AUTH_ENABLED', 'ASSISTANT_OPENAI_INFERENCE_ENABLED']:
            with self.subTest(flag=flag), override_settings(**{flag: False}), \
                    patch('assistant.chat.get_provider') as provider:
                response = self.save()
                self.assertEqual(response.status_code, 503)
                page = self.client.get(reverse('assistant:index'))
                self.assertEqual(page.context['selected_model'], '')
                provider.assert_not_called()
                self.assert_saved()
        self.account.status = ProviderConnection.Status.RECONNECT
        self.account.save(update_fields=['status'])
        self.assertEqual(self.save().status_code, 503)
        self.assert_saved()

    def test_authentication_post_only_and_csrf_boundaries(self):
        self.assertEqual(self.client.get(self.path).status_code, 405)
        self.client.logout()
        self.assertEqual(self.save().status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(self.path, self.data()).status_code, 403)
        csrf.get(reverse('assistant:index'))
        response = csrf.post(self.path, {**self.data(), 'csrfmiddlewaretoken': csrf.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 200)

    def test_missing_duplicated_and_unrelated_fields_do_not_change_settings(self):
        for fields in [{}, self.data(connection_id='invalid'), self.data(include_context='on'),
                       {key: value for key, value in self.data().items() if key != 'model'},
                       {key: value for key, value in self.data().items() if key != 'reasoning_effort'}]:
            with self.subTest(fields=fields):
                self.assertEqual(self.client.post(self.path, fields).status_code, 400)
                self.assert_saved()
        duplicate = QueryDict('', mutable=True)
        duplicate.update(self.data())
        duplicate.appendlist('model', 'another-model')
        response = self.client.post(self.path, duplicate.urlencode(), content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 400)
        self.assert_saved()


class PreferenceSyntheticProvider:
    available = True

    def __init__(self):
        self.requests = []

    def list_models(self):
        assert not connection.in_atomic_block
        return MODELS

    def stream(self, request, cancellation):
        assert not connection.in_atomic_block
        self.requests.append(request)
        yield ProviderEvent('text', text='Synthetic answer.')
        yield ProviderEvent('done')


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
class AcceptedSendPreferencesTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = make_owner('send-preference-owner')
        self.client.force_login(self.user)
        self.account = make_connection(self.user, 'synthetic-send', is_active=True)
        self.provider = PreferenceSyntheticProvider()
        fake = patch('assistant.chat.get_provider', return_value=self.provider)
        fake.start()
        self.addCleanup(fake.stop)
        network = patch('assistant.providers.openai.HTTPTransport.__call__',
                        side_effect=AssertionError('No external request'))
        network.start()
        self.addCleanup(network.stop)

    def send(self, *, effort='high', streaming=False, **changes):
        return self.client.post(reverse('assistant:send-new'), {
            'content': 'Synthetic question.', 'model': 'synthetic-model', 'reasoning_effort': effort,
            'connection_id': self.account.pk, 'request_id': uuid.uuid4(), **changes,
        }, HTTP_ACCEPT='text/event-stream' if streaming else 'text/html')

    def test_native_send_saves_the_validated_pair_and_next_page_uses_it(self):
        before = self.account.updated_at
        response = self.send()
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual((self.account.last_model_slug, self.account.last_reasoning_effort),
                         ('synthetic-model', 'high'))
        self.assertEqual(self.account.updated_at, before)
        self.assertEqual(self.provider.requests[0].reasoning_effort, 'high')
        following = self.client.get(reverse('assistant:index'))
        self.assertEqual(following.context['selected_model'], 'synthetic-model')
        self.assertEqual(following.context['selected_reasoning_effort'], 'high')
        self.assertFalse(following.context['send_form'].initial.get('include_context', False))

    def test_stream_acceptance_saves_model_default_without_waiting_for_output(self):
        response = self.send(effort='', streaming=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertEqual(self.provider.requests, [])
        self.account.refresh_from_db()
        self.assertEqual((self.account.last_model_slug, self.account.last_reasoning_effort), ('synthetic-model', ''))
        output = b''.join(response.streaming_content)
        self.assertIn(b'Synthetic answer.', output)
        self.assertEqual(len(self.provider.requests), 1)

    def test_native_accepted_send_completes_when_the_optional_settings_write_fails(self):
        with patch('assistant.views._save_chat_settings', side_effect=DatabaseError('Synthetic storage failure')):
            response = self.send()
        self.assertEqual(response.status_code, 302)
        run = GenerationRun.objects.get()
        self.assertEqual(run.status, GenerationRun.Status.COMPLETED)
        self.assertEqual(run.output_message.content, 'Synthetic answer.')
        self.assertEqual(len(self.provider.requests), 1)
        self.account.refresh_from_db()
        self.assertEqual((self.account.last_model_slug, self.account.last_reasoning_effort), ('', ''))

    def test_streamed_accepted_send_completes_when_the_optional_settings_write_fails(self):
        with patch('assistant.views._save_chat_settings', side_effect=DatabaseError('Synthetic storage failure')):
            response = self.send(streaming=True)
        self.assertEqual(response.status_code, 200)
        output = b''.join(response.streaming_content)
        self.assertIn(b'Synthetic answer.', output)
        run = GenerationRun.objects.get()
        self.assertEqual(run.status, GenerationRun.Status.COMPLETED)
        self.assertEqual(run.output_message.content, 'Synthetic answer.')
        self.assertEqual(len(self.provider.requests), 1)
        self.account.refresh_from_db()
        self.assertEqual((self.account.last_model_slug, self.account.last_reasoning_effort), ('', ''))

    def test_rejected_context_does_not_update_previous_choices(self):
        self.account.last_model_slug = 'another-model'
        self.account.save(update_fields=['last_model_slug'])
        response = self.send(scope='invalid-signed-scope')
        self.assertEqual(response.status_code, 400)
        self.account.refresh_from_db()
        self.assertEqual(self.account.last_model_slug, 'another-model')
        self.assertEqual(self.account.last_reasoning_effort, '')
        self.assertFalse(GenerationRun.objects.exists())
        self.assertEqual(self.provider.requests, [])
