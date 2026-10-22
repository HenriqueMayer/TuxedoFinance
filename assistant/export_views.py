# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Authenticated native downloads and clipboard reads without provider access."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from django.utils.translation import get_language, override
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from assistant.export import conversation_markdown, export_messages, message_markdown
from assistant.models import Conversation


def _response(request, conversation, message=None):
    if request.method == 'HEAD':
        response = HttpResponse(content_type='text/markdown; charset=utf-8')
    else:
        last_key = None if message else conversation.messages.order_by('-created_at', '-pk').values_list('created_at', 'pk').first()
        chunks = message_markdown(message) if message else conversation_markdown(conversation, last_key)
        language = get_language()

        def localized():
            with override(language):
                yield from chunks

        response = StreamingHttpResponse(localized(), content_type='text/markdown; charset=utf-8')
    identity = f'message-{message.pk}' if message else f'conversation-{conversation.pk}'
    response['Content-Disposition'] = f'attachment; filename="tuxedo-{identity}.md"'
    response['Cache-Control'] = 'private, no-store, no-cache, max-age=0'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Tuxedo-Assistant-User'] = str(request.user.pk)
    response['X-Tuxedo-Assistant-Session'] = salted_hmac('assistant.ui.session.v1',
        f'{request.user.pk}:{request.session.session_key or ""}', algorithm='sha256').hexdigest()
    return response


@never_cache
@login_required
@require_safe
def conversation(request, pk):
    owned = get_object_or_404(Conversation, user=request.user, pk=pk)
    return _response(request, owned)


@never_cache
@login_required
@require_safe
def message(request, pk, message_pk):
    owned = get_object_or_404(Conversation, user=request.user, pk=pk)
    item = get_object_or_404(export_messages(owned), pk=message_pk)
    return _response(request, owned, item)
