# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from assistant.context import read_scope, sign_scope
from assistant.models import Conversation, Message
from assistant.tests.support import make_finances, make_owner
from banking.models import BankMovement
from transactions.models import Transaction
from core.currencies import get_currency


class AssistantViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_owner('view-owner')
        cls.other = make_owner('view-other')
        cls.bank, cls.account, cls.category, cls.item = make_finances(cls.user)
        cls.conversation = Conversation.objects.create(user=cls.user, title='Local owner conversation')
        cls.foreign = Conversation.objects.create(user=cls.other, title='SECRET FOREIGN CONVERSATION')
        Message.objects.create(conversation=cls.foreign, role='user', content='SECRET FOREIGN MESSAGE')

    def setUp(self):
        self.client.force_login(self.user)

    def assert_private(self, response):
        cache = response.headers['Cache-Control']
        self.assertIn('private', cache)
        self.assertIn('no-store', cache)
        self.assertIn('no-cache', cache)

    def test_anonymous_access_requires_authentication_even_for_fragment_and_context(self):
        self.client.logout()
        for path in [reverse('assistant:index'), reverse('assistant:detail', args=[self.conversation.pk]),
                     reverse('assistant:context')]:
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_X_TUXEDO_ASSISTANT='panel')
                self.assertEqual(response.status_code, 302)
                self.assertIn('/accounts/login/', response.url)
                self.assert_private(response)

    def test_full_page_and_fragment_contract_and_neutral_direct_entry(self):
        full = self.client.get(reverse('assistant:index'))
        self.assertEqual(full.status_code, 200)
        self.assertTemplateUsed(full, 'assistant/index.html')
        self.assertIsNone(full.context['context_snapshot'])
        self.assertEqual(full.context['scope'], '')
        self.assertEqual(full.context['provider_state'], 'disconnected')
        self.assert_private(full)
        fragment = self.client.get(reverse('assistant:index'), HTTP_X_TUXEDO_ASSISTANT='panel')
        self.assertTemplateUsed(fragment, 'assistant/_content.html')
        self.assertTemplateNotUsed(fragment, 'assistant/index.html')
        self.assertContains(fragment, f'data-assistant-user="{self.user.pk}"')
        self.assertContains(fragment, 'csrfmiddlewaretoken')
        self.assertNotContains(fragment, 'SECRET FOREIGN')
        self.assertIn('X-Tuxedo-Assistant', fragment.headers['Vary'])
        self.assert_private(fragment)

    def test_conversation_prg_creation_deletion_cascade_and_financial_preservation(self):
        token = sign_scope(self.user, '/transactions/')
        created = self.client.post(reverse('assistant:create'), {'scope': token})
        self.assertEqual(created.status_code, 302)
        conversation = Conversation.objects.filter(user=self.user).exclude(pk=self.conversation.pk).get()
        self.assertEqual(conversation.title, '')
        self.assertIn(str(conversation.pk), created.url)
        self.assertIn('scope=', created.url)
        Message.objects.create(conversation=conversation, role='user', content='Synthetic local note')
        deleted = self.client.post(reverse('assistant:delete', args=[conversation.pk]), {'scope': token})
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(Conversation.objects.filter(pk=conversation.pk).exists())
        self.assertFalse(Message.objects.filter(conversation_id=conversation.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 1)

    def test_context_money_uses_shared_financial_format_without_changing_canonical_values(self):
        token = sign_scope(self.user, '/dashboard/')
        instant = datetime(2026, 10, 18, 12, tzinfo=datetime_timezone.utc)
        # Number separators follow the configured default currency throughout
        # the app; changing the UI language does not change financial notation.
        visible = 'BRL 87' + get_currency(settings.DEFAULT_CURRENCY).decimal_separator + '66'
        for language in ['en', 'pt-br']:
            with self.subTest(language=language), patch('assistant.context.timezone.now', return_value=instant):
                response = self.client.get(reverse('assistant:index'), {'scope': token},
                                           HTTP_X_TUXEDO_ASSISTANT='panel', HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, visible)
                self.assertEqual(response.context['context_snapshot']['metrics'][0]['value'], '87.66')
                self.assertEqual(response.context['context_captured_at'], instant)
                self.assertEqual(response.context['context_cutoff'].isoformat(),
                                 response.context['context_snapshot']['cutoff'])
                self.assertContains(response, '<time datetime="2026-10-18T12:00:00+00:00">')

    def test_panel_owner_identifiers_stay_unlocalized_above_999(self):
        owner = self.user.__class__.objects.create_user(pk=2001, username='high-id-owner', password='local-test-only')
        self.client.force_login(owner)
        # Both halves of the session check must use the same machine identity,
        # regardless of translated number grouping in visible financial values.
        with self.settings(USE_THOUSAND_SEPARATOR=True):
            for language in ['en', 'pt-br']:
                with self.subTest(language=language):
                    workspace = self.client.get(reverse('banking:list'), HTTP_ACCEPT_LANGUAGE=language)
                    fragment = self.client.get(reverse('assistant:index'),
                                               HTTP_X_TUXEDO_ASSISTANT='panel', HTTP_ACCEPT_LANGUAGE=language)
                    self.assertContains(workspace, 'data-assistant-user="2001"')
                    self.assertContains(fragment, 'data-assistant-user="2001"')

    def test_ownership_and_method_boundaries(self):
        for name, method in [('assistant:detail', 'get'), ('assistant:delete', 'post'), ('assistant:send', 'post')]:
            with self.subTest(name=name):
                response = getattr(self.client, method)(reverse(name, args=[self.foreign.pk]), HTTP_X_TUXEDO_ASSISTANT='panel')
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, 'SECRET FOREIGN', status_code=404)
        for name in ['assistant:create', 'assistant:delete', 'assistant:send']:
            path = reverse(name, args=[self.conversation.pk] if name != 'assistant:create' else [])
            self.assertEqual(self.client.get(path).status_code, 405)
        self.assertEqual(self.client.post(reverse('assistant:context')).status_code, 405)
        self.assertEqual(self.client.post(reverse('assistant:index')).status_code, 405)

    def test_csrf_is_enforced_for_every_local_write_and_unavailable_send(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        for name in ['assistant:create', 'assistant:delete', 'assistant:send']:
            path = reverse(name, args=[self.conversation.pk] if name != 'assistant:create' else [])
            self.assertEqual(csrf_client.post(path).status_code, 403)
        csrf_client.get(reverse('assistant:index'), HTTP_X_TUXEDO_ASSISTANT='panel')
        response = csrf_client.post(reverse('assistant:create'), {'csrfmiddlewaretoken': csrf_client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)

    def test_unavailable_send_does_not_persist_a_user_message_answer_or_financial_change(self):
        before = self.conversation.updated_at
        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(reverse('assistant:send', args=[self.conversation.pk]),
                                        {'content': 'Do not pretend to send this'}, HTTP_X_TUXEDO_ASSISTANT='panel')
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, 'No message was sent or saved', status_code=503)
        self.assertFalse(self.conversation.messages.exists())
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.updated_at, before)
        writes = [query['sql'] for query in queries if query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writes, [])
        self.assert_private(response)

    def test_history_paginated_without_foreign_conversations_and_text_escaped(self):
        Conversation.objects.bulk_create([Conversation(user=self.user, title=f'History {number}') for number in range(31)])
        Message.objects.create(conversation=self.conversation, role='user', content='<script>private()</script>')
        response = self.client.get(reverse('assistant:detail', args=[self.conversation.pk]), {'page': '2'}, HTTP_X_TUXEDO_ASSISTANT='panel')
        self.assertEqual(response.context['history_page'].paginator.count, 32)
        self.assertEqual(len(response.context['conversations']), 2)
        self.assertTrue(response.context['history_page'].has_previous())
        self.assertContains(response, '&lt;script&gt;private()&lt;/script&gt;')
        self.assertNotContains(response, '<script>private()</script>')
        self.assertNotContains(response, 'SECRET FOREIGN')

    def test_transcript_bound_is_explicit_and_uses_latest_messages(self):
        Message.objects.bulk_create([Message(conversation=self.conversation, role='user', content=f'Fixture {number}')
                                     for number in range(201)])
        response = self.client.get(reverse('assistant:detail', args=[self.conversation.pk]), HTTP_X_TUXEDO_ASSISTANT='panel')
        self.assertEqual(len(response.context['chat_messages']), 200)
        self.assertContains(response, 'Only the latest 200 messages are displayed.')

    def test_bad_scope_never_creates_deletes_or_broadens_and_send_stays_unavailable(self):
        count = Conversation.objects.count()
        response = self.client.post(reverse('assistant:create'), {'scope': 'tampered'}, HTTP_X_TUXEDO_ASSISTANT='panel')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Conversation.objects.count(), count)
        self.assertIsNone(response.context['context_snapshot'])
        response = self.client.post(reverse('assistant:delete', args=[self.conversation.pk]), {'scope': 'tampered'})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Conversation.objects.filter(pk=self.conversation.pk).exists())
        response = self.client.post(reverse('assistant:send', args=[self.conversation.pk]), {'scope': 'tampered'})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.conversation.messages.exists())

    def test_context_endpoint_requires_valid_owner_scope_and_refreshed_location_is_signed(self):
        path = reverse('assistant:context')
        self.assertEqual(self.client.get(path).status_code, 400)
        token = sign_scope(self.user, '/dashboard/')
        response = self.client.get(path, {'scope': token, 'location': '/transactions/?month=2026-10'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(read_scope(self.user, data['scope'])['filters'], {'month': '2026-10'})
        self.assertEqual(data['context_snapshot']['metrics'], [])
        self.assert_private(response)
        for params in [{'scope': token, 'location': 'https://example.com/'},
                       {'location': '/dashboard/'}, {'scope': sign_scope(self.other, '/dashboard/')},
                       {'scope': token, 'location': f'/transactions/{self.item.pk}/delete/'}]:
            with self.subTest(params=params):
                invalid = self.client.get(path, params)
                self.assertEqual(invalid.status_code, 400)
                self.assertIsNone(invalid.json()['context_snapshot'])
