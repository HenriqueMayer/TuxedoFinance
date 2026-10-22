# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Private Markdown exports from stored messages, never rendered chat HTML."""
from django.db.models import Prefetch, Q
from django.utils.translation import gettext as _

from assistant.models import ActionProposal, GenerationRun
from core.navigation import safe_local_url


def _inline(value):
    # Metadata is our Markdown, whereas message content below deliberately
    # retains the author's exact source, including spacing and code fences.
    value = ' '.join(str(value).splitlines())
    for character in '\\`*_{}[]<>#':
        value = value.replace(character, '\\' + character)
    return value


def _run(message):
    if message.role != 'assistant':
        return None
    try:
        return message.generation_result
    except GenerationRun.DoesNotExist:
        return None


def message_markdown(message):
    """Keep raw source first; attach only completed, server-owned evidence."""
    yield message.content
    run = _run(message)
    if run is None:
        return
    if run.status != GenerationRun.Status.COMPLETED:
        states = {'running': _('In progress'), 'cancelled': _('Stopped'), 'failed': _('Not completed')}
        yield '\n\n> ' + _('Partial response') + ' · ' + states.get(run.status, _('Not completed'))
        return
    references = run.context_references.get('references', []) if isinstance(run.context_references, dict) else []
    selected = []
    if isinstance(references, list):
        for reference in references[:20]:
            if not isinstance(reference, dict) or not isinstance(reference.get('label'), str):
                continue
            url = safe_local_url(reference.get('url'))
            if url:
                # Angle-delimited destinations preserve parentheses in local
                # paths while escaping metacharacters in human labels.
                selected.append(f'- [{_inline(reference["label"])}](<{url.replace(">", "%3E").replace("<", "%3C")}>)')
    if selected:
        yield '\n\n### ' + _('References') + '\n\n' + '\n'.join(selected)
    for proposal in getattr(message, 'export_proposals', []):
        if (proposal.generation_run_id != run.pk or proposal.conversation_id != message.conversation_id
                or run.output_message_id != message.pk):
            continue
        status = {'executed': _('Completed'), 'cancelled': _('Discarded')}.get(proposal.status, _('Review before confirming'))
        yield '\n\n### ' + _('Proposed action') + ' — ' + status + '\n\n'
        for row in proposal.summary if isinstance(proposal.summary, list) else []:
            if isinstance(row, dict) and isinstance(row.get('label'), str) and isinstance(row.get('value'), str):
                yield f'- **{_inline(row["label"])}:** {_inline(row["value"])}\n'
        destination = safe_local_url(proposal.result_url) if proposal.status == 'executed' else ''
        if destination:
            label = _('View transactions') if proposal.result.get('operation') == 'deleted' else _('View saved record')
            yield f'\n[{label}](<{destination.replace(">", "%3E").replace("<", "%3C")}>)'
        warnings = proposal.result.get('warnings', []) if isinstance(proposal.result, dict) else []
        if isinstance(warnings, list) and 'projection_pending' in warnings:
            yield '\n\n> ' + _('The record changed, but financial projections need review.')


def export_messages(conversation):
    return conversation.messages.select_related('generation_result').prefetch_related(Prefetch(
        'action_proposals', to_attr='export_proposals', queryset=ActionProposal.objects.filter(
            conversation=conversation, generation_run__status=GenerationRun.Status.COMPLETED)))


def conversation_markdown(conversation, last_key):
    """Export all history with bounded queries and no cursor held while sending.

    The upper message key is fixed at request start. Concurrent new sends belong
    to the next export; the UI's 200-message display limit never truncates this.
    """
    yield '# ' + _inline(conversation.title or _('New conversation')) + '\n\n'
    last = last_key
    if last is None:
        return
    bound = Q(created_at__lt=last[0]) | Q(created_at=last[0], pk__lte=last[1])
    cursor = None
    while True:
        query = export_messages(conversation).filter(bound)
        if cursor:
            query = query.filter(Q(created_at__gt=cursor[0]) | Q(created_at=cursor[0], pk__gt=cursor[1]))
        batch = list(query.order_by('created_at', 'pk')[:100])
        if not batch:
            break
        for message in batch:
            role = _('You') if message.role == 'user' else _('Tuxedo assistant')
            yield '## ' + role + '\n\n'
            yield from message_markdown(message)
            yield '\n\n---\n\n'
        cursor = batch[-1].created_at, batch[-1].pk
        if cursor == last:
            break
