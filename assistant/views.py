# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Private conversation history, explicit context and closeable SSE generation."""
import json
from urllib.parse import urlencode
import uuid

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.vary import vary_on_headers

from assistant import chat
from assistant.context import ScopeError, read_scope, scope_label, sign_normalized_scope
from assistant.context_request import build_context
from assistant.forms import CreateConversationForm, SendMessageForm
from assistant.models import Conversation, GenerationRun


def _scope(request, *, include_financial=False):
    token = request.POST.get('scope', request.GET.get('scope', ''))
    location = request.POST.get('location', request.GET.get('location')) or None
    if not token and location is None:
        return '', '', None, None
    scope = read_scope(request.user, token, location=location)
    return (sign_normalized_scope(request.user, scope), scope_label(scope),
            build_context(request.user, scope, include_financial), scope)


def _render(request, conversation=None, *, status=200, error=None, create_form=None, send_form=None):
    try:
        token, label, snapshot, scope = _scope(request)
    except (ScopeError, ValueError):
        token, label, snapshot, scope = '', '', None, None
        error = _('This assistant context is no longer available. Open it again from the workspace.')
        status = 400 if status != 503 else status
    history = Paginator(Conversation.objects.filter(user=request.user), 30).get_page(request.GET.get('page'))
    messages = list(conversation.messages.order_by('-created_at', '-pk')[:201]) if conversation else []
    if len(messages) > 200:
        messages = messages[:200]
        error = error or _('Only the latest 200 messages are displayed.')
    messages.reverse()
    message_ids = [message.pk for message in messages]
    runs = list(GenerationRun.objects.filter(Q(input_message_id__in=message_ids)
                | Q(output_message_id__in=message_ids), conversation=conversation)) if conversation else []
    by_message = {}
    for run in runs:
        by_message[run.input_message_id] = run
        if run.output_message_id:
            by_message[run.output_message_id] = run
    for message in messages:
        run = by_message.get(message.pk)
        message.generation_status = run.status if run else GenerationRun.Status.COMPLETED
        message.generation_error = run.error_code if run else ''
        message.reference_sources = (run.context_references.get('references', [])
                                     if run and run.status == GenerationRun.Status.COMPLETED
                                     and message.role == 'assistant' else [])
    state = chat.composer_state(request.user)
    selected = request.POST.get('model', request.GET.get('model', ''))
    if selected not in {model['slug'] for model in state['models']}:
        selected = ''
    request_id = str(uuid.uuid4())
    auto_id = 'assistant-panel-%s' if request.headers.get('X-Tuxedo-Assistant') == 'panel' else 'assistant-page-%s'
    if send_form is None:
        send_form = SendMessageForm(models=state['models'], auto_id=auto_id, initial={
            'scope': token, 'location': scope['location'] if scope else '', 'model': selected,
            'connection_id': state['connection_id'], 'request_id': request_id})
    else:
        send_form.auto_id = auto_id
        request_id = str(send_form.data.get('request_id') or request_id)
    context = {'conversations': history.object_list, 'history_page': history, 'conversation': conversation,
               'chat_messages': messages, 'provider_state': state['provider_state'], 'provider_error': state['error'],
               'models': state['models'], 'selected_model': selected, 'connection_id': state['connection_id'],
               'request_id': request_id, 'run_by_message': by_message, 'scope': token, 'scope_label': label,
               'scope_location': scope['location'] if scope else '', 'context_snapshot': snapshot,
               'create_form': create_form or CreateConversationForm(initial={'scope': token}),
               'send_form': send_form, 'error': error}
    template = 'assistant/_content.html' if request.headers.get('X-Tuxedo-Assistant') == 'panel' else 'assistant/index.html'
    return render(request, template, context, status=status)


def _destination(name, token, pk=None):
    path = reverse(name, args=[pk] if pk else None)
    return path + ('?' + urlencode({'scope': token}) if token else '')


def _wants_stream(request):
    return 'text/event-stream' in request.headers.get('Accept', '')


def _send_problem(request, conversation, code, *, status=400, form=None):
    if _wants_stream(request) and (status != 400 or form is None):
        return JsonResponse({'error': code, 'errors': form.errors.get_json_data() if form else {}}, status=status)
    message = (_('No AI provider is connected. No message was sent or saved.') if code == 'unavailable' else
               _('The message could not be sent. Review the form and try again.'))
    return _render(request, conversation, status=status, error=message, send_form=form)


class _SSEStream:
    def __init__(self, stream):
        self.stream, self.iterator = stream, iter(stream)

    def __iter__(self):
        return self

    def __next__(self):
        kind, data = next(self.iterator)
        return f'event: {kind}\ndata: {json.dumps(data, ensure_ascii=True, separators=(",", ":"))}\n\n'.encode('utf-8')

    def close(self):
        if callable(getattr(self.stream, 'close', None)):
            self.stream.close()
        elif callable(getattr(self.iterator, 'close', None)):
            self.iterator.close()


def _send(request, conversation=None):
    state = chat.composer_state(request.user, request.POST.get('connection_id') or None)
    if state['provider_state'] != 'ready':
        return _send_problem(request, conversation, 'unavailable', status=503)
    form = SendMessageForm(request.POST, models=state['models'])
    if not form.is_valid():
        return _send_problem(request, conversation, 'invalid_form', form=form)
    try:
        token, _label, _snapshot, scope = _scope(request)
        run, stream = chat.start_run(request.user, request.session.session_key, form.cleaned_data,
                                     scope=scope, conversation=conversation,
                                     language=getattr(request, 'LANGUAGE_CODE', 'en'), scope_token=token)
    except chat.ChatError as error:
        return _send_problem(request, conversation, error.code, status=error.status, form=form)
    except (ScopeError, ValueError):
        return _send_problem(request, conversation, 'invalid_context', form=form)
    except Exception:
        # A local DEBUG response must not expose adapter credentials or context.
        return _send_problem(request, conversation, 'provider_error', status=503, form=form)
    if _wants_stream(request):
        response = StreamingHttpResponse(_SSEStream(stream), content_type='text/event-stream; charset=utf-8')
        response['X-Accel-Buffering'] = 'no'
        response['Cache-Control'] = 'private, no-store, no-cache, max-age=0'
        response['Referrer-Policy'] = 'no-referrer'
        return response
    try:
        for _kind, _data in stream:
            pass
    finally:
        if callable(getattr(stream, 'close', None)):
            stream.close()
    destination = _destination('assistant:detail', token, run.conversation_id)
    return redirect(destination + ('&' if '?' in destination else '?') + urlencode({'model': run.model_slug}))


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_GET
def index(request):
    return _render(request)


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_GET
def detail(request, pk):
    return _render(request, get_object_or_404(Conversation, user=request.user, pk=pk))


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_POST
def create(request):
    form = CreateConversationForm(request.POST)
    try:
        token, _label, _snapshot, _normalized = _scope(request)
    except (ScopeError, ValueError):
        return _render(request, status=400, error=_('Invalid assistant context.'), create_form=form)
    if not form.is_valid():
        return _render(request, status=400, create_form=form)
    conversation = Conversation.objects.create(user=request.user, title=form.cleaned_data['title'])
    return redirect(_destination('assistant:detail', token, conversation.pk))


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_POST
def delete(request, pk):
    conversation = get_object_or_404(Conversation, user=request.user, pk=pk)
    try:
        token, _label, _snapshot, _normalized = _scope(request)
    except (ScopeError, ValueError):
        return _render(request, conversation, status=400, error=_('Invalid assistant context.'))
    conversation.delete()
    return redirect(_destination('assistant:index', token))


@never_cache
@vary_on_headers('Accept', 'X-Tuxedo-Assistant')
@login_required
@require_POST
def send(request, pk):
    return _send(request, get_object_or_404(Conversation, user=request.user, pk=pk))


@never_cache
@vary_on_headers('Accept', 'X-Tuxedo-Assistant')
@login_required
@require_POST
def send_new(request):
    return _send(request)


@never_cache
@login_required
@require_GET
def models(request):
    return JsonResponse(chat.composer_state(request.user, request.GET.get('connection_id'),
                                           refresh=request.GET.get('refresh') == '1'))


@never_cache
@login_required
@require_POST
def cancel_run(request, pk):
    try:
        run = chat.cancel_run(request.user, request.session.session_key, pk)
    except chat.ChatError as error:
        return JsonResponse({'error': error.code}, status=error.status)
    except Exception:
        return JsonResponse({'error': 'storage_unavailable'}, status=503)
    if 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'run_id': str(run.pk), 'status': run.status})
    return redirect('assistant:detail', pk=run.conversation_id)


@never_cache
@login_required
@require_GET
def context_snapshot(request):
    try:
        token, label, snapshot, _normalized = _scope(
            request, include_financial=request.GET.get('include_context') == '1')
        if snapshot is None:
            raise ScopeError(_('Open the assistant again from an available workspace.'))
    except (ScopeError, ValueError) as invalid:
        return JsonResponse({'error': str(invalid), 'context_snapshot': None}, status=400)
    return JsonResponse({'scope': token, 'scope_label': label, 'context_snapshot': snapshot})
