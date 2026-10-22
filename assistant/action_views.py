# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit owner-confirmed local actions; a model response cannot execute one."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from assistant import action_service
from assistant.context import ScopeError
from assistant.models import ActionProposal
from assistant.views import _destination, _render, _scope


def _problem(code):
    if code == 'proposal_expired':
        return _('This proposal expired. Ask Tuxedo to prepare a new one.')
    if code == 'proposal_changed':
        return _('The financial records changed. Ask Tuxedo to prepare a new proposal.')
    if code == 'unauthorized':
        return _('Your session changed. Reopen the conversation before continuing.')
    return _('This proposal could not be applied. Review its details or ask Tuxedo for a new one.')


def _apply(request, pk, action):
    proposal = get_object_or_404(ActionProposal.objects.select_related('conversation'),
                                 pk=pk, conversation__user=request.user)
    # Only an opaque proposal identity is accepted. Amounts, record IDs and
    # action parameters are always reloaded and revalidated by the service.
    if (set(request.POST) - {'scope', 'location', 'csrfmiddlewaretoken'}
            or any(len(request.POST.getlist(key)) != 1 for key in request.POST)):
        return _render(request, proposal.conversation, status=400, error=_problem('invalid_request'))
    try:
        token, _label, _snapshot, _normalized = _scope(request)
    except (ScopeError, ValueError):
        return _render(request, proposal.conversation, status=400, error=_('Invalid assistant context.'))
    try:
        action(request.user, request.session.session_key, proposal.pk)
    except action_service.ActionError as error:
        if error.status == 404:
            raise Http404 from None
        if error.status == 403:
            raise PermissionDenied from None
        return _render(request, proposal.conversation, status=error.status, error=_problem(error.code))
    except Exception:
        # Debug pages and raw validation exceptions can contain financial
        # parameters. Recover through the owned transcript with neutral copy.
        return _render(request, proposal.conversation, status=503, error=_problem('storage_unavailable'))
    return redirect(_destination('assistant:detail', token, proposal.conversation_id))


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_POST
def confirm(request, pk):
    return _apply(request, pk, action_service.confirm_action)


@never_cache
@vary_on_headers('X-Tuxedo-Assistant')
@login_required
@require_POST
def cancel(request, pk):
    return _apply(request, pk, action_service.cancel_action)
