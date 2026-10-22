# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Reviewable local financial actions; only explicit confirmation can write.

Model output is an untrusted proposal. The server resolves every reference,
uses the ordinary financial forms/services and checks their state again at the
separate confirmation boundary. No provider call belongs in this module.
"""
from dataclasses import dataclass
from copy import copy
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import re
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.translation import gettext as _

from assistant.models import ActionProposal, Conversation, GenerationRun
from banking.models import BankAccount, CreditCard, DebitCard
from categories.models import Category
from core.currencies import CURRENCIES
from planning.forms import CategoryBudgetForm, GoalCreationForm
from planning.services import create_goal, save_budget
from transactions.forms import TransactionForm
from transactions.models import Transaction
from transactions.projection import ProjectionLimitExceeded, validate_occurrences
from transactions.services import sync_user_ledger


PROPOSAL_LIFETIME = timedelta(minutes=30)
SUPPORTED_ACTIONS = ('transaction.create', 'transaction.categorize', 'transaction.update',
                     'transaction.delete', 'goal.create', 'budget.create')
_REQUIRED = {
    'transaction.create': {'title', 'amount', 'currency', 'date', 'transaction_type', 'category_id'},
    'transaction.categorize': {'transaction_id', 'category_id'},
    'transaction.update': {'transaction_id', 'changes'},
    'transaction.delete': {'transaction_id'},
    'goal.create': {'name', 'target_amount', 'currency', 'target_date'},
    'budget.create': {'category_id', 'month', 'currency', 'amount'},
}
_TRANSACTION_OPTIONAL = {'account_id', 'payment_channel', 'debit_card_id', 'credit_card_id',
                         'installments', 'is_fixed', 'fixed_until', 'billing_override', 'notes'}
_TRANSACTION_CHANGES = _REQUIRED['transaction.create'] | _TRANSACTION_OPTIONAL


class ActionError(Exception):
    """Stable public errors, without raw exceptions or foreign record labels."""

    def __init__(self, code, status=400, errors=None):
        self.code, self.status, self.errors = code, status, errors or {}
        super().__init__(code)


@dataclass
class _ValidatedAction:
    form: object
    summary: list
    dependency_digest: str
    original: object = None
    changed_fields: tuple = ()
    repairing_projection: bool = False


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     default=str, separators=(',', ':')).encode()).hexdigest()


def _session_digest(user, session_key, *, generation=False):
    if (not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False)
            or not isinstance(session_key, str) or not 1 <= len(session_key) <= 256
            or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists()):
        raise ActionError('unauthorized', 403)
    namespace = 'assistant.chat.session.v1' if generation else 'assistant.action.session.v1'
    return salted_hmac(namespace, f'{user.pk}:{session_key}', algorithm='sha256').hexdigest()


def _uuid(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ActionError('invalid_request') from None


def _identifier(value, *, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        raise ActionError('invalid_parameters')
    return value


def _date(value, *, nullable=False, month=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}' if month else r'\d{4}-\d{2}-\d{2}', value):
        raise ActionError('invalid_parameters')
    try:
        parsed = date.fromisoformat(value + '-01' if month else value)
    except ValueError:
        raise ActionError('invalid_parameters') from None
    if not 1901 <= parsed.year <= 9988:
        raise ActionError('invalid_parameters')
    return value


def normalize_parameters(name, parameters):
    """Canonical action values shared by proposal identity and validation."""
    if not isinstance(name, str) or name not in SUPPORTED_ACTIONS or not isinstance(parameters, dict):
        raise ActionError('unsupported_action')
    if name == 'transaction.update':
        if set(parameters) != {'transaction_id', 'changes'}:
            raise ActionError('invalid_parameters')
        changes = parameters['changes']
        if not isinstance(changes, dict) or not changes or set(changes) - _TRANSACTION_CHANGES:
            raise ActionError('invalid_parameters')
        return {'transaction_id': _identifier(parameters['transaction_id']),
                'changes': _normalize_values(dict(changes))}
    allowed = _REQUIRED[name] | (_TRANSACTION_OPTIONAL if name == 'transaction.create' else set())
    if not _REQUIRED[name] <= set(parameters) or set(parameters) - allowed:
        raise ActionError('invalid_parameters')
    normalized = dict(parameters)
    if name == 'transaction.create':
        normalized = dict(account_id=None, payment_channel='ACCOUNT', debit_card_id=None,
                          credit_card_id=None, installments=1, is_fixed=False, fixed_until=None,
                          billing_override=None, notes='') | normalized
    normalized = _normalize_values(normalized)
    if name == 'transaction.create':
        channel = normalized['payment_channel']
        if channel in {'ACCOUNT', 'PIX'}:
            if normalized['account_id'] is None or normalized['credit_card_id'] is not None or normalized['debit_card_id'] is not None:
                raise ActionError('invalid_parameters')
        elif channel == 'DEBIT_CARD':
            if normalized['debit_card_id'] is None or normalized['credit_card_id'] is not None:
                raise ActionError('invalid_parameters')
        elif normalized['credit_card_id'] is None or normalized['debit_card_id'] is not None:
            raise ActionError('invalid_parameters')
    return normalized


def _normalize_values(normalized):
    for key, value in normalized.items():
        if key.endswith('_id'):
            normalized[key] = _identifier(value, nullable=key in {'account_id', 'debit_card_id', 'credit_card_id'})
        elif key in {'title', 'name', 'notes'}:
            limit = {'title': 150, 'name': 120, 'notes': 2000}[key]
            if (not isinstance(value, str) or len(value) > limit
                    or (key != 'notes' and not value.strip())):
                raise ActionError('invalid_parameters')
            normalized[key] = value.strip()
        elif key == 'currency':
            if not isinstance(value, str) or value not in CURRENCIES:
                raise ActionError('invalid_parameters')
        elif key in {'amount', 'target_amount'}:
            # Bound before Decimal construction and forbid exponent expansion.
            if not isinstance(value, str) or not re.fullmatch(r'\d{1,14}(?:\.\d{1,2})?', value):
                raise ActionError('invalid_parameters')
            amount = Decimal(value)
            if amount < Decimal('0.01'):
                raise ActionError('invalid_parameters')
            normalized[key] = format(amount, '.2f')
        elif key in {'date', 'target_date', 'fixed_until', 'month'}:
            normalized[key] = _date(value, nullable=key in {'target_date', 'fixed_until'}, month=key == 'month')
        elif key == 'transaction_type' and value not in Transaction.TransactionType.values:
            raise ActionError('invalid_parameters')
        elif key == 'payment_channel' and value not in Transaction.PaymentChannel.values:
            raise ActionError('invalid_parameters')
        elif key == 'installments' and (type(value) is not int or not 1 <= value <= Transaction.MAX_INSTALLMENTS):
            raise ActionError('invalid_parameters')
        elif key == 'is_fixed' and type(value) is not bool:
            raise ActionError('invalid_parameters')
        elif key == 'billing_override' and value is not None and (type(value) is not int or value not in (0, 1)):
            raise ActionError('invalid_parameters')
    return normalized


def _category(user, category_id):
    category = Category.objects.filter(user=user, pk=category_id).filter(
        Q(parent_category__isnull=True) | Q(parent_category__user=user)).select_related('parent_category').first()
    if category is None:
        raise ActionError('invalid_reference')
    return category


def _account(user, account_id):
    account = BankAccount.objects.filter(user=user, bank__user=user, pk=account_id).select_related('bank').first()
    if account is None:
        raise ActionError('invalid_reference')
    return account


def _card(user, card_id, model):
    card = model.objects.filter(user=user, account__user=user, account__bank__user=user,
                                pk=card_id).select_related('account__bank').first()
    if card is None:
        raise ActionError('invalid_reference')
    return card


def _state(item):
    return {field.attname: getattr(item, field.attname) for field in item._meta.concrete_fields}


def _instrument(user, parameters):
    channel = parameters['payment_channel']
    if channel in {'ACCOUNT', 'PIX'}:
        account = instrument = _account(user, parameters['account_id'])
        field = 'bank_account'
    else:
        model, field = ((CreditCard, 'credit_card') if channel == 'CREDIT_CARD' else (DebitCard, 'debit_card'))
        instrument = _card(user, parameters[f'{field}_id'], model)
        account = instrument.account
        if parameters['account_id'] not in (None, account.pk):
            raise ActionError('invalid_reference')
    return account, instrument, field


def _assert_form(form):
    if not form.is_valid():
        raise ActionError('validation_failed', errors={key: [str(error) for error in errors]
                                                       for key, errors in form.errors.items()})
    return form


def _row(label, value):
    return {'label': str(label), 'value': str(value)}


def _transaction_summary(item, category):
    result = [_row(_('Title'), item.title),
              _row(_('Amount'), f'{item.native_currency} {item.amount:.2f}'),
              _row(_('Transaction type'), item.get_transaction_type_display()),
              _row(_('Transaction date'), item.date.isoformat()),
              _row(_('Category'), str(category)),
              _row(_('Payment channel'), item.get_payment_channel_display()),
              _row(_('Payment instrument'), item.payment_label)]
    if item.is_credit_card:
        result.extend([_row(_('Installments'), item.installments),
                       _row(_('Bill choice'), item.get_billing_override_display() if item.billing_override is not None else _('Automatic (from card cycle)')),
                       _row(_('Closing day'), item.credit_card.closing_day),
                       _row(_('Due day'), item.credit_card.due_day),
                       _row(_('Settlement'), _('Confirmed payments') if item.credit_card.manual_settlement_from else _('Automatic accounting'))])
        if item.credit_card.manual_settlement_from:
            result.append(_row(_('Confirmed payments from'), item.credit_card.manual_settlement_from.isoformat()))
    result.append(_row(_('Fixed / recurring transaction'), _('Yes') if item.is_fixed else _('No')))
    if item.fixed_until:
        result.append(_row(_('Repeat until'), item.fixed_until.isoformat()))
    if item.notes:
        result.append(_row(_('Notes'), item.notes))
    return result


def _owned_source(user, transaction_id):
    item = Transaction.objects.filter(user=user, pk=transaction_id, reward_redemption__isnull=True).select_related(
        'bank_account__bank', 'credit_card__account__bank', 'debit_card__account__bank', 'category').first()
    if item is None:
        raise ActionError('invalid_reference')
    if item.splits.exists():
        raise ActionError('split_requires_form')
    category = _category(user, item.category_id)
    account = item.payment_account
    instrument = item.bank_account or item.debit_card or item.credit_card
    if (not account or account.user_id != user.pk or account.bank.user_id != user.pk
            or not instrument or instrument.user_id != user.pk):
        raise ActionError('invalid_reference')
    dependencies = [_state(item), _state(category), _state(account), _state(account.bank), _state(instrument)]
    if category.parent_category_id:
        dependencies.append(_state(category.parent_category))
    return item, category, dependencies


def _saved_transaction_parameters(item):
    """An exact merge baseline; optional values are never reset by omission."""
    return {'title': item.title, 'amount': format(item.amount, '.2f'), 'currency': item.native_currency,
            'date': item.date.isoformat(), 'transaction_type': item.transaction_type,
            'category_id': item.category_id, 'payment_channel': item.payment_channel,
            'account_id': item.bank_account_id, 'credit_card_id': item.credit_card_id,
            'debit_card_id': item.debit_card_id, 'installments': item.installments,
            'is_fixed': item.is_fixed, 'fixed_until': item.fixed_until.isoformat() if item.fixed_until else None,
            'billing_override': item.billing_override, 'notes': item.notes}


def _excessive_schedule(item):
    try:
        validate_occurrences(item)
    except ProjectionLimitExceeded:
        return True
    return False


def _validate_update(user, parameters):
    original, old_category, dependencies = _owned_source(user, parameters['transaction_id'])
    changes = parameters['changes']
    if 'notes' in changes and len(original.notes) > 2000:
        raise ActionError('long_notes_require_form')
    baseline = _saved_transaction_parameters(original)
    values = baseline | changes
    # Unlike creation's optional account context, update's account_id is the
    # saved bank_account field. A channel transition must explicitly clear it.
    if values['payment_channel'] in {'CREDIT_CARD', 'DEBIT_CARD'} and values['account_id'] is not None:
        raise ActionError('invalid_parameters')
    # Validate requested scalars above, then the complete financial form. Long
    # unchanged legacy notes remain untouched instead of being reinterpreted.
    category = _category(user, values['category_id'])
    account, instrument, field = _instrument(user, values)
    if account.currency != baseline['currency'] and 'currency' not in changes:
        raise ActionError('currency_confirmation_required')
    if values['currency'] != account.currency:
        raise ActionError('currency_mismatch')
    dependencies.extend([_state(category), _state(account), _state(account.bank), _state(instrument)])
    if category.parent_category_id:
        dependencies.append(_state(category.parent_category))
    data = model_to_dict(original, fields=TransactionForm.Meta.fields)
    mapping = {'category_id': 'category', 'account_id': 'bank_account',
               'credit_card_id': 'credit_card', 'debit_card_id': 'debit_card'}
    for key, value in changes.items():
        if key != 'currency':
            data[mapping.get(key, key)] = value
    form = _assert_form(TransactionForm(data, user=user, instance=copy(original)))
    requested_fields = {mapping.get(key, key) for key in changes if key != 'currency'}
    changed_fields = []
    for model_field in Transaction._meta.concrete_fields:
        if model_field.name not in requested_fields:
            # Ordinary forms normalize text on binding. A partial action may
            # persist only the fields named in its reviewed changes object.
            setattr(form.instance, model_field.attname, getattr(original, model_field.attname))
        elif getattr(form.instance, model_field.attname) != getattr(original, model_field.attname):
            changed_fields.append(model_field.name)
    if not changed_fields:
        raise ActionError('no_changes')
    previous = {row['label']: row['value'] for row in _transaction_summary(original, old_category)}
    updated = {row['label']: row['value'] for row in _transaction_summary(form.instance, category)}
    summary = [_row(_('Transaction'), original.title),
               _row(_('Transaction date'), original.date.isoformat()),
               _row(_('Current amount'), f'{original.native_currency} {original.amount:.2f}')]
    for label in dict.fromkeys([*previous, *updated]):
        if previous.get(label) != updated.get(label):
            summary.extend([_row(_('%(field)s · before') % {'field': label}, previous.get(label, _('Not set'))),
                            _row(_('%(field)s · after') % {'field': label}, updated.get(label, _('Not set')))])
    if original.is_fixed or original.is_installment_plan:
        summary.append(_row(_('Scope'), _('Updates the source transaction and its scheduled occurrences.')))
    return _ValidatedAction(form, summary, _digest({'parameters': parameters, 'dependencies': dependencies}),
                            original, tuple(changed_fields), _excessive_schedule(original))


def _validate_delete(user, parameters):
    original, category, dependencies = _owned_source(user, parameters['transaction_id'])
    # Notes are not necessary to identify the reviewed deletion and can contain
    # unrestricted legacy text. Keep them out of the provider's review payload.
    shown = copy(original)
    shown.notes = ''
    summary = [_row(_('Action'), _('Delete transaction')),
               *_transaction_summary(shown, category),
               _row(_('Scope'), _('Removes this source transaction and all of its scheduled occurrences from the application. No money is moved at the bank.'))]
    return _ValidatedAction(None, summary, _digest({'parameters': parameters, 'dependencies': dependencies}),
                            original, (), _excessive_schedule(original))


def _validate(user, name, parameters):
    if name == 'transaction.update':
        return _validate_update(user, parameters)
    if name == 'transaction.delete':
        return _validate_delete(user, parameters)
    category = _category(user, parameters['category_id']) if 'category_id' in parameters else None
    dependencies = [_state(category)] if category else []
    if category and category.parent_category_id:
        dependencies.append(_state(category.parent_category))
    original = None
    if name == 'transaction.create':
        account, instrument, field = _instrument(user, parameters)
        if account.currency != parameters['currency']:
            raise ActionError('currency_mismatch')
        dependencies.extend([_state(account), _state(account.bank), _state(instrument)])
        form_data = {key: parameters[key] for key in ('title', 'amount', 'date', 'transaction_type',
                     'payment_channel', 'installments', 'is_fixed', 'fixed_until', 'billing_override', 'notes')}
        form_data.update(category=category.pk, **{field: instrument.pk})
        form = _assert_form(TransactionForm(form_data, user=user))
        summary = _transaction_summary(form.instance, category)
    elif name == 'transaction.categorize':
        original = Transaction.objects.filter(user=user, pk=parameters['transaction_id'],
                     reward_redemption__isnull=True).select_related('bank_account__bank',
                     'credit_card__account__bank', 'debit_card__account__bank', 'category').first()
        if original is None:
            raise ActionError('invalid_reference')
        if original.splits.exists():
            raise ActionError('split_requires_form')
        account = original.payment_account
        instrument = original.bank_account or original.debit_card or original.credit_card
        if (not account or account.user_id != user.pk or account.bank.user_id != user.pk
                or not instrument or instrument.user_id != user.pk):
            raise ActionError('invalid_reference')
        # A stale preview must never overwrite a concurrent edit, even notes
        # or split state that is deliberately absent from the model context.
        dependencies.extend([_state(original), _state(account), _state(account.bank), _state(instrument)])
        previous_category = _category(user, original.category_id)
        dependencies.append(_state(previous_category))
        if previous_category.parent_category_id:
            dependencies.append(_state(previous_category.parent_category))
        data = model_to_dict(original, fields=TransactionForm.Meta.fields)
        data['category'] = category.pk
        form = _assert_form(TransactionForm(data, user=user, instance=original))
        summary = _transaction_summary(form.instance, category)
        summary.insert(0, _row(_('Previous category'), str(previous_category)))
    elif name == 'goal.create':
        form = _assert_form(GoalCreationForm({**parameters, 'reserve_now': False}, user=user))
        item = form.instance
        summary = [_row(_('Name'), item.name),
                   _row(_('Goal amount'), f'{item.currency} {item.target_amount:.2f}'),
                   _row(_('Target date'), item.target_date.isoformat() if item.target_date else _('Not set')),
                   _row(_('Reserved amount'), f'{item.currency} 0.00')]
    else:
        form = _assert_form(CategoryBudgetForm({**parameters, 'category': category.pk}, user=user))
        item = form.instance
        summary = [_row(_('Category'), str(category)), _row(_('Month'), item.month.strftime('%Y-%m')),
                   _row(_('Budget limit'), f'{item.currency} {item.amount:.2f}')]
    return _ValidatedAction(form, summary, _digest({'parameters': parameters, 'dependencies': dependencies}), original)


def _run(user, session_key, conversation, run_id, *, completed=False):
    if run_id is None:
        return None
    run = GenerationRun.objects.filter(pk=_uuid(run_id), conversation=conversation,
                                       conversation__user=user).first()
    if run is None or not constant_time_compare(run.session_digest, _session_digest(user, session_key, generation=True)):
        raise ActionError('not_found', 404)
    allowed = {GenerationRun.Status.COMPLETED} if completed else {GenerationRun.Status.RUNNING, GenerationRun.Status.COMPLETED}
    if run.status not in allowed:
        raise ActionError('generation_not_completed', 409)
    return run


def prepare_action(user, session_key, conversation, name, parameters, *, request_id=None, run_id=None):
    """Validate an untrusted proposal and store only a local review record."""
    session_digest = _session_digest(user, session_key)
    conversation_id = getattr(conversation, 'pk', conversation)
    conversation = Conversation.objects.filter(pk=_uuid(conversation_id), user=user).first()
    if conversation is None:
        raise ActionError('not_found', 404)
    normalized = normalize_parameters(name, parameters)
    run = _run(user, session_key, conversation, run_id)
    request_id = _uuid(request_id) if request_id is not None else uuid.uuid4()
    previous = ActionProposal.objects.filter(conversation=conversation, request_id=request_id).first()
    if previous:
        if (previous.name != name or previous.parameters != normalized
                or previous.generation_run_id != getattr(run, 'pk', None)
                or not constant_time_compare(previous.session_digest, session_digest)):
            raise ActionError('request_conflict', 409)
        return previous
    validated = _validate(user, name, normalized)
    try:
        # No financial saves or synchronization occur while preparing a review.
        with transaction.atomic():
            return ActionProposal.objects.create(conversation=conversation, generation_run=run,
                request_id=request_id, session_digest=session_digest, name=name, parameters=normalized,
                summary=validated.summary, dependency_digest=validated.dependency_digest,
                expires_at=timezone.now() + PROPOSAL_LIFETIME)
    except IntegrityError:
        raise ActionError('request_conflict', 409) from None


def _owned_proposal(user, session_key, proposal_id):
    session_digest = _session_digest(user, session_key)
    proposal = ActionProposal.objects.filter(pk=_uuid(proposal_id), conversation__user=user).first()
    if proposal is None or not constant_time_compare(proposal.session_digest, session_digest):
        raise ActionError('not_found', 404)
    return proposal


def _validation_error(error):
    errors = error.message_dict if hasattr(error, 'message_dict') else {'__all__': error.messages}
    return ActionError('validation_failed', errors={key: [str(value) for value in values]
                                                   for key, values in errors.items()})


def confirm_action(user, session_key, proposal_id):
    """Execute one immutable review after an authenticated CSRF-protected POST.

    The caller owns HTTP authentication, CSRF and deliberate confirmation. A
    model response, tool call or GET must never call this function.
    """
    proposal = _owned_proposal(user, session_key, proposal_id)
    _run(user, session_key, proposal.conversation, proposal.generation_run_id, completed=True)
    if proposal.status == ActionProposal.Status.EXECUTED:
        return proposal
    if proposal.status != ActionProposal.Status.PENDING:
        raise ActionError('proposal_unavailable', 409)
    if proposal.expires_at <= timezone.now():
        raise ActionError('proposal_expired', 409)
    try:
        with transaction.atomic():
            # SQLite ignores SELECT FOR UPDATE; claiming the row before reading
            # financial dependencies acquires its writer lock and prevents a
            # second confirmation from creating a duplicate financial record.
            claimed = ActionProposal.objects.filter(pk=proposal.pk, status=ActionProposal.Status.PENDING,
                                                     expires_at__gt=timezone.now()).update(status=ActionProposal.Status.EXECUTING)
            if not claimed:
                raise ActionError('proposal_unavailable', 409)
            get_user_model().objects.select_for_update().get(pk=user.pk, is_active=True)
            _run(user, session_key, proposal.conversation, proposal.generation_run_id, completed=True)
            normalized = normalize_parameters(proposal.name, proposal.parameters)
            validated = _validate(user, proposal.name, normalized)
            if not constant_time_compare(validated.dependency_digest, proposal.dependency_digest):
                raise ActionError('proposal_changed', 409)
            result_metadata = {}
            if proposal.name == 'transaction.delete':
                item = validated.original
                object_id = item.pk
                item.delete()
                try:
                    sync_user_ledger(user)
                except ProjectionLimitExceeded:
                    if not validated.repairing_projection:
                        raise
                    # Match the ordinary delete route: a legacy excessive
                    # source can be removed while another still blocks sync.
                    result_metadata['warnings'] = ['projection_pending']
                url = reverse('transactions:list')
                result_metadata['operation'] = 'deleted'
            elif proposal.name in {'transaction.create', 'transaction.categorize', 'transaction.update'}:
                item = validated.form.save(commit=False)
                item.full_clean()
                # Form validation may normalize unrelated legacy text. Only the
                # reviewed category is a write in a categorization action.
                if proposal.name == 'transaction.categorize':
                    item.save(update_fields=['category', 'updated_at'])
                elif proposal.name == 'transaction.update':
                    item.save(update_fields=[*validated.changed_fields, 'updated_at'])
                else:
                    item.save()
                try:
                    sync_user_ledger(user)
                except ProjectionLimitExceeded:
                    if not validated.repairing_projection:
                        raise
                    # Match the ordinary update route's explicit repair path.
                    validate_occurrences(item)
                    result_metadata['warnings'] = ['projection_pending']
                url = reverse('transactions:update', args=[item.pk])
                object_id = item.pk
            elif proposal.name == 'goal.create':
                item = create_goal(validated.form.save(commit=False), validated.form.allocation)
                url = reverse('planning:goal_detail', args=[item.pk])
                object_id = item.pk
            else:
                item = save_budget(validated.form.save(commit=False))
                url = reverse('planning:budgets') + f'?month={item.month:%Y-%m}'
                object_id = item.pk
            proposal.status = ActionProposal.Status.EXECUTED
            proposal.result = {'object_id': object_id, 'url': url, **result_metadata}
            proposal.completed_at = timezone.now()
            proposal.save(update_fields=['status', 'result', 'completed_at'])
    except ProjectionLimitExceeded:
        raise ActionError('projection_limit', 409) from None
    except ValidationError as error:
        raise _validation_error(error) from None
    except DatabaseError:
        raise ActionError('storage_unavailable', 503) from None
    return proposal


def cancel_action(user, session_key, proposal_id):
    """Discard a pending proposal without touching any financial record."""
    proposal = _owned_proposal(user, session_key, proposal_id)
    if proposal.status == ActionProposal.Status.CANCELLED:
        return proposal
    changed = ActionProposal.objects.filter(pk=proposal.pk, status=ActionProposal.Status.PENDING).update(
        status=ActionProposal.Status.CANCELLED, completed_at=timezone.now())
    if not changed:
        raise ActionError('proposal_unavailable', 409)
    proposal.refresh_from_db()
    return proposal


def action_choices(user, kind, query='', *, transaction_type=None):
    """Bounded owned lookup metadata; never balances, notes or full history."""
    if (not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False)
            or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists()):
        raise ActionError('unauthorized', 403)
    if not isinstance(query, str) or len(query) > 120:
        raise ActionError('invalid_parameters')
    query = query.strip()
    if transaction_type is not None and transaction_type not in Transaction.TransactionType.values:
        raise ActionError('invalid_parameters')
    if kind == 'categories':
        rows = Category.objects.filter(user=user).filter(Q(parent_category__isnull=True) | Q(parent_category__user=user))
        if transaction_type:
            rows = rows.filter(Q(transaction_type=transaction_type) | Q(transaction_type='') | Q(transaction_type__isnull=True))
        if query:
            rows = rows.filter(name__icontains=query)
        selected = list(rows.order_by('name', 'pk')[:21])
        items = [{'id': row.pk, 'label': row.name, 'transaction_type': row.transaction_type or ''} for row in selected[:20]]
    elif kind == 'accounts':
        rows = BankAccount.objects.filter(user=user, bank__user=user).select_related('bank')
        if query:
            rows = rows.filter(Q(name__icontains=query) | Q(bank__name__icontains=query))
        selected = list(rows.order_by('name', 'pk')[:21])
        items = [{'id': row.pk, 'label': f'{row.name} · {row.bank.name}', 'currency': row.currency,
                  'pix_enabled': row.pix_enabled} for row in selected[:20]]
    elif kind in {'credit_cards', 'debit_cards'}:
        model = CreditCard if kind == 'credit_cards' else DebitCard
        rows = model.objects.filter(user=user, account__user=user, account__bank__user=user).select_related('account__bank')
        if query:
            rows = rows.filter(Q(name__icontains=query) | Q(account__name__icontains=query) | Q(account__bank__name__icontains=query))
        selected = list(rows.order_by('name', 'pk')[:21])
        items = [{'id': row.pk, 'label': f'{row.name} · {row.account.bank.name} · {row.account.name}',
                  'currency': row.account.currency, 'account_id': row.account_id} for row in selected[:20]]
    elif kind == 'transactions':
        if not query:
            raise ActionError('query_required')
        rows = Transaction.objects.filter(user=user, reward_redemption__isnull=True, splits__isnull=True).filter(
            Q(bank_account__user=user, bank_account__bank__user=user)
            | Q(credit_card__user=user, credit_card__account__user=user, credit_card__account__bank__user=user)
            | Q(debit_card__user=user, debit_card__account__user=user, debit_card__account__bank__user=user))
        rows = rows.filter(title__icontains=query).select_related('bank_account', 'credit_card__account', 'debit_card__account')
        if transaction_type:
            rows = rows.filter(transaction_type=transaction_type)
        selected = list(rows.order_by('-date', '-pk')[:21])
        items = [{'id': row.pk, 'label': row.title, 'date': row.date.isoformat(),
                  'amount': format(row.amount, '.2f'), 'currency': row.native_currency,
                  'transaction_type': row.transaction_type} for row in selected[:20]]
    else:
        raise ActionError('unsupported_choice')
    return {'items': items, 'has_more': len(selected) > 20}
