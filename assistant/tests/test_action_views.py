# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assistant import action_service
from assistant.context import sign_scope
from assistant.models import ActionProposal, Conversation, GenerationRun, Message
from assistant.tests.support import make_finances, make_owner
from transactions.models import Transaction


class ActionViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_owner('action-http-owner')
        cls.other = make_owner('action-http-other')
        cls.bank, cls.account, cls.category, cls.item = make_finances(cls.user)

    def setUp(self):
        self.client.force_login(self.user)
        self.conversation = Conversation.objects.create(user=self.user, title='Owned review')
        self.input = Message.objects.create(conversation=self.conversation, role='user', content='Prepare a synthetic purchase')
        self.output = Message.objects.create(conversation=self.conversation, role='assistant', content='Review **before** saving.')
        self.run = GenerationRun.objects.create(conversation=self.conversation, input_message=self.input,
            output_message=self.output, status='completed', model_slug='offline',
            session_digest=action_service._session_digest(self.user, self.client.session.session_key, generation=True))
        self.proposal = action_service.prepare_action(self.user, self.client.session.session_key,
            self.conversation, 'transaction.create', {'title': 'Synthetic reviewed purchase', 'amount': '15.00',
                'currency': 'BRL', 'date': '2026-10-20', 'transaction_type': 'EXPENSE',
                'category_id': self.category.pk, 'account_id': self.account.pk}, run_id=self.run.pk)
        self.proposal.message = self.output
        self.proposal.save(update_fields=['message'])
        self.confirm = reverse('assistant:action-confirm', args=[self.proposal.pk])
        self.cancel = reverse('assistant:action-cancel', args=[self.proposal.pk])
        self.detail = reverse('assistant:detail', args=[self.conversation.pk])

    def test_completed_owned_proposal_has_native_forms_with_no_client_parameters(self):
        response = self.client.get(self.detail, HTTP_ACCEPT_LANGUAGE='en')
        self.assertContains(response, 'Confirm action')
        self.assertContains(response, 'Discard')
        self.assertContains(response, 'Synthetic reviewed purchase')
        self.assertContains(response, self.confirm)
        self.assertNotContains(response, 'name="parameters"')
        self.assertNotContains(response, 'name="account_id"')
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_explicit_native_confirmation_is_idempotent_and_preserves_scope(self):
        token = sign_scope(self.user, '/transactions/')
        first = self.client.post(self.confirm, {'scope': token}, follow=True, HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(first.status_code, 200)
        self.assertContains(first, 'View saved record')
        self.assertNotContains(first, 'Confirm action')
        self.assertIn('scope=', first.redirect_chain[0][0])
        self.assertEqual(Transaction.objects.filter(user=self.user, title='Synthetic reviewed purchase').count(), 1)
        self.client.post(self.confirm)
        self.assertEqual(Transaction.objects.filter(user=self.user, title='Synthetic reviewed purchase').count(), 1)

    def test_cancel_is_native_idempotent_and_never_writes_finances(self):
        for _ in range(2):
            response = self.client.post(self.cancel, follow=True, HTTP_ACCEPT_LANGUAGE='en')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Discarded')
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)
        self.assertEqual(self.client.post(self.confirm).status_code, 409)

    def test_invalid_scope_and_extra_or_duplicate_values_cannot_execute(self):
        for data in [{'scope': 'tampered'}, {'amount': '0.01'}, {'scope': ['', '']}]:
            with self.subTest(data=data):
                response = self.client.post(self.confirm, data)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, 'pending')

    def test_foreign_anonymous_get_and_missing_csrf_cannot_execute(self):
        self.assertEqual(self.client.get(self.confirm).status_code, 405)
        self.assertEqual(self.client.get(self.cancel).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.confirm).status_code, 404)
        self.assertEqual(self.client.post(self.cancel).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.post(self.confirm).status_code, 302)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.confirm).status_code, 403)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_another_session_cannot_confirm_or_cancel_the_proposal(self):
        other_session = Client()
        other_session.force_login(self.user)
        self.assertEqual(other_session.post(self.confirm).status_code, 404)
        self.assertEqual(other_session.post(self.cancel).status_code, 404)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_failed_generation_never_exposes_confirm_controls(self):
        for status in ['running', 'failed', 'cancelled']:
            with self.subTest(status=status):
                GenerationRun.objects.filter(pk=self.run.pk).update(status=status)
                self.assertNotContains(self.client.get(self.detail), 'data-assistant-proposal=')
                self.assertEqual(self.client.post(self.confirm).status_code, 409)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_expiry_and_raw_storage_failure_recover_privately(self):
        ActionProposal.objects.filter(pk=self.proposal.pk).update(expires_at=timezone.now())
        response = self.client.post(self.confirm, HTTP_X_TUXEDO_ASSISTANT='panel', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(response.status_code, 409)
        self.assertTemplateUsed(response, 'assistant/_content.html')
        self.assertContains(response, 'This proposal expired.', status_code=409)
        with patch('assistant.action_views.action_service.cancel_action', side_effect=RuntimeError('SECRET PROVIDER DATA')):
            failed = self.client.post(self.cancel, HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(failed.status_code, 503)
        self.assertNotContains(failed, 'SECRET PROVIDER DATA', status_code=503)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_summaries_are_escaped_and_result_links_remain_local(self):
        ActionProposal.objects.filter(pk=self.proposal.pk).update(summary=[{'label': '<img src=x>', 'value': '<script>bad()</script>'}],
            status='executed', result={'url': 'https://example.test/foreign'})
        response = self.client.get(self.detail, HTTP_ACCEPT_LANGUAGE='en')
        self.assertContains(response, '&lt;script&gt;bad()&lt;/script&gt;')
        self.assertNotContains(response, '<img src=x>')
        self.assertNotContains(response, 'https://example.test/foreign')
        self.assertNotContains(response, 'View saved record')

    def test_deleted_result_names_the_list_and_keeps_projection_recovery_visible(self):
        ActionProposal.objects.filter(pk=self.proposal.pk).update(status='executed', result={
            'url': '/transactions/', 'operation': 'deleted', 'warnings': ['projection_pending']})
        response = self.client.get(self.detail, HTTP_ACCEPT_LANGUAGE='en')
        self.assertContains(response, 'View transactions')
        self.assertNotContains(response, 'View saved record')
        self.assertContains(response, 'The record changed, but financial projections need review.')
