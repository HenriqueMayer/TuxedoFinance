# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from collections import Counter, defaultdict
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _

from banking.models import BankAccount, BankMovement, CardInvoice
from categories.models import Category
from core.navigation import return_url, with_return_url
from ingestion.forms import ConfirmationForm, MappingForm, ReviewRowForm, UploadForm
from ingestion.models import ExternalStatementIdentity, ImportBatch
from ingestion.services import confirm_batch, decision_digest, map_csv_batch, reconciliation, save_review, stage_statement, undo_batch


def _batch(user, pk):
    return get_object_or_404(ImportBatch.objects.select_related('account__bank', 'user'), user=user, pk=pk)


def _destination(batch):
    return reverse('ingestion:mapping' if batch.status == 'STAGED' else 'ingestion:review' if batch.status == 'READY' else 'ingestion:detail', args=[batch.pk])


def _error(form, error):
    if hasattr(error, 'message_dict'):
        for values in error.message_dict.values():
            for value in values:
                form.add_error(None, value)
    else:
        form.add_error(None, error)


@login_required
@never_cache
@require_http_methods(['GET'])
def history(request):
    # The review gate pauses writes, but never hides posted source provenance.
    query = request.GET.get('q', '').strip()[:200]
    batches = ImportBatch.objects.filter(user=request.user, status__in=['CONFIRMED', 'UNDONE']).select_related('account__bank')
    if query:
        batches = batches.filter(Q(file_name__icontains=query) | Q(account__name__icontains=query) | Q(account__bank__name__icontains=query))
    return render(request, 'ingestion/history.html', {
        'batches': Paginator(batches, 20).get_page(request.GET.get('page')), 'query': query,
    })


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def index(request):
    shortcut = request.GET.get('account', '')
    account = BankAccount.objects.filter(user=request.user, pk=int(shortcut)).first() if shortcut.isascii() and shortcut.isdecimal() and len(shortcut) <= 12 else None
    form = UploadForm(request.POST or None, request.FILES or None, user=request.user, initial={'account': account.pk} if account else {})
    if request.method == 'POST' and form.is_valid():
        cleaned = form.cleaned_data
        try:
            batch, created = stage_statement(request.user, cleaned['account'].pk,
                cleaned['statement'].read(2 * 1024 * 1024 + 1), cleaned['statement'].name,
                cleaned['file_format'], cleaned['encoding'], closing_balance=cleaned['closing_balance'], closing_date=cleaned['closing_date'])
            if not created:
                messages.info(request, _('This exact file already has an active import for this account. Its existing review is shown.'))
            return redirect(with_return_url(_destination(batch), return_url(request, '')))
        except ValidationError as error:
            _error(form, error)
    batches = ImportBatch.objects.filter(user=request.user).select_related('account__bank')
    page = Paginator(batches, 20).get_page(request.GET.get('page'))
    return render(request, 'ingestion/index.html', {'form': form, 'batches': page, 'return_url': return_url(request, '')})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def mapping(request, pk):
    batch = _batch(request.user, pk)
    if batch.status not in ('STAGED', 'READY') or batch.file_format != 'CSV':
        return redirect(with_return_url(_destination(batch), return_url(request, '')))
    initial = {**batch.mapping, 'amount_mode': 'signed' if batch.mapping.get('amount_column') else 'separate' if batch.mapping else ''}
    previous = ImportBatch.objects.filter(user=request.user, account=batch.account, file_format='CSV',
        status='CONFIRMED', encoding=batch.encoding, headers=batch.headers).exclude(pk=batch.pk).first()
    if previous and previous.metadata.get('delimiter') != batch.metadata.get('delimiter'):
        previous = None
    if previous:
        previous_choices = {**previous.mapping, 'amount_mode': 'signed' if previous.mapping.get('amount_column') else 'separate'}
        if not MappingForm(previous_choices, headers=batch.headers).is_valid():
            previous = None
    reused = bool(previous and request.GET.get('reuse') == '1')
    if reused:
        # Reuse only prepares owned compatible choices. The explicit parse
        # submission still validates this file and replaces pending decisions.
        initial = previous_choices
    form = MappingForm(request.POST or None, headers=batch.headers, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            map_csv_batch(request.user, batch.pk, form.mapping())
            return redirect(with_return_url(reverse('ingestion:review', args=[batch.pk]), return_url(request, '')))
        except ValidationError as error:
            _error(form, error)
    # Original text is escaped and shown only inside this owned local review.
    preview = batch.raw_text.splitlines()[:6]
    return render(request, 'ingestion/mapping.html', {'batch': batch, 'form': form, 'preview': preview,
        'previous_mapping': previous, 'reused_mapping': reused, 'return_url': return_url(request, ''),
        'cancel_url': return_url(request, reverse('ingestion:index'))})


def _resources(batch, rows):
    matches = defaultdict(list)
    if rows:
        movements = BankMovement.objects.filter(user=batch.user, account=batch.account,
            effective_date__range=(min(row.date for row in rows), max(row.date for row in rows))).select_related('account')
        for movement in movements:
            matches[(movement.effective_date, movement.signed_amount)].append(movement)
    duplicate_ids = {identity.external_id: identity for identity in ExternalStatementIdentity.objects.filter(
        user=batch.user, account=batch.account, external_id__in=[row.external_id for row in rows if row.external_id],
    ).select_related('row__batch')}
    return {'categories': list(Category.objects.filter(user=batch.user)),
        'invoices': list(CardInvoice.objects.filter(user=batch.user, manual_settlement=True).exclude(status='PAID').select_related('card__account')),
        'accounts': list(BankAccount.objects.filter(user=batch.user).select_related('bank')),
        'matches': matches, 'duplicates': duplicate_ids,
        'models': {'category': Category, 'matched_movement': BankMovement, 'invoice': CardInvoice, 'counterparty_account': BankAccount}}


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def review(request, pk):
    batch = _batch(request.user, pk)
    if batch.status != 'READY':
        return redirect(with_return_url(_destination(batch), return_url(request, '')))
    rows = list(batch.rows.all())
    resources = _resources(batch, rows)
    pending_count = sum(not row.action for row in rows)
    page = Paginator(rows, 25).get_page(request.POST.get('page') if request.method == 'POST' else request.GET.get('page'))
    identifier_counts = Counter(row.external_id for row in rows if row.external_id)
    bulk_skip = request.method == 'POST' and request.POST.get('bulk_action') == 'skip_confirmed'
    data = request.POST.copy() if request.method == 'POST' else None
    skippable_count = sum(not row.action and row.external_id in resources['duplicates'] for row in page)
    to_skip = {row.pk for row in page if not row.action and data.get(f'row-{row.pk}-action', '') in ('', 'SKIP') and row.external_id in resources['duplicates']} if bulk_skip else set()
    for row_id in to_skip:
        data[f'row-{row_id}-action'] = 'SKIP'
    entries = []
    for row in page:
        row.batch = batch
        form_data = data if not bulk_skip or data.get(f'row-{row.pk}-action') else None
        form = ReviewRowForm(form_data, row=row, resources=resources, prefix=f'row-{row.pk}')
        candidates = resources['matches'].get((row.date, row.amount), [])
        entries.append({'row': row, 'form': form, 'strong_duplicate': resources['duplicates'].get(row.external_id),
            'weak_duplicate': any(movement.description.casefold().strip() == row.description.casefold().strip() for movement in candidates),
            'repeated_identifier': bool(row.external_id and identifier_counts[row.external_id] > 1)})
    if request.method == 'POST':
        # Field names are untrusted. Compare canonical IDs without converting
        # arbitrary digit strings to integers or accepting localized IDs.
        submitted_ids = {match.group(1) for name in request.POST if (match := re.match(r'^row-(\d+)-', name))}
        selected = [entry for entry in entries if not bulk_skip or data.get(f"row-{entry['row'].pk}-action")]
        valid = [entry['form'].is_valid() for entry in selected]
        if not submitted_ids.issubset({str(row.pk) for row in page}):
            entries[0]['form'].add_error(None, _('Review only the entries shown on this page.'))
            valid.append(False)
        if bulk_skip and not to_skip:
            entries[0]['form'].add_error(None, _('No pending confirmed bank identifiers are available to skip on this page.'))
            valid.append(False)
        if all(valid):
            try:
                save_review(request.user, batch.pk, {entry['row'].pk: entry['form'].decision() for entry in selected},
                    partial=bulk_skip or page.paginator.num_pages > 1, confirmed_skips=to_skip)
                pending = batch.rows.filter(action='').order_by('number', 'pk').values('pk', 'number').first()
                target = reverse('ingestion:confirmation', args=[batch.pk])
                if pending:
                    # Another tab may remap this CSV after the review commits.
                    # Use current row numbers, never PKs from the rendered page.
                    number = (pending['number'] - 1) // 25 + 1
                    target = reverse('ingestion:review', args=[batch.pk]) + f"?page={number}#entry-{pending['pk']}"
                return redirect(with_return_url(target, return_url(request, '')))
            except ValidationError as error:
                _error(entries[0]['form'], error)
    first_pending = next((entry for entry in entries if not entry['row'].action), entries[0])
    for entry in entries:
        entry['expanded'] = entry is first_pending or bool(entry['form'].errors) if request.method == 'POST' else entry is first_pending
    return render(request, 'ingestion/review.html', {'batch': batch, 'entries': entries, 'page': page,
        'pending_count': pending_count, 'entry_count': len(rows),
        'duplicate_count': sum(bool(row.external_id in resources['duplicates'] or (row.external_id and identifier_counts[row.external_id] > 1)) for row in rows),
        'skippable_count': skippable_count,
        'unknown_baseline': bool(batch.account.opening_balance and batch.account.opening_date is None),
        'return_url': return_url(request, ''), 'cancel_url': return_url(request, reverse('ingestion:index'))})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def confirmation(request, pk):
    batch = _batch(request.user, pk)
    if batch.status != 'READY':
        return redirect(with_return_url(_destination(batch), return_url(request, '')))
    form = ConfirmationForm(request.POST or None, initial={'digest': decision_digest(batch)}, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            confirm_batch(request.user, batch.pk, form.cleaned_data['digest'])
            messages.success(request, _('Statement import confirmed.'))
            return redirect(return_url(request, reverse('ingestion:detail', args=[batch.pk])))
        except ValidationError as error:
            _error(form, error)
    rows = batch.rows.select_related('category', 'matched_movement', 'invoice__card', 'counterparty_account__bank')
    return render(request, 'ingestion/confirmation.html', {'batch': batch, 'rows': rows, 'form': form,
        'return_url': return_url(request, ''), 'cancel_url': return_url(request, reverse('ingestion:review', args=[batch.pk]))})


@login_required
@never_cache
@require_http_methods(['GET'])
def detail(request, pk):
    batch = _batch(request.user, pk)
    if batch.status in ('STAGED', 'READY'):
        return redirect(with_return_url(_destination(batch), return_url(request, '')))
    rows = batch.rows.select_related('category', 'matched_movement', 'invoice__card', 'counterparty_account__bank', 'created_transaction', 'created_payment__invoice', 'created_transfer')
    return render(request, 'ingestion/detail.html', {'batch': batch, 'rows': rows, 'reconciliation': reconciliation(batch), 'return_url': return_url(request, '')})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def undo(request, pk):
    batch = _batch(request.user, pk)
    if batch.status != 'CONFIRMED':
        return redirect(with_return_url(_destination(batch), return_url(request, '')))
    error = None
    if request.method == 'POST':
        try:
            undo_batch(request.user, batch.pk)
            messages.success(request, _('Import undone. Matched original records were kept. Uploading the file again now starts a new explicit review.'))
            return redirect(return_url(request, reverse('ingestion:detail', args=[batch.pk])))
        except ValidationError as exception:
            error = exception.messages if not hasattr(exception, 'message_dict') else [message for values in exception.message_dict.values() for message in values]
    return render(request, 'ingestion/undo.html', {'batch': batch, 'errors': error,
        'return_url': return_url(request, ''), 'cancel_url': return_url(request, reverse('ingestion:detail', args=[batch.pk]))})
