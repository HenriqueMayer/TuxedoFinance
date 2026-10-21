# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from assistant.models import ActionProposal, Conversation, GenerationRun, Message
from assistant.tests.support import make_owner


def text(response):
    return b''.join(response.streaming_content).decode() if response.streaming else response.content.decode()


class AssistantExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_owner('markdown-owner')
        cls.other = make_owner('markdown-other')
        cls.conversation = Conversation.objects.create(user=cls.user, title='Owned conversation')
        cls.foreign = Conversation.objects.create(user=cls.other, title='FOREIGN PRIVATE TITLE')
        cls.message = Message.objects.create(conversation=cls.conversation, role='assistant',
            content='  **Valor**: BRL 12,34\n\n```html\n<img src=x onerror=alert(1)>\n```\nÚltima linha.  ')
        cls.foreign_message = Message.objects.create(conversation=cls.foreign, role='assistant', content='FOREIGN PRIVATE MESSAGE')

    def setUp(self):
        self.client.force_login(self.user)
        self.conversation_url = reverse('assistant:export-conversation', args=[self.conversation.pk])
        self.message_url = reverse('assistant:export-message', args=[self.conversation.pk, self.message.pk])

    def test_message_download_preserves_raw_markdown_and_private_headers_without_provider(self):
        with patch('assistant.chat.composer_state', side_effect=AssertionError('Export must not load a provider')):
            response = self.client.get(self.message_url, HTTP_ACCEPT_LANGUAGE='en')
            self.assertEqual(text(response), self.message.content)
        self.assertEqual(response['Content-Type'], 'text/markdown; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('.md', response['Content-Disposition'])
        for value in ['private', 'no-store', 'no-cache']:
            self.assertIn(value, response['Cache-Control'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['X-Tuxedo-Assistant-User'], str(self.user.pk))
        self.assertRegex(response['X-Tuxedo-Assistant-Session'], r'^[a-f0-9]{64}$')
        self.assertNotIn(self.client.session.session_key, repr(dict(response.headers)))

    def test_full_conversation_exceeds_display_limit_and_uses_request_start_upper_key(self):
        Message.objects.bulk_create([Message(conversation=self.conversation, role='user', content=f'History item {index:03d}')
                                     for index in range(207)])
        response = self.client.get(self.conversation_url, HTTP_ACCEPT_LANGUAGE='en')
        Message.objects.create(conversation=self.conversation, role='user', content='LATER REQUEST SHOULD NOT APPEAR')
        markdown = text(response)
        self.assertIn(self.message.content, markdown)
        positions = [markdown.index(f'History item {index:03d}') for index in range(207)]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('LATER REQUEST SHOULD NOT APPEAR', markdown)
        self.assertEqual(markdown.count('## You\n'), 207)

    def test_every_export_requires_conversation_and_message_ownership(self):
        for url in [reverse('assistant:export-conversation', args=[self.foreign.pk]),
                    reverse('assistant:export-message', args=[self.foreign.pk, self.foreign_message.pk]),
                    reverse('assistant:export-message', args=[self.conversation.pk, self.foreign_message.pk])]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('FOREIGN PRIVATE', text(response))
        self.client.logout()
        for url in [self.conversation_url, self.message_url]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertNotIn(self.message.content, text(response))

    def test_head_authorization_has_no_transcript_and_session_binding_changes(self):
        first = self.client.head(self.conversation_url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.content, b'')
        another = Client()
        another.force_login(self.user)
        second = another.head(self.conversation_url)
        self.assertNotEqual(first['X-Tuxedo-Assistant-Session'], second['X-Tuxedo-Assistant-Session'])
        self.assertEqual(self.client.post(self.conversation_url).status_code, 405)
        self.assertEqual(self.client.post(self.message_url).status_code, 405)

    def run_for_message(self, status='completed'):
        incoming = Message.objects.create(conversation=self.conversation, role='user', content='Synthetic request')
        return GenerationRun.objects.create(conversation=self.conversation, input_message=incoming,
            output_message=self.message, model_slug='synthetic', session_digest='not-exported', status=status,
            context_references={'references': [{'label': 'Own [account]', 'url': '/banking/'},
                {'label': 'External forged source', 'url': 'https://example.test/secret'}],
                'notes': 'PRIVATE CONTEXT MUST NOT BE EXPORTED'})

    def test_completed_references_and_action_summary_are_scoped_and_safe(self):
        run = self.run_for_message()
        ActionProposal.objects.create(conversation=self.conversation, message=self.message, generation_run=run,
            session_digest='private-session', name='transaction.create', parameters={'secret': 'NEVER EXPORT PARAMETERS'},
            summary=[{'label': 'Amount', 'value': 'BRL 12.34'}], dependency_digest='hidden',
            status='executed', result={'url': '/transactions/123/edit/'}, expires_at=timezone.now() + timedelta(minutes=10))
        markdown = text(self.client.get(self.message_url, HTTP_ACCEPT_LANGUAGE='en'))
        self.assertTrue(markdown.startswith(self.message.content))
        self.assertIn('[Own \\[account\\]](</banking/>)', markdown)
        self.assertIn('### Proposed action — Completed', markdown)
        self.assertIn('**Amount:** BRL 12.34', markdown)
        self.assertIn('[View saved record](</transactions/123/edit/>)', markdown)
        for private in ['PRIVATE CONTEXT', 'NEVER EXPORT PARAMETERS', 'private-session', 'https://example.test/secret', 'hidden']:
            self.assertNotIn(private, markdown)

    def test_partial_reply_retains_status_but_no_action_or_reference_claims(self):
        run = self.run_for_message('cancelled')
        ActionProposal.objects.create(conversation=self.conversation, message=self.message, generation_run=run,
            session_digest='private', name='goal.create', summary=[{'label': 'SECRET SUMMARY', 'value': 'hidden'}],
            dependency_digest='hidden', expires_at=timezone.now() + timedelta(minutes=10))
        markdown = text(self.client.get(self.message_url, HTTP_ACCEPT_LANGUAGE='en'))
        self.assertIn('Partial response · Stopped', markdown)
        self.assertNotIn('SECRET SUMMARY', markdown)
        self.assertNotIn('References', markdown)

    def test_exports_read_only_chat_storage_and_deleted_conversations_stay_gone(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.conversation_url)
            text(response)
        sql = '\n'.join(query['sql'].lower() for query in queries)
        for table in ['banking_', 'transactions_', 'planning_', 'investments_']:
            self.assertNotIn(table, sql)
        self.conversation.delete()
        self.assertEqual(self.client.get(self.conversation_url).status_code, 404)
        self.assertEqual(self.client.get(self.message_url).status_code, 404)
