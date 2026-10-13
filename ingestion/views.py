# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _

from banking.models import BankAccount, BankMovement, CardInvoice
from categories.models import Category
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
@require_http_methods(['GET', 'POST'])
def index(request):
    form = UploadForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        cleaned = form.cleaned_data
        try:
            batch, created = stage_statement(request.user, cleaned['account'].pk,
                cleaned['statement'].read(2 * 1024 * 1024 + 1), cleaned['statement'].name,
                cleaned['file_format'], cleaned['encoding'], closing_balance=cleaned['closing_balance'], closing_date=cleaned['closing_date'])
            if not created:
                messages.info(request, _('This exact file already has an active import for this account. Its existing review is shown.'))
            return redirect(_destination(batch))
        except ValidationError as error:
            _error(form, error)
    batches = ImportBatch.objects.filter(user=request.user).select_related('account__bank')
    page = Paginator(batches, 20).get_page(request.GET.get('page'))
    return render(request, 'ingestion/index.html', {'form': form, 'batches': page})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def mapping(request, pk):
    batch = _batch(request.user, pk)
    if batch.status not in ('STAGED', 'READY') or batch.file_format != 'CSV':
        return redirect(_destination(batch))
    initial = {**batch.mapping, 'amount_mode': 'signed' if batch.mapping.get('amount_column') else 'separate' if batch.mapping else ''}
    form = MappingForm(request.POST or None, headers=batch.headers, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            map_csv_batch(request.user, batch.pk, form.mapping())
            return redirect('ingestion:review', pk=batch.pk)
        except ValidationError as error:
            _error(form, error)
    # Original text is escaped and shown only inside this owned local review.
    preview = batch.raw_text.splitlines()[:6]
    return render(request, 'ingestion/mapping.html', {'batch': batch, 'form': form, 'preview': preview})


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
        return redirect(_destination(batch))
    rows = list(batch.rows.all())
    resources = _resources(batch, rows)
    entries = []
    for row in rows:
        row.batch = batch
        form = ReviewRowForm(request.POST if request.method == 'POST' else None, row=row, resources=resources, prefix=f'row-{row.pk}')
        candidates = resources['matches'].get((row.date, row.amount), [])
        entries.append({'row': row, 'form': form, 'strong_duplicate': resources['duplicates'].get(row.external_id),
            'weak_duplicate': any(movement.description.casefold().strip() == row.description.casefold().strip() for movement in candidates)})
    if request.method == 'POST':
        valid = [entry['form'].is_valid() for entry in entries]
        if all(valid):
            try:
                save_review(request.user, batch.pk, {entry['row'].pk: entry['form'].decision() for entry in entries})
                return redirect('ingestion:confirmation', pk=batch.pk)
            except ValidationError as error:
                _error(entries[0]['form'], error)
    return render(request, 'ingestion/review.html', {'batch': batch, 'entries': entries,
        'unknown_baseline': bool(batch.account.opening_balance and batch.account.opening_date is None)})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def confirmation(request, pk):
    batch = _batch(request.user, pk)
    if batch.status != 'READY':
        return redirect(_destination(batch))
    form = ConfirmationForm(request.POST or None, initial={'digest': decision_digest(batch)}, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            confirm_batch(request.user, batch.pk, form.cleaned_data['digest'])
            messages.success(request, _('Statement import confirmed.'))
            return redirect('ingestion:detail', pk=batch.pk)
        except ValidationError as error:
            _error(form, error)
    rows = batch.rows.select_related('category', 'matched_movement', 'invoice__card', 'counterparty_account__bank')
    return render(request, 'ingestion/confirmation.html', {'batch': batch, 'rows': rows, 'form': form})


@login_required
@never_cache
@require_http_methods(['GET'])
def detail(request, pk):
    batch = _batch(request.user, pk)
    if batch.status in ('STAGED', 'READY'):
        return redirect(_destination(batch))
    rows = batch.rows.select_related('category', 'matched_movement', 'invoice__card', 'counterparty_account__bank', 'created_transaction', 'created_payment__invoice', 'created_transfer')
    return render(request, 'ingestion/detail.html', {'batch': batch, 'rows': rows, 'reconciliation': reconciliation(batch)})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def undo(request, pk):
    batch = _batch(request.user, pk)
    if batch.status != 'CONFIRMED':
        return redirect(_destination(batch))
    error = None
    if request.method == 'POST':
        try:
            undo_batch(request.user, batch.pk)
            messages.success(request, _('Import undone. Matched original records were kept. Uploading the file again now starts a new explicit review.'))
            return redirect('ingestion:detail', pk=batch.pk)
        except ValidationError as exception:
            error = exception.messages if not hasattr(exception, 'message_dict') else [message for values in exception.message_dict.values() for message in values]
    return render(request, 'ingestion/undo.html', {'batch': batch, 'errors': error})
