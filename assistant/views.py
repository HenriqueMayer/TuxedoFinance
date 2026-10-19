# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Private local history and honest provider-unavailable recovery."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.vary import vary_on_headers

from assistant.context import ScopeError, collect_context, read_scope, scope_label, sign_normalized_scope
from assistant.forms import CreateConversationForm, SendMessageForm
from assistant.models import Conversation


def _scope(request):
    token = request.POST.get('scope', request.GET.get('scope', ''))
    location = request.POST.get('location', request.GET.get('location'))
    if not token and location is None:
        return '', '', None
    scope = read_scope(request.user, token, location=location)
    return sign_normalized_scope(request.user, scope), scope_label(scope), collect_context(request.user, scope)


def _render(request, conversation=None, *, status=200, error=None, create_form=None):
    try:
        token, label, snapshot = _scope(request)
    except (ScopeError, ValueError) as invalid:
        token, label, snapshot = '', '', None
        error = str(invalid)
        status = 400 if status != 503 else status
    history = Paginator(Conversation.objects.filter(user=request.user), 30).get_page(request.GET.get('page'))
    messages = list(conversation.messages.order_by('-created_at', '-pk')[:201]) if conversation else []
    if len(messages) > 200:
        messages = messages[:200]
        error = error or _('Only the latest 200 messages are displayed.')
    messages.reverse()
    # The UI shows location and its link only. Bounded financial evidence stays
    # in the structured context contract instead of becoming a second dashboard.
    context = {'conversations': history.object_list, 'history_page': history, 'conversation': conversation,
               'chat_messages': messages, 'provider_state': 'disconnected', 'scope': token,
               'scope_label': label, 'context_snapshot': snapshot,
               'create_form': create_form or CreateConversationForm(initial={'scope': token}),
               'send_form': SendMessageForm(initial={'scope': token}), 'error': error}
    template = 'assistant/_content.html' if request.headers.get('X-Tuxedo-Assistant') == 'panel' else 'assistant/index.html'
    return render(request, template, context, status=status)


def _destination(name, token, pk=None):
    path = reverse(name, args=[pk] if pk else None)
    return path + ('?' + urlencode({'scope': token}) if token else '')


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
    conversation = get_object_or_404(Conversation, user=request.user, pk=pk)
    return _render(request, conversation)


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_POST
def create(request):
    form = CreateConversationForm(request.POST)
    try:
        token, _label, _snapshot = _scope(request)
    except (ScopeError, ValueError) as invalid:
        return _render(request, status=400, error=str(invalid), create_form=form)
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
        token, _label, _snapshot = _scope(request)
    except (ScopeError, ValueError) as invalid:
        return _render(request, conversation, status=400, error=str(invalid))
    conversation.delete()
    return redirect(_destination('assistant:index', token))


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_POST
def send(request, pk):
    conversation = get_object_or_404(Conversation, user=request.user, pk=pk)
    # No provider exists: accepting even the user's message would falsely imply
    # a submitted generation. Keep the request recoverable without any write.
    return _render(request, conversation, status=503,
                   error=_('No AI provider is connected. No message was sent or saved.'))


@never_cache
@login_required
@require_GET
def context_snapshot(request):
    try:
        token, label, snapshot = _scope(request)
        if snapshot is None:
            raise ScopeError(_('Open the assistant again from an available workspace.'))
    except (ScopeError, ValueError) as invalid:
        return JsonResponse({'error': str(invalid), 'context_snapshot': None}, status=400)
    return JsonResponse({'scope': token, 'scope_label': label, 'context_snapshot': snapshot})
