# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owned, idempotent chat runs; provider waits never hold database transactions."""
from importlib import import_module
from dataclasses import replace
from datetime import timedelta
import json
import re
from threading import Lock
import time
from urllib.parse import urlencode
from weakref import WeakValueDictionary

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from assistant.context_request import build_context
from assistant.models import ActionProposal, Conversation, GenerationRun, Message, ProviderConnection
from assistant.providers import get_provider
from assistant.providers.base import CancellationToken, ChatTurn, GenerationRequest, ProviderError, reasoning_efforts, stream_response
from assistant.tooling import financial_tools, recorded_actions, run_tool


CATALOG_SECONDS = 120
MAX_OUTPUT_CHARS = 16000
MAX_RUN_SECONDS = 90
_ERRORS = {'unavailable', 'cancelled', 'provider_error', 'transport_error', 'rate_limited',
           'unauthorized', 'limit_exceeded', 'invalid_model', 'incomplete', 'interrupted',
           'timeout', 'invalid_grant', 'reconnect_required', 'auth_disabled', 'disabled',
           'vault_unavailable', 'storage_unavailable', 'connection_error', 'host_mismatch',
           'request_rejected', 'invalid_response', 'permission_denied', 'invalid_reasoning_effort'}
_LIVE_TOKENS = WeakValueDictionary()
_LIVE_TOKENS_LOCK = Lock()


class ChatError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def _outside_transaction():
    if any(database.in_atomic_block for database in connections.all(initialized_only=True)):
        raise ChatError('transaction_active', 503)


def _safe_code(error):
    code = getattr(error, 'code', 'provider_error')
    return code if code in _ERRORS else 'provider_error'


def _session_digest(user, session_key):
    if (not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False)
            or not isinstance(session_key, str) or not session_key or len(session_key) > 256):
        raise ChatError('unauthorized', 403)
    return salted_hmac('assistant.chat.session.v1', f'{user.pk}:{session_key}', algorithm='sha256').hexdigest()


def _session_authorized(owner, session_key):
    try:
        user = get_user_model().objects.filter(pk=owner.pk, is_active=True).first()
        if user is None:
            return False
        session = import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key).load()
        if str(session.get('_auth_user_id', '')) != str(user.pk):
            return False
        hashes = [user.get_session_auth_hash(), *user.get_session_auth_fallback_hash()]
        return any(constant_time_compare(session.get('_auth_user_hash', ''), value) for value in hashes)
    except Exception:
        return False


def _selected_connection(user, requested=None):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        return None, 'disconnected'
    connection = ProviderConnection.objects.filter(user=user, provider='openai', is_active=True).first()
    if connection is None:
        return None, 'disconnected'
    if requested and str(connection.pk) != str(requested):
        return None, 'reauth'
    if connection.status == ProviderConnection.Status.RECONNECT:
        return connection, 'reauth'
    if connection.status != ProviderConnection.Status.READY:
        return connection, 'disconnected'
    # A stored account selection survives a local service switch. Preserve that
    # identity in the UI without resolving a provider or loading its catalogue.
    if (getattr(settings, 'ASSISTANT_OPENAI_AUTH_ENABLED', False) is not True
            or getattr(settings, 'ASSISTANT_OPENAI_INFERENCE_ENABLED', False) is not True):
        return connection, 'disabled'
    return connection, 'ready'


def composer_state(user, connection_id=None, *, refresh=False):
    """Read account metadata first; only an opted-in eligible account loads models."""
    connection, state = _selected_connection(user, connection_id)
    result = {'provider_state': state, 'error': '', 'models': [],
              'connection_id': str(connection.pk) if connection else ''}
    if state == 'disabled':
        result['error'] = ('auth_disabled' if getattr(settings, 'ASSISTANT_OPENAI_AUTH_ENABLED', False) is not True
                           else 'disabled')
    if state != 'ready':
        return result
    key = f'assistant.models.v2:{user.pk}:{connection.pk}:{connection.updated_at.isoformat()}'
    try:
        models = None if refresh else cache.get(key)
        if models is None:
            _outside_transaction()
            provider = get_provider(user, connection.pk)
            if not getattr(provider, 'available', False):
                result.update(provider_state='reauth', error='unavailable')
                return result
            supplied = provider.list_models()
            if not isinstance(supplied, list):
                raise ChatError('provider_error', 503)
            models, seen = [], set()
            for item in supplied[:100]:
                if (not isinstance(item, dict) or not isinstance(item.get('slug'), str)
                        or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,160}', item['slug'])
                        or not isinstance(item.get('display_name'), str)
                        or not 1 <= len(item['display_name']) <= 160):
                    continue
                if item['slug'] not in seen:
                    efforts = reasoning_efforts(item.get('reasoning_efforts'))
                    normalized = {'slug': item['slug'], 'display_name': item['display_name'],
                                  'reasoning_efforts': efforts}
                    default = item.get('default_reasoning_effort')
                    if isinstance(default, str) and default in efforts:
                        normalized['default_reasoning_effort'] = default
                    models.append(normalized)
                    seen.add(item['slug'])
            cache.set(key, models, CATALOG_SECONDS)
        result['models'] = models
        if not models:
            result.update(provider_state='error', error='models_unavailable')
    except Exception as error:
        code = _safe_code(error)
        result.update(provider_state='reauth' if code in {'unauthorized', 'invalid_grant', 'reconnect_required'}
                      else 'error', error=code)
    return result


def _history(conversation):
    if conversation is None:
        return ()
    # Failed/cancelled input and partial output remain visible locally but are
    # never silently reused as completed history in a later model request.
    completed = (Q(generation_result__status=GenerationRun.Status.COMPLETED)
                 | Q(generation_inputs__status=GenerationRun.Status.COMPLETED)
                 | Q(generation_result__isnull=True, generation_inputs__isnull=True))
    messages = list(Message.objects.filter(completed, conversation=conversation).distinct()
                    .order_by('-created_at', '-pk')[:19])
    return tuple(ChatTurn(message.role, message.content[:4000]) for message in reversed(messages))


def _references(context, scope, include_financial):
    return {'include_financial': bool(include_financial), 'scope_location': scope['location'] if scope else '',
            'captured_at': context.get('captured_at', ''), 'cutoff': context.get('cutoff', ''),
            'references': context.get('references', [])}


def _existing(user, session_key, data, conversation):
    run = GenerationRun.objects.select_related('conversation', 'input_message', 'output_message').filter(
        pk=data['request_id']).first()
    if run is None:
        return None
    if (run.conversation.user_id != user.pk
            or not constant_time_compare(run.session_digest, _session_digest(user, session_key))):
        raise ChatError('request_conflict', 409)
    if (conversation is not None and run.conversation_id != conversation.pk
            or run.input_message.content != data['content'] or run.model_slug != data['model']
            or run.reasoning_effort != data.get('reasoning_effort', '')
            or str(run.connection_id) != str(data['connection_id'])
            or bool(run.context_references.get('include_financial')) != bool(data.get('include_context'))
            or run.context_references.get('scope_location', '') != data.get('_scope_location', '')):
        raise ChatError('request_conflict', 409)
    if run.status == GenerationRun.Status.RUNNING:
        raise ChatError('generation_running', 409)
    return run


def _expire_stale_runs(user, conversation):
    stale = GenerationRun.objects.filter(conversation__user=user, status=GenerationRun.Status.RUNNING,
                                          created_at__lte=timezone.now() - timedelta(seconds=MAX_RUN_SECONDS))
    if conversation is not None:
        stale = stale.filter(conversation=conversation)
    identifiers = list(stale.values_list('pk', flat=True))
    if not identifiers:
        return
    stale.update(status=GenerationRun.Status.FAILED, error_code='interrupted', completed_at=timezone.now())
    with _LIVE_TOKENS_LOCK:
        tokens = [_LIVE_TOKENS.get(str(identifier)) for identifier in identifiers]
    for token in tokens:
        if token is not None:
            token.cancel()


def start_run(user, session_key, data, *, scope=None, conversation=None, language='en', scope_token=''):
    _outside_transaction()
    digest = _session_digest(user, session_key)
    data = {**data, '_scope_location': scope['location'] if scope else ''}
    original_conversation = conversation
    if conversation is not None and conversation.user_id != user.pk:
        raise ChatError('not_found', 404)
    # A process exit cannot leave a conversation permanently occupied. A later
    # deliberate send marks expired in-flight work interrupted before retrying.
    _expire_stale_runs(user, conversation)
    existing = _existing(user, session_key, data, conversation)
    if existing:
        return existing, ReplayStream(existing, user, session_key, scope_token)
    state = composer_state(user, data['connection_id'])
    if state['provider_state'] != 'ready':
        raise ChatError(state['error'] or 'unavailable', 503)
    model = next((model for model in state['models'] if model['slug'] == data['model']), None)
    if model is None:
        raise ChatError('invalid_model')
    effort = data.get('reasoning_effort', '')
    if not isinstance(effort, str) or effort and effort not in model['reasoning_efforts']:
        raise ChatError('invalid_reasoning_effort')
    selected, status = _selected_connection(user, data['connection_id'])
    if status != 'ready':
        raise ChatError('unauthorized', 403)
    provider = get_provider(user, selected.pk)
    if not getattr(provider, 'available', False):
        raise ChatError('unavailable', 503)
    context = build_context(user, scope, bool(data.get('include_context')))
    # Workspace access is a tool capability, not a copy of every financial row.
    # The current page is orientation only; tools can read other owned areas.
    context['application_access'] = {'read': 'all_owned_financial_workspaces',
        'simulations': 'available_without_saving_or_confirmation',
        'writes': 'separate_review_and_confirmation_required'}
    actions = recorded_actions(user, conversation)
    if actions:
        context['recorded_actions'] = actions
        # Keep the original financial evidence budget authoritative. Recent
        # action status is optional when a bounded page snapshot fills it.
        while context['recorded_actions'] and len(json.dumps(context, ensure_ascii=True, separators=(',', ':'))) > 32000:
            context['recorded_actions'].pop()
        if not context['recorded_actions']:
            del context['recorded_actions']
    request = GenerationRequest(json.dumps(context, ensure_ascii=True, separators=(',', ':')),
                                history=_history(conversation) + (ChatTurn('user', data['content']),),
                                language='pt-br' if language.lower().startswith('pt') else 'en', model=data['model'],
                                reasoning_effort=effort)
    try:
        with transaction.atomic():
            if conversation is None:
                conversation = Conversation.objects.create(user=user)
            message = Message.objects.create(conversation=conversation, role=Message.Role.USER, content=data['content'])
            run = GenerationRun.objects.create(
                pk=data['request_id'], conversation=conversation, connection=selected, model_slug=data['model'],
                reasoning_effort=effort,
                input_message=message, session_digest=digest,
                context_references=_references(context, scope, data.get('include_context')))
            Conversation.objects.filter(pk=conversation.pk, user=user).update(updated_at=timezone.now())
    except IntegrityError:
        existing = _existing(user, session_key, data, original_conversation)
        if existing:
            return existing, ReplayStream(existing, user, session_key, scope_token)
        raise ChatError('generation_running', 409) from None
    except DatabaseError:
        raise ChatError('storage_unavailable', 503) from None
    return run, RunStream(run, user, session_key, provider, request, scope_token)


def cancel_run(user, session_key, run_id):
    _outside_transaction()
    digest = _session_digest(user, session_key)
    run = GenerationRun.objects.select_related('conversation').filter(pk=run_id, conversation__user=user).first()
    if run is None:
        raise ChatError('not_found', 404)
    if not constant_time_compare(digest, run.session_digest):
        raise ChatError('unauthorized', 403)
    GenerationRun.objects.filter(pk=run.pk, status=GenerationRun.Status.RUNNING).update(
        status=GenerationRun.Status.CANCELLED, error_code='cancelled', completed_at=timezone.now())
    # Complete this request's DB reads before waking the streaming writer.
    # SQLite shared-cache connections cannot upgrade a concurrent table read
    # while that writer persists the partial response after cancellation.
    run.refresh_from_db()
    # The DB state remains authoritative across workers. In the serving process
    # also close a blocked transport immediately; other workers recheck the DB
    # between chunks and retain the provider's bounded read/deadline behavior.
    with _LIVE_TOKENS_LOCK:
        token = _LIVE_TOKENS.get(str(run.pk))
    if token is not None:
        token.cancel()
    return run


def _meta(run, user, scope_token):
    detail = reverse('assistant:detail', args=[run.conversation_id])
    if scope_token:
        detail += '?' + urlencode({'scope': scope_token})
    return {'owner': str(user.pk), 'run_id': str(run.pk), 'conversation_id': str(run.conversation_id),
            'detail_url': detail}


class ReplayStream:
    def __init__(self, run, user, session_key, scope_token):
        self.run, self.user, self.session_key, self.scope_token = run, user, session_key, scope_token

    def _authorized(self):
        connection, state = _selected_connection(self.user, self.run.connection_id)
        return (state == 'ready' and connection is not None and _session_authorized(self.user, self.session_key)
                and Conversation.objects.filter(pk=self.run.conversation_id, user=self.user).exists())

    def __iter__(self):
        if not self._authorized():
            yield 'error', {'run_id': str(self.run.pk), 'code': 'cancelled'}
            return
        yield 'meta', _meta(self.run, self.user, self.scope_token)
        if not self._authorized():
            yield 'error', {'run_id': str(self.run.pk), 'code': 'cancelled'}
            return
        if self.run.output_message_id:
            yield 'text', {'delta': self.run.output_message.content}
        if not self._authorized():
            yield 'error', {'run_id': str(self.run.pk), 'code': 'cancelled'}
            return
        if self.run.status == GenerationRun.Status.COMPLETED:
            yield 'done', {'run_id': str(self.run.pk), 'status': self.run.status,
                           'references': self.run.context_references.get('references', [])}
        else:
            yield 'error', {'run_id': str(self.run.pk), 'code': self.run.error_code or 'interrupted'}


class RunStream:
    """Closeable even before iteration starts, so abandoned responses cancel."""
    def __init__(self, run, user, session_key, provider, request, scope_token):
        self.run, self.user, self.session_key = run, user, session_key
        self.provider, self.request, self.scope_token = provider, request, scope_token
        self.cancellation = CancellationToken()
        self.request = replace(request, tools=financial_tools(), tool_runner=self._tool)
        with _LIVE_TOKENS_LOCK:
            _LIVE_TOKENS[str(run.pk)] = self.cancellation
        self.output = ''
        self.started = time.monotonic()
        self.finished = False
        self.events = self._events()

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.events)

    def _authorized(self):
        current = GenerationRun.objects.filter(pk=self.run.pk, conversation__user=self.user,
                                               status=GenerationRun.Status.RUNNING).exists()
        if not current:
            return False
        connection, state = _selected_connection(self.user, self.run.connection_id)
        if state != 'ready' or connection is None:
            return False
        return _session_authorized(self.user, self.session_key)

    def _tool(self, name, arguments):
        # A provider receives only a proposal callback, never a confirm/write
        # function. Reauthorize around local reads just like streamed deltas.
        self.cancellation.raise_if_cancelled()
        if not self._authorized():
            self.cancellation.cancel()
            self.cancellation.raise_if_cancelled()
        if time.monotonic() - self.started > MAX_RUN_SECONDS:
            raise ProviderError('timeout')
        result = run_tool(self.user, self.session_key, self.run, name, arguments)
        self.cancellation.raise_if_cancelled()
        if not self._authorized():
            self.cancellation.cancel()
            self.cancellation.raise_if_cancelled()
        # References come from server calculations, never generated message
        # links. Retain them for the transcript/replay without copying figures.
        references = list(self.run.context_references.get('references', []))
        from core.navigation import safe_local_url
        for source in result.get('references', []):
            if (isinstance(source, dict) and isinstance(source.get('label'), str)
                    and len(source['label']) <= 160 and safe_local_url(source.get('url'))
                    and not any(row['url'] == source['url'] for row in references)
                    and len(references) < 20):
                references.append({'label': source['label'], 'url': source['url']})
        self.run.context_references = {**self.run.context_references, 'references': references,
                                      'financial_tools_available': True}
        GenerationRun.objects.filter(pk=self.run.pk, status=GenerationRun.Status.RUNNING).update(
            context_references=self.run.context_references)
        return result

    def _finish(self, status, code=''):
        if self.finished:
            return self.run
        _outside_transaction()
        with transaction.atomic():
            GenerationRun.objects.filter(pk=self.run.pk, status=GenerationRun.Status.RUNNING).update(
                status=status, error_code=code, completed_at=timezone.now())
            current = GenerationRun.objects.filter(pk=self.run.pk, conversation__user=self.user).first()
            if current is None:
                self.finished = True
                return self.run
            if self.output and current.output_message_id is None:
                message = Message.objects.create(conversation_id=current.conversation_id,
                                                 role=Message.Role.ASSISTANT, content=self.output)
                GenerationRun.objects.filter(pk=current.pk, output_message__isnull=True).update(output_message=message)
                current.output_message = message
            if current.status == GenerationRun.Status.COMPLETED and current.output_message_id:
                ActionProposal.objects.filter(generation_run=current, conversation_id=current.conversation_id,
                                               message__isnull=True).update(message_id=current.output_message_id)
            Conversation.objects.filter(pk=current.conversation_id, user=self.user).update(updated_at=timezone.now())
        self.run, self.finished = current, True
        return current

    def _failure(self, code):
        cancelled = code == 'cancelled'
        result = self._finish(GenerationRun.Status.CANCELLED if cancelled else GenerationRun.Status.FAILED, code)
        return 'error', {'run_id': str(result.pk), 'code': result.error_code or code}

    def _events(self):
        iterator = None
        try:
            if not self._authorized():
                yield self._failure('cancelled')
                return
            yield 'meta', _meta(self.run, self.user, self.scope_token)
            iterator = iter(stream_response(self.provider, self.request, self.cancellation))
            while True:
                if not self._authorized():
                    yield self._failure('cancelled')
                    return
                if time.monotonic() - self.started > MAX_RUN_SECONDS:
                    yield self._failure('timeout')
                    return
                try:
                    event = next(iterator)
                except StopIteration:
                    yield self._failure('incomplete')
                    return
                # Reauthorize after a blocking read and before exposing its text.
                if not self._authorized():
                    yield self._failure('cancelled')
                    return
                if time.monotonic() - self.started > MAX_RUN_SECONDS:
                    yield self._failure('timeout')
                    return
                if event.kind == 'text':
                    if len(self.output) + len(event.text) > MAX_OUTPUT_CHARS:
                        yield self._failure('limit_exceeded')
                        return
                    self.output += event.text
                    yield 'text', {'delta': event.text}
                elif event.kind == 'error':
                    yield self._failure(_safe_code(event))
                    return
                elif event.kind == 'done':
                    if not self.output:
                        yield self._failure('incomplete')
                        return
                    result = self._finish(GenerationRun.Status.COMPLETED)
                    if result.status != GenerationRun.Status.COMPLETED:
                        yield 'error', {'run_id': str(result.pk), 'code': result.error_code or 'cancelled'}
                    else:
                        yield 'done', {'run_id': str(result.pk), 'status': result.status,
                                       'references': result.context_references.get('references', [])}
                    return
        except GeneratorExit:
            self.cancellation.cancel()
            try:
                self._finish(GenerationRun.Status.CANCELLED, 'cancelled')
            except Exception:
                pass
            raise
        except Exception as error:
            try:
                yield self._failure('storage_unavailable' if isinstance(error, DatabaseError) else _safe_code(error))
            except Exception:
                yield 'error', {'run_id': str(self.run.pk), 'code': 'storage_unavailable'}
        finally:
            self.cancellation.cancel()
            with _LIVE_TOKENS_LOCK:
                _LIVE_TOKENS.pop(str(self.run.pk), None)
            if iterator is not None and callable(getattr(iterator, 'close', None)):
                try:
                    iterator.close()
                except Exception:
                    pass

    def close(self):
        self.cancellation.cancel()
        try:
            self.events.close()
        finally:
            with _LIVE_TOKENS_LOCK:
                _LIVE_TOKENS.pop(str(self.run.pk), None)
            if not self.finished:
                try:
                    self._finish(GenerationRun.Status.CANCELLED, 'cancelled')
                except Exception:
                    pass
