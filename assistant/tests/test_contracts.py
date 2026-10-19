# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Offline contract evaluations, not live-model quality or safety measurements."""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path

from django.db import transaction
from django.test import SimpleTestCase, TestCase

from assistant.actions import preview_action
from assistant.prompts import INSTRUCTIONS_VERSION, load_instructions
from assistant.providers import get_provider
from assistant.providers.base import (
    CancellationToken, ChatTurn, GenerationRequest, ProviderEvent, ProviderTransactionError,
    stream_response,
)


class OfflineProviderContractsTests(SimpleTestCase):
    def test_default_provider_has_only_explicit_unavailable_terminal_event(self):
        events = list(stream_response(get_provider(), GenerationRequest('{}'), CancellationToken()))
        self.assertEqual(events, [ProviderEvent('error', code='unavailable')])

    def test_selected_history_context_and_languages_are_bounded(self):
        turn = ChatTurn('user', 'Synthetic question')
        request = GenerationRequest('{}', history=(turn,), language='pt-br')
        self.assertIn('Selected user language: pt-br.', request.instructions)
        with self.assertRaises(FrozenInstanceError):
            request.language = 'en'
        rejected = [lambda: ChatTurn('system', 'Do not elevate untrusted history'),
                    lambda: ChatTurn('user', 'x' * 4001), lambda: GenerationRequest('[]'),
                    lambda: GenerationRequest('{' + 'x' * 32000),
                    lambda: GenerationRequest('{}', history=(turn,) * 21),
                    lambda: GenerationRequest('{}', language='invalid'),
                    lambda: GenerationRequest('{}', instructions_version='../other'),
                    lambda: GenerationRequest('{}', reasoning_effort='unknown'),
                    lambda: GenerationRequest('{}', reasoning_effort=None)]
        for make_invalid in rejected:
            with self.subTest(make_invalid=make_invalid):
                with self.assertRaises(ValueError):
                    make_invalid()

    def test_versioned_instruction_fixture_obligations_are_present(self):
        cases = json.loads((Path(__file__).parent / 'offline_cases.json').read_text())
        instructions = ' '.join(load_instructions().split())
        self.assertEqual(INSTRUCTIONS_VERSION, 'v2')
        for case in cases:
            with self.subTest(case=case['id']):
                self.assertTrue(case['synthetic_only'])
                self.assertIsInstance(case['question'], str)
                self.assertTrue(case['question'])
                self.assertTrue(case['expected_behavior'])
                self.assertTrue(case['forbidden_behavior'])
                self.assertEqual(set(case['context']), {'captured_at', 'cutoff', 'currency', 'workspace_label',
                                                       'metrics', 'warnings', 'sources'})
                self.assertIn(case['required_instruction'], instructions)
                request = GenerationRequest(json.dumps(case['context']),
                                            history=(ChatTurn('user', case['question']),), language=case['request_language'])
                self.assertIn('Selected user language: ' + case['request_language'], request.instructions)
                self.assertLessEqual(len(request.context_json), 32000)
        with self.assertRaises(ValueError):
            load_instructions('../../unexpected')

    def test_fixture_stream_completion_and_cooperative_cancellation_close_iterator(self):
        closed = []

        class TestOnlyProvider:
            def stream(self, request, cancellation):
                try:
                    yield ProviderEvent('text', text='Synthetic fixture, not a product answer')
                    yield ProviderEvent('text', text='Second fixture event')
                    yield ProviderEvent('done')
                finally:
                    closed.append(True)

        token = CancellationToken()
        stream = stream_response(TestOnlyProvider(), GenerationRequest('{}'), token)
        self.assertEqual(next(stream).kind, 'text')
        token.cancel()
        self.assertEqual(list(stream), [ProviderEvent('error', code='cancelled')])
        self.assertEqual(closed, [True])
        complete = list(stream_response(TestOnlyProvider(), GenerationRequest('{}'), CancellationToken()))
        self.assertEqual([event.kind for event in complete], ['text', 'text', 'done'])

    def test_disconnect_close_and_failure_do_not_expose_raw_transport_secrets(self):
        class FailingIterator:
            def __iter__(self):
                return self

            def __next__(self):
                raise TimeoutError('SECRET TRANSPORT TOKEN')

            def close(self):
                raise RuntimeError('SECRET CLOSE TOKEN')

        class TestOnlyProvider:
            def stream(self, request, cancellation):
                return FailingIterator()

        events = list(stream_response(TestOnlyProvider(), GenerationRequest('{}'), CancellationToken()))
        self.assertEqual(events, [ProviderEvent('error', code='transport_error')])
        self.assertNotIn('SECRET', repr(events))

    def test_client_abandonment_closes_provider_and_precancel_never_opens_it(self):
        calls, closed = [], []

        class TestOnlyProvider:
            def stream(self, request, cancellation):
                calls.append(True)
                try:
                    yield ProviderEvent('text', text='Fixture')
                finally:
                    closed.append(True)

        token = CancellationToken()
        token.cancel()
        self.assertEqual(list(stream_response(TestOnlyProvider(), GenerationRequest('{}'), token)),
                         [ProviderEvent('error', code='cancelled')])
        self.assertEqual(calls, [])
        stream = stream_response(TestOnlyProvider(), GenerationRequest('{}'), CancellationToken())
        next(stream)
        stream.close()
        self.assertEqual(closed, [True])

    def test_invalid_provider_events_have_stable_error_and_terminal_stops_stream(self):
        class InvalidProvider:
            def stream(self, request, cancellation):
                yield {'unexpected': 'SECRET MODEL TOKEN'}

        class TerminalProvider:
            def stream(self, request, cancellation):
                yield ProviderEvent('done')
                raise AssertionError('A terminal event must stop iteration')

        self.assertEqual(list(stream_response(InvalidProvider(), GenerationRequest('{}'), CancellationToken())),
                         [ProviderEvent('error', code='provider_error')])
        self.assertEqual(list(stream_response(TerminalProvider(), GenerationRequest('{}'), CancellationToken())),
                         [ProviderEvent('done')])
        with self.assertRaises(ValueError):
            ProviderEvent('error', text='Raw exception material', code='transport_error')


class ProviderTransactionBoundaryTests(TestCase):
    def test_generation_cannot_start_inside_database_transaction(self):
        with transaction.atomic():
            with self.assertRaises(ProviderTransactionError):
                list(stream_response(get_provider(), GenerationRequest('{}'), CancellationToken()))


class OfflineActionProposalTests(SimpleTestCase):
    """Database access is forbidden by SimpleTestCase, including dry runs."""

    def test_allowlisted_transaction_goal_budget_alert_shapes_are_non_executable(self):
        cases = {
            'transaction.create': {'title': 'Synthetic expense', 'amount': '10.20', 'currency': 'BRL',
                                   'date': '2026-10-18', 'transaction_type': 'EXPENSE', 'account_id': 1, 'category_id': 2},
            'transaction.categorize': {'transaction_id': 1, 'category_id': 2},
            'goal.create': {'name': 'Synthetic goal', 'target_amount': '100.00', 'currency': 'USD', 'target_date': None},
            'budget.create': {'category_id': 2, 'month': '2026-10', 'currency': 'EUR', 'amount': '30.00'},
            'alert.propose': {'kind': 'cash_shortage', 'summary': 'Synthetic review suggestion', 'source_url': '/planning/signals/'},
        }
        for name, parameters in cases.items():
            with self.subTest(name=name):
                preview = preview_action(name, parameters)
                self.assertEqual(dict(preview.parameters), parameters)
                self.assertTrue(preview.requires_review)
                self.assertFalse(preview.executable)
                self.assertIn('have not been validated', preview.warnings[0])
                with self.assertRaises(TypeError):
                    preview.parameters['owner'] = 1

    def test_unsupported_actions_extra_owners_invalid_dates_and_precision_are_rejected(self):
        valid = {'title': 'Fixture', 'amount': '10.00', 'currency': 'BRL', 'date': '2026-10-18',
                 'transaction_type': 'EXPENSE', 'account_id': 1, 'category_id': 2}
        for field, value in [('amount', '0'), ('amount', 'NaN'), ('amount', '1.001'), ('amount', 10.0),
                             ('currency', 'INVALID'), ('date', '2026-02-31'), ('title', ''), ('account_id', True),
                             ('category_id', -1), ('category_id', 9223372036854775808), ('transaction_type', 'anything')]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    preview_action('transaction.create', {**valid, field: value})
        for name, parameters in [('transfer.execute', valid), ('transaction.create', {**valid, 'user_id': 1}),
                                  ('transaction.create', {**valid, 'execute': True}),
                                  ('budget.create', {'category_id': 1, 'month': '2026-13', 'currency': 'BRL', 'amount': '10.00'}),
                                  ('alert.propose', {'kind': 'cash_shortage', 'summary': 'Fixture', 'source_url': 'https://example.com/'})]:
            with self.subTest(name=name, parameters=parameters):
                with self.assertRaises(ValueError):
                    preview_action(name, parameters)
