# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bounded application tool calls using synthetic SSE only; no network or money."""
from dataclasses import replace
import io
import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from assistant.connections import service
from assistant.providers import openai
from assistant.providers.base import (
    CancellationToken, GenerationRequest, ProviderError, ProviderEvent, stream_response,
)


def sse(*events):
    return b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events)


class FakeStream(io.BytesIO):
    was_closed = False

    def close(self):
        self.was_closed = True
        super().close()


TOOL = {'type': 'function', 'name': 'prepare_transaction', 'description': 'Prepare for user review.',
        'parameters': {'type': 'object', 'properties': {'title': {'type': 'string'}},
                       'required': ['title'], 'additionalProperties': False}, 'strict': True}


def call(call_id='call_1', **changes):
    return {'type': 'function_call', 'namespace': 'tuxedo', 'name': 'prepare_transaction',
            'call_id': call_id, 'arguments': '{"title":"Synthetic"}', 'status': 'completed', **changes}


def completed(*items):
    return {'type': 'response.completed', 'response': {'output': list(items)}}


def item_done(item, index=0):
    return {'type': 'response.output_item.done', 'output_index': index, 'item': item}


@override_settings(ASSISTANT_OPENAI_AUTH_ENABLED=True, ASSISTANT_OPENAI_INFERENCE_ENABLED=True)
class OpenAIToolLoopTests(SimpleTestCase):
    def setUp(self):
        patcher = patch.object(service, 'get_authorized_access_token',
                               return_value=service.AuthorizedAccessToken('SYNTHETIC-TOKEN'))
        self.authorize = patcher.start()
        self.addCleanup(patcher.stop)
        self.calls, self.sources = [], []
        self.runner = Mock(return_value={'prepared': True, 'requires_review': True})
        self.request = GenerationRequest('{}', model='synthetic-model', tools=(TOOL,), tool_runner=self.runner)
        self.token = CancellationToken()

    def execute(self, *responses):
        self.sources = [FakeStream(sse(*events)) for events in responses]

        def transport(method, url, **kwargs):
            # The previous response must be closed before the next request starts.
            if self.calls:
                self.assertTrue(self.sources[len(self.calls) - 1].was_closed)
            self.calls.append((method, url, kwargs))
            return openai.TransportResponse(200, stream=self.sources[len(self.calls) - 1])
        self.provider = openai.OpenAIProvider(object(), 'synthetic', transport=transport)
        return list(stream_response(self.provider, self.request, self.token))

    def test_tool_contract_is_opt_in_detached_and_callback_is_not_in_repr(self):
        self.assertNotIn('tool_runner', repr(self.request))
        self.assertEqual(GenerationRequest('{}').tools, ())
        schema = json.loads(json.dumps(TOOL))
        request = replace(self.request, tools=(schema,))
        schema['parameters']['properties']['title']['type'] = 'number'
        self.assertEqual(request.tools[0]['parameters']['properties']['title']['type'], 'string')
        for changes in [{'tools': [TOOL]}, {'tool_runner': None}, {'tools': ()},
                        {'tools': (), 'tool_runner': 'unexpected'}, {'tools': (TOOL,) * 6},
                        {'tools': ({**TOOL, 'name': 'tuxedo.prepare_transaction'},)},
                        {'tools': ({**TOOL, 'type': 'web_search'},)},
                        {'tools': ({**TOOL, 'parameters': {'type': 'array'}},)},
                        {'tools': ({**TOOL, 'extra': 'forbidden'},)},
                        {'tools': ({**TOOL, 'description': 'x' * 32000},)}]:
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ValueError):
                    replace(self.request, **changes)

    def test_complete_calls_run_after_close_and_reasoning_roundtrips_with_results(self):
        reasoning = {'type': 'reasoning', 'id': 'rs_synthetic', 'summary': [],
                     'encrypted_content': 'SYNTHETIC-OPAQUE-REASONING'}

        def prepare(name, arguments):
            self.assertTrue(self.sources[0].was_closed)
            self.assertEqual((name, arguments), ('prepare_transaction', {'title': 'Synthetic'}))
            return {'prepared': True, 'requires_review': True}
        self.runner.side_effect = prepare
        events = self.execute([item_done(reasoning, 0),
                               {'type': 'response.function_call_arguments.delta', 'output_index': 1, 'delta': '{"title":'},
                               item_done(call(), 1), completed(reasoning, call())],
                              [{'type': 'response.output_text.delta', 'delta': '**Review** the prepared entry.'}, completed()])
        self.assertEqual(events, [ProviderEvent('text', text='**Review** the prepared entry.'), ProviderEvent('done')])
        self.runner.assert_called_once()
        self.assertEqual(self.authorize.call_count, 2)
        first, second = [row[2]['data'] for row in self.calls]
        self.assertEqual(first['tools'], [{'type': 'namespace', 'name': 'tuxedo',
            'description': 'Consult owned Tuxedo finances, calculate simulations and prepare changes for user review.', 'tools': [TOOL]}])
        self.assertEqual(first['include'], ['reasoning.encrypted_content'])
        self.assertEqual(second['input'][1:3], [reasoning, call()])
        output = second['input'][-1]
        self.assertEqual(output['type'], 'function_call_output')
        self.assertEqual(output['call_id'], 'call_1')
        self.assertEqual(json.loads(output['output']), {'prepared': True, 'requires_review': True})
        for body in (first, second):
            self.assertFalse(body['store'])
            self.assertTrue(body['stream'])
            self.assertNotIn('previous_response_id', body)
            self.assertNotIn('max_tool_calls', body)
            self.assertNotIn('SYNTHETIC-TOKEN', json.dumps(body))
        self.assertTrue(all(source.was_closed for source in self.sources))

    def test_omitted_namespace_calls_continue_without_rewriting_returned_history(self):
        item = call(id='fc_synthetic')
        del item['namespace']
        original = dict(item)
        events = self.execute([completed(item)],
            [{'type': 'response.output_text.delta', 'delta': 'Ready for review.'}, completed()])
        self.assertEqual(events, [ProviderEvent('text', text='Ready for review.'), ProviderEvent('done')])
        self.runner.assert_called_once_with('prepare_transaction', {'title': 'Synthetic'})
        self.assertEqual(item, original)
        self.assertEqual(len(self.calls), 2)
        first, second = [row[2]['data'] for row in self.calls]
        self.assertEqual(second['input'][1], original)
        self.assertNotIn('namespace', second['input'][1])
        self.assertEqual(second['input'][-1]['type'], 'function_call_output')
        self.assertEqual(second['input'][-1]['call_id'], original['call_id'])
        self.assertEqual(json.loads(second['input'][-1]['output']), self.runner.return_value)
        for body in (first, second):
            self.assertIs(body['store'], False)
            self.assertIs(body['stream'], True)
            self.assertNotIn('previous_response_id', body)
        self.assertTrue(all(source.was_closed for source in self.sources))

    def test_mixed_namespace_batch_executes_each_valid_call_and_preserves_both_items(self):
        bare = call('call_bare', arguments='{"title":"Bare"}')
        del bare['namespace']
        explicit = call('call_explicit', arguments='{"title":"Explicit"}')
        events = self.execute([completed(bare, explicit)], [completed()])
        self.assertEqual(events, [ProviderEvent('done')])
        self.assertEqual([entry.args for entry in self.runner.call_args_list],
            [('prepare_transaction', {'title': 'Bare'}), ('prepare_transaction', {'title': 'Explicit'})])
        self.assertEqual(len(self.calls), 2)
        second = self.calls[1][2]['data']
        self.assertEqual(second['input'][1:3], [bare, explicit])
        self.assertNotIn('namespace', second['input'][1])
        self.assertEqual(second['input'][2]['namespace'], 'tuxedo')
        self.assertEqual([item['call_id'] for item in second['input'][-2:]], ['call_bare', 'call_explicit'])
        self.assertTrue(all(source.was_closed for source in self.sources))

    def test_invalid_namespace_or_function_rejects_entire_batch_before_callbacks(self):
        invalid = [call('call_invalid', namespace=value) for value in (None, '', 'other', 'tuxedo.other', 1)]
        for name in ('execute_payment', 'tuxedo.prepare_transaction', 'functions.prepare_transaction'):
            explicit = call('call_invalid', name=name)
            bare = dict(explicit)
            del bare['namespace']
            invalid.extend((explicit, bare))
        for item in invalid:
            with self.subTest(namespace=item.get('namespace', 'omitted'), name=item['name']):
                self.calls.clear()
                events = self.execute([completed(call('call_valid'), item)])
                self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                self.runner.assert_not_called()
                self.assertEqual(len(self.calls), 1)
                self.assertTrue(self.sources[0].was_closed)

    def test_protocol_diagnostics_log_only_fixed_stages_not_returned_tool_fields(self):
        marker = 'SYNTHETIC-PRIVATE-DO-NOT-LOG'
        invalid = [
            (call(namespace=marker), 'tool_namespace'),
            (call(name=marker), 'tool_name'),
            (call(call_id=marker + '\nunsafe'), 'tool_call_id'),
            (call(status=marker), 'tool_status'),
            (call(arguments='{"private":"' + marker + '"'), 'tool_arguments'),
            ({'type': marker, 'name': marker, 'namespace': marker, 'call_id': marker, 'arguments': marker}, 'tool_output'),
        ]
        for item, stage in invalid:
            with self.subTest(stage=stage):
                self.calls.clear()
                with self.assertLogs(openai.logger.name, level='WARNING') as logs:
                    events = self.execute([completed(item)])
                self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                self.assertEqual(len(logs.records), 1)
                self.assertIn('stage=' + stage, logs.output[0])
                self.assertNotIn(marker, '\n'.join(logs.output))
                self.assertNotIn(marker, repr(logs.records[0].args))
                self.runner.assert_not_called()

    def test_arbitrary_diagnostic_stage_is_classified_without_echoing_private_values(self):
        marker = 'SYNTHETIC-PRIVATE-DO-NOT-LOG'
        with self.assertLogs(openai.logger.name, level='WARNING') as logs:
            openai._diagnostic(200, 'invalid_schema', protocol_stage=marker)
        self.assertEqual(len(logs.records), 1)
        self.assertIn('stage=other', logs.output[0])
        self.assertNotIn(marker, '\n'.join(logs.output))
        self.assertNotIn(marker, repr(logs.records[0].args))

    def test_compact_completion_retains_done_reasoning_and_two_calls_in_index_order(self):
        reasoning = {'type': 'reasoning', 'id': 'rs_compact', 'summary': [],
                     'encrypted_content': 'SYNTHETIC-COMPLETE-ENCRYPTED-REASONING'}
        first = call('call_first', arguments='{"title":"First"}')
        second = call('call_second', arguments='{"title":"Second"}')
        del second['namespace']
        for ending in (completed(), {'type': 'response.completed', 'response': {}}):
            with self.subTest(output_present='output' in ending['response']):
                self.calls.clear()
                self.runner.reset_mock()

                def prepare(name, arguments):
                    self.assertTrue(self.sources[0].was_closed)
                    return {'prepared': True, 'title': arguments['title']}
                self.runner.side_effect = prepare
                events = self.execute([
                    item_done(reasoning, 0),
                    {'type': 'response.output_item.added', 'output_index': 1,
                     'item': {**first, 'arguments': '', 'status': 'in_progress'}},
                    {'type': 'response.function_call_arguments.delta', 'output_index': 1, 'delta': '{"title":'},
                    item_done(second, 2), item_done(first, 1), ending,
                ], [{'type': 'response.output_text.delta', 'delta': 'Prepared.'}, completed()])
                self.assertEqual(events, [ProviderEvent('text', text='Prepared.'), ProviderEvent('done')])
                self.assertEqual([entry.args for entry in self.runner.call_args_list],
                    [('prepare_transaction', {'title': 'First'}), ('prepare_transaction', {'title': 'Second'})])
                second_request = self.calls[1][2]['data']
                self.assertEqual(second_request['input'][1:4], [reasoning, first, second])
                self.assertNotIn('namespace', second_request['input'][3])
                self.assertEqual([row['call_id'] for row in second_request['input'][-2:]], ['call_first', 'call_second'])
                for _method, _url, kwargs in self.calls:
                    self.assertIs(kwargs['data']['store'], False)
                    self.assertIs(kwargs['data']['stream'], True)
                self.assertTrue(all(source.was_closed for source in self.sources))

    def test_done_call_waits_for_explicit_completed_and_rejects_other_terminal_outcomes(self):
        endings = [(None, 'interrupted'), ({'type': 'response.failed'}, 'provider_error'),
                   ({'type': 'response.incomplete'}, 'incomplete'), ({'type': 'error'}, 'provider_error')]
        for ending, code in endings:
            with self.subTest(ending=ending):
                self.calls.clear()
                source_events = [item_done(call())]
                if ending is not None:
                    source_events.append(ending)
                self.assertEqual(self.execute(source_events), [ProviderEvent('error', code=code)])
                self.runner.assert_not_called()
                self.assertTrue(self.sources[0].was_closed)

    def test_cancellation_after_done_before_compact_completion_never_runs_callback(self):
        token = self.token

        class CancellingStream(FakeStream):
            def readline(self, limit):
                line = super().readline(limit)
                if b'"type": "response.completed"' in line:
                    token.cancel()
                return line

        with patch('assistant.tests.test_openai_tools.FakeStream', CancellingStream):
            events = self.execute([item_done(call()), completed()])
        self.assertEqual(events, [ProviderEvent('error', code='cancelled')])
        self.runner.assert_not_called()
        self.assertTrue(self.sources[0].was_closed)

    def test_compact_completion_rejects_any_unfinished_function_in_an_otherwise_done_batch(self):
        partials = [
            {'type': 'response.output_item.added', 'output_index': 1,
             'item': call('call_partial', arguments='', status='in_progress')},
            {'type': 'response.function_call_arguments.delta', 'output_index': 1, 'delta': '{"title":"Partial'},
            {'type': 'response.function_call_arguments.done', 'output_index': 1, 'arguments': '{"title":"Complete arguments"}'},
            {'type': 'response.function_call_arguments.delta', 'delta': '{"title":"No index"}'},
        ]
        for partial in partials:
            with self.subTest(type=partial['type'], indexed='output_index' in partial):
                self.calls.clear()
                events = self.execute([item_done(call()), partial, completed()])
                self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                self.runner.assert_not_called()
                self.assertTrue(self.sources[0].was_closed)

    def test_arguments_done_without_output_item_done_cannot_become_a_compact_call(self):
        events = self.execute([
            {'type': 'response.output_item.added', 'output_index': 0,
             'item': call(arguments='', status='in_progress')},
            {'type': 'response.function_call_arguments.done', 'output_index': 0,
             'arguments': '{"title":"Synthetic"}'}, completed(),
        ])
        self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
        self.runner.assert_not_called()

    def test_compact_done_items_require_bounded_unique_contiguous_integer_indexes(self):
        bad_indexes = [True, False, -1, 32, 1.5, '0', None]
        cases = [[item_done(call(), index)] for index in bad_indexes]
        missing = item_done(call())
        del missing['output_index']
        cases.extend(([missing], [item_done(call(), 1)],
                      [item_done(call()), item_done(call('call_second'))],
                      [item_done(call()), item_done(call())]))
        for source_events in cases:
            with self.subTest(events=source_events):
                self.calls.clear()
                events = self.execute([*source_events, completed()])
                self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                self.runner.assert_not_called()
                self.assertTrue(self.sources[0].was_closed)

    def test_compact_done_items_with_incomplete_status_or_malformed_content_never_run(self):
        invalid = [item_done(call(status=status)) for status in ('in_progress', 'incomplete', None)]
        invalid.extend((item_done(None), item_done([]), item_done('not an item')))
        for event in invalid:
            with self.subTest(event=event):
                self.calls.clear()
                self.assertEqual(self.execute([event, completed()]), [ProviderEvent('error', code='invalid_response')])
                self.runner.assert_not_called()

    def test_compact_done_calls_still_validate_names_arguments_and_duplicate_call_ids_as_a_batch(self):
        for invalid in (call('call_second', name='execute_payment'), call('call_second', arguments='[]'),
                        call('call_second', arguments='not JSON'), call()):
            with self.subTest(invalid=invalid):
                self.calls.clear()
                events = self.execute([item_done(call(), 0), item_done(invalid, 1), completed()])
                self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                self.runner.assert_not_called()

    def test_nonempty_completion_must_match_each_done_slot_and_never_duplicates_callbacks(self):
        for replacement in (call(arguments='{"title":"Changed"}'), call('call_different'),
                            call(name='execute_payment')):
            with self.subTest(replacement=replacement):
                self.calls.clear()
                events = self.execute([item_done(call()), completed(replacement)])
                self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                self.runner.assert_not_called()
        self.calls.clear()
        events = self.execute([item_done(call()), completed(call())], [completed()])
        self.assertEqual(events, [ProviderEvent('done')])
        self.runner.assert_called_once_with('prepare_transaction', {'title': 'Synthetic'})
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(sum(row.get('type') == 'function_call' for row in self.calls[1][2]['data']['input']), 1)

    def test_done_items_do_not_override_explicit_null_or_invalid_completion_output(self):
        for output in (None, {}, 'invalid'):
            with self.subTest(output=output):
                self.calls.clear()
                events = self.execute([item_done(call()), {'type': 'response.completed', 'response': {'output': output}}])
                self.assertEqual(events, [ProviderEvent('error', code='invalid_response')])
                self.runner.assert_not_called()

    def test_compact_done_items_preserve_global_history_and_tool_call_budgets(self):
        large = 'x' * (openai.MAX_TOOL_HISTORY_BYTES // 2)
        reasoning = {'type': 'reasoning', 'summary': [], 'encrypted_content': large}
        events = self.execute([item_done({**reasoning, 'id': 'rs_first'}, 0),
                               item_done({**reasoning, 'id': 'rs_second'}, 1), item_done(call(), 2), completed()])
        self.assertEqual(events, [ProviderEvent('error', code='limit_exceeded')])
        self.runner.assert_not_called()
        self.calls.clear()
        events = self.execute([*(item_done(call(f'call_{index}'), index) for index in range(11)), completed()])
        self.assertEqual(events, [ProviderEvent('error', code='limit_exceeded')])
        self.runner.assert_not_called()

    def test_partial_streamed_arguments_never_execute(self):
        for ending in [None, {'type': 'response.incomplete'}, {'type': 'response.failed'}, completed()]:
            with self.subTest(ending=ending):
                events = [{'type': 'response.function_call_arguments.delta', 'delta': '{"title":"Partial'}]
                if ending is not None:
                    events.append(ending)
                self.calls.clear()
                result = self.execute(events)
                self.assertEqual(result[-1].kind, 'error')
                self.runner.assert_not_called()
                self.assertTrue(self.sources[0].was_closed)

    def test_unknown_namespace_name_duplicates_and_invalid_arguments_fail_before_any_tool(self):
        invalid = [call(namespace='other'), call(name='execute_payment'), call(status='in_progress'),
                   call(arguments='[]'), call(arguments='{"title":NaN}'),
                   call(arguments='{"amount":1e400}'),
                   call(arguments='{"title":"A","title":"B"}'), call(arguments='not json'),
                   call(call_id='unsafe\nidentifier'), call(arguments='x' * (openai.MAX_TOOL_BYTES + 1))]
        for item in invalid:
            with self.subTest(item=item.get('name')):
                self.calls.clear()
                self.assertEqual(self.execute([completed(item)])[-1].kind, 'error')
                self.runner.assert_not_called()
        self.calls.clear()
        self.assertEqual(self.execute([completed(call(), call())])[-1],
                         ProviderEvent('error', code='invalid_response'))
        self.runner.assert_not_called()

    def test_duplicate_call_across_rounds_is_not_repeated(self):
        events = self.execute([completed(call())], [completed(call())])
        self.assertEqual(events[-1], ProviderEvent('error', code='invalid_response'))
        self.runner.assert_called_once()
        self.assertEqual(len(self.calls), 2)

    def test_five_request_and_ten_call_limits_are_global_without_retry(self):
        events = self.execute(*([completed(call(f'round_{i}'))] for i in range(5)))
        self.assertEqual(events[-1], ProviderEvent('error', code='limit_exceeded'))
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(self.runner.call_count, 4)
        self.calls.clear()
        self.runner.reset_mock()
        events = self.execute([completed(*(call(f'call_{i}') for i in range(11)))])
        self.assertEqual(events[-1], ProviderEvent('error', code='limit_exceeded'))
        self.runner.assert_not_called()
        self.assertEqual(len(self.calls), 1)
        self.calls.clear()
        events = self.execute([completed(*(call(f'call_{i}') for i in range(10)))], [completed()])
        self.assertEqual(events[-1], ProviderEvent('done'))
        self.assertEqual(self.runner.call_count, 10)

    def test_invalid_or_oversized_tool_results_and_callback_failures_are_safe(self):
        for result, code in [(['invalid'], 'invalid_response'), ({'bad': float('nan')}, 'invalid_response'),
                             ({'large': 'x' * openai.MAX_TOOL_BYTES}, 'limit_exceeded')]:
            with self.subTest(code=code):
                self.calls.clear()
                self.runner.return_value = result
                self.assertEqual(self.execute([completed(call())])[-1], ProviderEvent('error', code=code))
                self.assertEqual(len(self.calls), 1)
        self.calls.clear()
        self.runner.side_effect = RuntimeError('SECRET-CALLBACK-CREDENTIAL')
        events = self.execute([completed(call())])
        self.assertEqual(events[-1], ProviderEvent('error', code='provider_error'))
        self.assertNotIn('SECRET', repr(events))
        self.calls.clear()
        self.runner.side_effect = ProviderError('unauthorized')
        self.assertEqual(self.execute([completed(call())])[-1], ProviderEvent('error', code='unauthorized'))

    def test_cancellation_from_callback_stops_before_followup(self):
        def cancel(name, arguments):
            self.token.cancel()
            return {'prepared': True}
        self.runner.side_effect = cancel
        self.assertEqual(self.execute([completed(call())])[-1], ProviderEvent('error', code='cancelled'))
        self.assertEqual(len(self.calls), 1)

    def test_client_abandonment_closes_tool_enabled_response_before_completion(self):
        source = FakeStream(sse({'type': 'response.output_text.delta', 'delta': 'Preparing'}, completed(call())))
        provider = openai.OpenAIProvider(object(), 'synthetic',
            transport=lambda *args, **kwargs: openai.TransportResponse(200, stream=source))
        iterator = stream_response(provider, self.request, self.token)
        self.assertEqual(next(iterator), ProviderEvent('text', text='Preparing'))
        iterator.close()
        self.assertTrue(source.was_closed)
        self.runner.assert_not_called()

    def test_deadline_is_shared_across_rounds_and_tool_callback(self):
        clock = [0]
        def slow(name, arguments):
            clock[0] = 91
            return {'prepared': True}
        self.runner.side_effect = slow
        with patch.object(openai.time, 'monotonic', side_effect=lambda: clock[0]):
            self.assertEqual(self.execute([completed(call())])[-1], ProviderEvent('error', code='timeout'))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.sources[0].was_closed)

    def test_undeclared_calls_do_not_execute_and_output_text_limit_spans_rounds(self):
        self.request = replace(self.request, tools=(), tool_runner=None)
        self.assertEqual(self.execute([completed(call())])[-1], ProviderEvent('error', code='invalid_response'))
        self.runner.assert_not_called()
        self.calls.clear()
        self.request = replace(self.request, tools=(TOOL,), tool_runner=self.runner)
        events = self.execute([{'type': 'response.output_text.delta', 'delta': 'x' * 9000}, completed(call())],
                              [{'type': 'response.output_text.delta', 'delta': 'y' * 9000}, completed()])
        self.assertEqual(events[-1], ProviderEvent('error', code='limit_exceeded'))
        self.assertLessEqual(sum(len(event.text) for event in events), 16000)
