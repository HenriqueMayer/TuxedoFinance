# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Provider-neutral, bounded proposal tools; confirmation is never a model tool."""
from hashlib import sha256
import json
import uuid

from core.currencies import CURRENCIES


def _function(name, description, fields):
    return {'type': 'function', 'name': name, 'description': description, 'strict': True,
            'parameters': {'type': 'object', 'properties': fields,
                           'required': list(fields), 'additionalProperties': False}}


def financial_tools():
    """Fresh schemas contain no user records, credentials or execution endpoint."""
    from transactions.models import Transaction
    text = {'type': 'string'}
    money = {'type': 'string', 'description': 'Positive native amount as a decimal string, e.g. 12.34. Never cents or a float.'}
    currency = {'type': 'string', 'enum': list(CURRENCIES)}
    record = {'type': 'integer', 'minimum': 1}
    optional_record = {'type': ['integer', 'null'], 'minimum': 1}
    tools = (
        _function('find_choices',
                  'Find at most 20 owned choices needed for the user\'s requested action. '
                  'Search a named account/card/category rather than inventing an ID. '
                  'Transactions require a nonempty title query. This does not read balances, notes or complete history.',
                  {'kind': {'type': 'string', 'enum': ['accounts', 'credit_cards', 'debit_cards', 'categories', 'transactions']},
                   'query': {'type': 'string', 'maxLength': 120}}),
        _function('prepare_transaction',
                  'Prepare a requested income/expense for review. This saves no financial transaction. '
                  'Ask for missing amount, date, title, category or payment instrument. '
                  'Use null for incompatible instruments, 1 installment, false recurrence, null cycle and empty notes unless requested. '
                  'Do not silently create a transfer, settlement or split. User must confirm in the chat.',
                  {'title': {'type': 'string', 'maxLength': 150}, 'amount': money, 'currency': currency,
                   'date': {'type': 'string', 'description': 'Explicit YYYY-MM-DD date; resolve today from supplied cutoff.'},
                   'transaction_type': {'type': 'string', 'enum': ['INCOME', 'EXPENSE']}, 'category_id': record,
                   'payment_channel': {'type': 'string', 'enum': ['ACCOUNT', 'PIX', 'DEBIT_CARD', 'CREDIT_CARD']},
                   'account_id': optional_record, 'debit_card_id': optional_record, 'credit_card_id': optional_record,
                   'installments': {'type': 'integer', 'minimum': 1, 'maximum': Transaction.MAX_INSTALLMENTS},
                   'is_fixed': {'type': 'boolean'}, 'fixed_until': {'type': ['string', 'null']},
                   'billing_override': {'type': ['integer', 'null'], 'enum': [None, 0, 1]},
                   'notes': {'type': 'string', 'maxLength': 2000}}),
        _function('prepare_categorization',
                  'Prepare changing one explicitly identified source transaction category. '
                  'Split and generated/locked transactions must use their existing application flow. Nothing changes until user confirmation.',
                  {'transaction_id': record, 'category_id': record}),
        _function('prepare_goal',
                  'Prepare a requested financial target for review. Ask for name, target amount and currency; '
                  'target_date may be null. Creates no reservation or transfer. Nothing is saved until user confirmation.',
                  {'name': {'type': 'string', 'maxLength': 120}, 'target_amount': money,
                   'currency': currency, 'target_date': {'type': ['string', 'null']}}),
        _function('prepare_budget',
                  'Prepare a requested category budget for a YYYY-MM month and native currency. '
                  'Respect existing overlap rules. Nothing is saved until user confirmation.',
                  {'category_id': record, 'month': text, 'currency': currency, 'amount': money}),
    )
    from assistant.consultation import consultation_schema
    from assistant.simulation_tools import monthly_simulation_schema
    editable = tools[1]['parameters']['properties']
    return (*tools, consultation_schema(), monthly_simulation_schema(),
        _function('prepare_transaction_update',
            'Prepare editing an explicitly identified source transaction. Only include fields the user requested. '
            'Nothing changes before the user reviews before/after values and confirms. '
            'An explicit null clears an optional field; never use null to mean unchanged. '
            'Resolve transaction/category/instrument IDs with owned tools. A source split needs its ordinary editor.',
            {'transaction_id': record, 'changes': {'type': 'array', 'minItems': 1, 'maxItems': len(editable),
                'items': {'type': 'object', 'additionalProperties': False, 'required': ['field', 'value'],
                          'properties': {'field': {'type': 'string', 'enum': list(editable)},
                              'value': {'anyOf': [{'type': 'string'}, {'type': 'integer'},
                                                   {'type': 'boolean'}, {'type': 'null'}]}}}}}),
        _function('prepare_transaction_delete',
            'Prepare deleting one explicitly identified source transaction. Never delete from a vague or ambiguous match. '
            'Shows its complete identity and consequences for user confirmation; this tool does not delete.',
            {'transaction_id': record}))


_ACTIONS = {'prepare_transaction': 'transaction.create', 'prepare_categorization': 'transaction.categorize',
            'prepare_goal': 'goal.create', 'prepare_budget': 'budget.create',
            'prepare_transaction_update': 'transaction.update', 'prepare_transaction_delete': 'transaction.delete'}


def recorded_actions(user, conversation):
    """Recent facts from this chat, not another financial-context inventory."""
    if conversation is None:
        return []
    from assistant.models import ActionProposal
    rows = ActionProposal.objects.filter(conversation=conversation, conversation__user=user,
                                          generation_run__status='completed').order_by('-created_at', '-pk')[:5]
    return [{'proposal_id': str(row.pk), 'action': row.name, 'status': row.status,
             'result_url': row.result_url if row.status == 'executed' else ''} for row in rows]


def run_tool(user, session_key, run, name, arguments):
    """Called only through the live run's repeated owner/session authorization."""
    from assistant import action_service

    if not isinstance(arguments, dict):
        return {'error': 'invalid_parameters', 'saved': False}
    if name in {'read_financial_data', 'simulate_month'}:
        from assistant.consultation import assert_owned_sources, read_financial_data
        from assistant.simulation_tools import simulate_month
        from django.core.exceptions import ValidationError
        try:
            if name == 'read_financial_data':
                return read_financial_data(user, arguments)
            assert_owned_sources(user)
            return simulate_month(user, arguments)
        except action_service.ActionError as error:
            return {'error': error.code, 'saved': False}
        except (ValidationError, ValueError, ArithmeticError):
            return {'error': 'financial_data_unavailable', 'saved': False}
    if name == 'find_choices':
        if (set(arguments) != {'kind', 'query'} or not isinstance(arguments['query'], str)
                or len(arguments['query']) > 120 or not isinstance(arguments['kind'], str)):
            return {'error': 'invalid_parameters', 'saved': False}
        try:
            return action_service.action_choices(user, arguments['kind'], arguments['query'])
        except action_service.ActionError as error:
            return {'error': error.code, 'saved': False}
    action = _ACTIONS.get(name)
    if action is None:
        return {'error': 'unsupported_action', 'saved': False}
    try:
        if action == 'transaction.update':
            changes = arguments.get('changes')
            if (set(arguments) != {'transaction_id', 'changes'} or not isinstance(changes, list)
                    or not 1 <= len(changes) <= 17
                    or any(not isinstance(row, dict) or set(row) != {'field', 'value'}
                           or not isinstance(row['field'], str) for row in changes)
                    or len({row['field'] for row in changes}) != len(changes)):
                return {'error': 'invalid_parameters', 'saved': False}
            arguments = {**arguments, 'changes': {row['field']: row['value'] for row in changes}}
        normalized = action_service.normalize_parameters(action, arguments)
        # Repeating the same proposal in one reply must not create two separate
        # Confirm buttons. A new user request has a different run identity.
        fingerprint = sha256(json.dumps({'name': action, 'parameters': normalized}, sort_keys=True,
                                       ensure_ascii=True, allow_nan=False).encode()).hexdigest()
        proposal = action_service.prepare_action(
            user, session_key, run.conversation, action, normalized,
            request_id=uuid.uuid5(run.pk, fingerprint), run_id=run.pk)
    except (ValueError, TypeError):
        return {'error': 'invalid_parameters', 'saved': False}
    except action_service.ActionError as error:
        return {'error': error.code, 'fields': error.errors, 'saved': False}
    # The complete review stays in the local UI. In particular, categorizing an
    # existing source must not disclose its notes or payment details to a model.
    return {'proposal_id': str(proposal.pk), 'action': proposal.name, 'status': 'awaiting_confirmation',
            'saved': False,
            'next_step': 'The user must review and press the application Confirm button. Model text never confirms.'}
