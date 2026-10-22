# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Full local run/proposal/confirmation lifecycle without external inference."""
import json
from unittest.mock import patch
import uuid

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from assistant import chat
from assistant.models import ActionProposal, Conversation, GenerationRun, ProviderConnection
from assistant.providers.base import ProviderEvent
from assistant.tests.support import make_finances, make_owner
from assistant.tooling import financial_tools, recorded_actions
from categories.models import Category
from planning.models import FinancialGoal
from transactions.models import Transaction


class ToolProvider:
    available = True

    def __init__(self, calls, *, failed=False):
        self.calls, self.failed = calls, failed
        self.results, self.requests = [], []

    def list_models(self):
        return [{'slug': 'synthetic-tools', 'display_name': 'Synthetic tools', 'reasoning_efforts': []}]

    def stream(self, request, cancellation):
        self.requests.append(request)
        for name, arguments in self.calls:
            cancellation.raise_if_cancelled()
            assert not connection.in_atomic_block
            self.results.append(request.tool_runner(name, arguments))
        yield ProviderEvent('text', text='Review the prepared action. Nothing has been saved yet.')
        yield ProviderEvent('error', code='interrupted') if self.failed else ProviderEvent('done')


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
class LocalToolDispatchTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user = make_owner('local-tool-owner')
        self.other = make_owner('local-tool-other')
        self.client.force_login(self.user)
        self.account = ProviderConnection.objects.create(
            user=self.user, issuer='https://auth.openai.com', subject='synthetic-tool-owner',
            client_id='synthetic-tool-registration', scopes=['resource.invoke', 'chatgpt.tokens.use.direct'],
            status='ready', is_active=True)
        self.conversation = Conversation.objects.create(user=self.user)
        self.provider = ToolProvider([])
        patcher = patch('assistant.chat.get_provider', side_effect=lambda *args: self.provider)
        patcher.start()
        self.addCleanup(patcher.stop)
        network = patch('assistant.providers.openai.HTTPTransport.__call__', side_effect=AssertionError('No real inference'))
        network.start()
        self.addCleanup(network.stop)

    def send(self, **changes):
        data = {'content': 'Prepare a synthetic goal for review', 'model': 'synthetic-tools',
                'connection_id': str(self.account.pk), 'request_id': str(uuid.uuid4())} | changes
        response = self.client.post(reverse('assistant:send', args=[self.conversation.pk]), data,
                                    HTTP_ACCEPT='text/event-stream')
        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content).decode()
        return body, data

    def goal(self):
        return {'name': 'Synthetic reviewed goal', 'target_amount': '500.00', 'currency': 'BRL', 'target_date': None}

    def test_tool_prepares_only_then_confirm_saves_once_and_next_request_knows_status(self):
        self.provider = ToolProvider([('prepare_goal', self.goal()),
                                      ('prepare_goal', self.goal() | {'name': ' Synthetic reviewed goal ',
                                                                       'target_amount': '500.0'})])
        body, data = self.send()
        self.assertIn('event: done', body)
        self.assertEqual(FinancialGoal.objects.filter(user=self.user).count(), 0)
        self.assertEqual(ActionProposal.objects.count(), 1)
        proposal = ActionProposal.objects.get()
        self.assertEqual(proposal.generation_run.status, 'completed')
        self.assertEqual(proposal.message_id, proposal.generation_run.output_message_id)
        self.assertFalse(self.provider.results[0]['saved'])
        self.assertEqual(self.provider.results[0]['proposal_id'], self.provider.results[1]['proposal_id'])
        rendered = self.client.get(reverse('assistant:detail', args=[self.conversation.pk]))
        self.assertContains(rendered, 'Confirm action')
        for _ in range(2):
            self.assertEqual(self.client.post(reverse('assistant:action-confirm', args=[proposal.pk])).status_code, 302)
        self.assertEqual(FinancialGoal.objects.filter(user=self.user).count(), 1)
        result = recorded_actions(self.user, self.conversation)
        self.assertEqual(result[0]['status'], 'executed')
        self.assertTrue(result[0]['result_url'].startswith('/planning/'))
        self.assertEqual(recorded_actions(self.other, self.conversation), [])
        self.provider = ToolProvider([])
        self.send(content='What was saved?')
        context = json.loads(self.provider.requests[0].context_json)
        self.assertEqual(context['recorded_actions'][0]['status'], 'executed')
        self.assertNotIn('metrics', context)
        # Replaying the original request UUID never calls the provider again.
        self.send(**data)
        self.assertEqual(len(self.provider.requests), 1)

    def test_partial_generation_never_exposes_or_executes_its_proposal(self):
        self.provider = ToolProvider([('prepare_goal', self.goal())], failed=True)
        body, _ = self.send()
        self.assertIn('event: error', body)
        proposal = ActionProposal.objects.get()
        self.assertIsNone(proposal.message_id)
        self.assertEqual(proposal.generation_run.status, 'failed')
        rendered = self.client.get(reverse('assistant:detail', args=[self.conversation.pk]))
        self.assertNotContains(rendered, 'Confirm action')
        self.assertEqual(self.client.post(reverse('assistant:action-confirm', args=[proposal.pk])).status_code, 409)
        self.assertEqual(FinancialGoal.objects.count(), 0)

    def test_choice_lookup_is_bounded_owned_metadata_and_no_confirm_tool_exists(self):
        make_finances(self.user, 'Owned')
        make_finances(self.other, 'Foreign')
        self.provider = ToolProvider([
            ('find_choices', {'kind': 'accounts', 'query': ''}),
            ('find_choices', {'kind': 'transactions', 'query': ''}),
            ('confirm_action', {'proposal_id': str(uuid.uuid4())}),
        ])
        self.send()
        account = self.provider.results[0]['items'][0]
        self.assertIn('Owned', account['label'])
        self.assertNotIn('Foreign', json.dumps(self.provider.results))
        self.assertNotIn('balance', account)
        self.assertEqual(self.provider.results[1]['error'], 'query_required')
        self.assertEqual(self.provider.results[2]['error'], 'unsupported_action')
        self.assertEqual(ActionProposal.objects.count(), 0)
        schemas = financial_tools()
        self.assertEqual(len(schemas), 9)
        self.assertFalse(any('confirm' in tool['name'] or 'execute' in tool['name'] for tool in schemas))
        for tool in schemas:
            self.assertFalse(tool['parameters']['additionalProperties'])
            self.assertEqual(set(tool['parameters']['required']), set(tool['parameters']['properties']))
        schema = next(tool for tool in schemas if tool['name'] == 'prepare_transaction')
        self.assertEqual(schema['parameters']['properties']['installments']['maximum'], Transaction.MAX_INSTALLMENTS)

    def test_tool_callback_rechecks_session_before_any_proposal(self):
        self.provider = ToolProvider([('prepare_goal', self.goal())])
        original = self.provider.stream

        def logout_then_stream(request, cancellation):
            self.client.logout()
            yield from original(request, cancellation)

        self.provider.stream = logout_then_stream
        body, _ = self.send()
        self.assertIn('event: error', body)
        self.assertEqual(ActionProposal.objects.count(), 0)
        self.assertEqual(FinancialGoal.objects.count(), 0)
        self.assertEqual(GenerationRun.objects.get().status, 'cancelled')

    def test_categorization_review_stays_local_without_disclosing_source_notes(self):
        _bank, _account, _category, source = make_finances(self.user, 'Private source')
        source.notes = 'Private note needed only for local validation'
        source.save(update_fields=['notes'])
        category = Category.objects.create(user=self.user, name='Reviewed category', transaction_type='EXPENSE')
        self.provider = ToolProvider([('prepare_categorization', {
            'transaction_id': source.pk, 'category_id': category.pk})])
        self.send(content='Move my Private source purchase to Reviewed category')
        result = self.provider.results[0]
        self.assertEqual(result['status'], 'awaiting_confirmation')
        self.assertFalse(result['saved'])
        self.assertNotIn('summary', result)
        self.assertNotIn(source.notes, json.dumps(result))
        proposal = ActionProposal.objects.get()
        self.assertIn(source.notes, json.dumps(proposal.summary))
        rendered = self.client.get(reverse('assistant:detail', args=[self.conversation.pk]))
        self.assertContains(rendered, source.notes)
        source.refresh_from_db()
        self.assertEqual(source.category_id, _category.pk)

    def test_default_access_reads_other_workspaces_and_runs_a_real_local_simulation(self):
        from banking.models import BankMovement
        from planning.models import CategoryBudget
        _bank, _account, _category, source = make_finances(self.user, 'Owned scenario')
        make_finances(self.other, 'Foreign scenario')
        self.provider = ToolProvider([
            ('read_financial_data', {'area': 'planning', 'month': '2026-10', 'query': '', 'record_id': None, 'page': 0}),
            ('simulate_month', {'planning_month': '2026-10', 'gross_salary': '6000', 'clt_dependents': 0,
                'clt_pension': '0', 'clt_transport': '0', 'clt_food': '0', 'clt_health': '0', 'clt_other': '600',
                'extra_expenses': []}),
        ])
        counts = [model.objects.count() for model in (Transaction, BankMovement, FinancialGoal, CategoryBudget)]
        from assistant.context import sign_scope
        self.send(content='Simule este mês com salário bruto CLT 6000 e outros descontos em folha 600',
                  scope=sign_scope(self.user, '/banking/'))
        context = json.loads(self.provider.requests[0].context_json)
        self.assertEqual(context['current_page']['route'], 'banking:list')
        self.assertEqual(context['application_access']['read'], 'all_owned_financial_workspaces')
        self.assertNotIn('metrics', context)
        self.assertNotIn('error', self.provider.results[0])
        result = self.provider.results[1]
        self.assertEqual(result['payroll']['net'], '4373.39')
        self.assertEqual(result['budget']['registered_expenses'], '12.34')
        self.assertEqual(result['budget']['remaining'], '4361.05')
        self.assertFalse(result['saved'])
        self.assertNotIn('Foreign scenario', json.dumps(self.provider.results))
        self.assertEqual(counts, [model.objects.count() for model in (Transaction, BankMovement, FinancialGoal, CategoryBudget)])
        run = GenerationRun.objects.get()
        self.assertTrue(any('/planning/' in row['url'] for row in run.context_references['references']))
        self.assertEqual(ActionProposal.objects.count(), 0)

    def test_edit_and_delete_tools_preserve_separate_confirmation_and_exact_fields(self):
        _bank, _account, _category, source = make_finances(self.user, 'Edited source')
        self.provider = ToolProvider([('prepare_transaction_update', {'transaction_id': source.pk,
            'changes': [{'field': 'amount', 'value': '20.00'}]})])
        self.send(content='Change my Edited source purchase amount to BRL 20')
        source.refresh_from_db()
        self.assertEqual(str(source.amount), '12.34')
        proposal = ActionProposal.objects.get()
        self.assertFalse(self.provider.results[0]['saved'])
        self.assertEqual(self.client.post(reverse('assistant:action-confirm', args=[proposal.pk])).status_code, 302)
        source.refresh_from_db()
        self.assertEqual(str(source.amount), '20.00')
        self.assertEqual(source.notes, 'DO NOT COPY PRIVATE NOTES')
        self.provider = ToolProvider([('prepare_transaction_delete', {'transaction_id': source.pk})])
        self.send(content='Delete my Edited source purchase')
        self.assertTrue(Transaction.objects.filter(pk=source.pk).exists())
        proposal = ActionProposal.objects.get(name='transaction.delete')
        for _ in range(2):
            self.assertEqual(self.client.post(reverse('assistant:action-confirm', args=[proposal.pk])).status_code, 302)
        self.assertFalse(Transaction.objects.filter(pk=source.pk).exists())
