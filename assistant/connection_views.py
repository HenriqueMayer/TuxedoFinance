# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owner-scoped connection settings; account linking never enables inference."""
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import TooManyFieldsSent
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from assistant.connections import service
from assistant.models import AuthorizationAttempt, ProviderConnection


def _private(response):
    response['Referrer-Policy'] = 'no-referrer'
    response['Cache-Control'] = 'private, no-store, max-age=0'
    return response


def _problem(request, code):
    if code == 'disabled':
        text = _('Real sign-in is disabled in this delivery. No account was contacted.')
    elif code in {'attempt_expired', 'attempt_used', 'state_invalid', 'invalid_session', 'forbidden'}:
        text = _('This authorization is unavailable. Start again from the original settings tab.')
    elif code == 'too_many_attempts':
        text = _('Finish or cancel an existing authorization before starting another.')
    elif code == 'vault_unavailable':
        text = _('The local credential vault is unavailable. Check its key and permissions before trying again.')
    else:
        text = _('The connection could not be updated. Your financial data and conversations were kept.')
    messages.error(request, text)
    return _private(redirect('assistant:connections'))


@never_cache
@login_required
@require_GET
def index(request):
    pending = []
    attempts = service.pending_authorizations(request.user, request.session.session_key) if request.session.session_key else []
    for attempt in attempts:
        preview = None
        if attempt.status == AuthorizationAttempt.Status.VERIFIED:
            try:
                preview = service.authorization_preview(request.user, request.session.session_key or '', attempt.pk)
            except service.ConnectionError:
                pass
        pending.append({'attempt': attempt, 'preview': preview})
    return _private(render(request, 'assistant/connections.html', {
        'connections': ProviderConnection.objects.filter(user=request.user).order_by('-is_active', '-updated_at'),
        'pending_authorizations': pending,
        'auth_enabled': settings.ASSISTANT_OPENAI_AUTH_ENABLED,
    }))


@never_cache
@login_required
@require_POST
def start(request, pk=None):
    if pk is not None:
        get_object_or_404(ProviderConnection, pk=pk, user=request.user)
    try:
        _attempt, destination = service.begin_authorization(request.user, request.session.session_key or '', pk)
    except service.ConnectionError as error:
        return _problem(request, error.code)
    # Native POST/redirect keeps OAuth outside HTMX and browser DOM history.
    return _private(redirect(destination))


@never_cache
@require_GET
def callback(request):
    # The callback may arrive on 127.0.0.1 without the original localhost
    # session. Only the original authenticated tab can confirm the link.
    try:
        if any(len(request.GET.getlist(key)) != 1 for key in request.GET):
            raise service.ConnectionError('state_invalid')
        service.receive_callback(request.GET.dict())
        outcome = 'received'
    except (service.ConnectionError, TooManyFieldsSent):
        outcome = 'failed'
    response = redirect('assistant:connection-callback-result')
    response['Location'] += '?' + urlencode({'status': outcome})
    return _private(response)


@never_cache
@require_GET
def callback_result(request):
    return _private(render(request, 'assistant/connection_callback.html', {
        'received': request.GET.get('status') == 'received',
    }))


@never_cache
@login_required
@require_POST
def finish(request, pk):
    get_object_or_404(AuthorizationAttempt, pk=pk, user=request.user)
    try:
        service.finish_authorization(request.user, request.session.session_key or '', pk)
    except service.ConnectionError as error:
        return _problem(request, error.code)
    messages.success(request, _('Account linked locally. AI responses remain unavailable in this delivery.'))
    return _private(redirect('assistant:connections'))


@never_cache
@login_required
@require_POST
def cancel(request, pk):
    get_object_or_404(AuthorizationAttempt, pk=pk, user=request.user)
    try:
        service.cancel_authorization(request.user, request.session.session_key or '', pk)
    except service.ConnectionError as error:
        return _problem(request, error.code)
    messages.success(request, _('Authorization cancelled.'))
    return _private(redirect('assistant:connections'))


@never_cache
@login_required
@require_POST
def activate(request, pk):
    get_object_or_404(ProviderConnection, pk=pk, user=request.user)
    try:
        service.activate_connection(request.user, pk)
    except service.ConnectionError as error:
        return _problem(request, error.code)
    messages.success(request, _('Account selected. This does not enable AI responses.'))
    return _private(redirect('assistant:connections'))


@never_cache
@login_required
@require_POST
def disconnect(request, pk):
    get_object_or_404(ProviderConnection, pk=pk, user=request.user)
    try:
        _connection, revoked = service.disconnect_connection(request.user, pk)
    except service.ConnectionError as error:
        return _problem(request, error.code)
    if revoked:
        messages.success(request, _('Account disconnected and renewable access revoked.'))
    else:
        messages.warning(request, _('Local credentials removed. Remote revocation was not confirmed; review app access in ChatGPT settings.'))
    return _private(redirect('assistant:connections'))
