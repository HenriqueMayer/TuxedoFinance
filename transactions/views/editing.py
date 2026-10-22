# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owned transaction editing and atomic category-allocation submissions."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import CreateView, DeleteView, UpdateView
from django.views.generic.edit import ModelFormMixin

from banking.models import BankAccount, CreditCard, DebitCard
from core.navigation import ReturnContextMixin, return_url
from transactions.forms import (
    BaseTransactionSplitFormSet, TransactionForm, TransactionSplitForm,
)
from transactions.models import Transaction, TransactionSplit
from transactions.services import sync_user_ledger
from transactions.projection import ProjectionLimitExceeded, validate_occurrences


def _excessive_schedule(item):
    try:
        validate_occurrences(item)
    except ProjectionLimitExceeded:
        return True
    return False


def _pending_projection_notice(request):
    messages.warning(request, _(
        'The transaction change was saved. Ledger synchronization remains stopped '
        'until the other excessive recurring schedules are reviewed.'
    ))


@login_required
def category_split(request, pk):
    item = get_object_or_404(Transaction, pk=pk, user=request.user, reward_redemption__isnull=True)
    destination = return_url(request, reverse('transactions:update', args=[pk]))
    factory = inlineformset_factory(Transaction, TransactionSplit, form=TransactionSplitForm, formset=BaseTransactionSplitFormSet, extra=2, max_num=20, validate_max=True)
    data = request.POST.copy() if request.method == 'POST' else None
    if data is not None and 'add_split' in data:
        try:
            count = int(data.get('splits-TOTAL_FORMS', '0'))
        except ValueError:
            count = 0
        data['splits-TOTAL_FORMS'] = str(min(max(2, count + 1), 20))
    formset = factory(data, instance=item, prefix='splits', form_kwargs={'user': request.user, 'transaction_type': item.transaction_type})
    if request.method == 'POST' and 'clear_split' in request.POST:
        item.splits.all().delete()
        return redirect(destination)
    if request.method == 'POST' and 'add_split' not in request.POST and formset.is_valid():
        with db_transaction.atomic():
            # A split changes classification only: the parent and its cash
            # projection retain their identifiers and amounts.
            formset.save()
        messages.success(request, _('Category split saved.'))
        return redirect(destination)
    return render(request, 'transactions/split.html', {'transaction': item, 'formset': formset, 'return_url': destination})

class TransactionFormMixin(ReturnContextMixin, LoginRequiredMixin):
    """Shared plumbing for the create/update CBVs (per-user isolation, PRD R3)."""

    model = Transaction
    form_class = TransactionForm
    template_name = 'transactions/form.html'
    success_url = reverse_lazy('transactions:list')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['manage_splits'] = (self.request.method != 'POST'
                                  or 'splits-TOTAL_FORMS' in self.request.POST
                                  or 'split_categories' in self.request.POST)
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get('split') == '1':
            initial['split_categories'] = True
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        factory = inlineformset_factory(Transaction, TransactionSplit,
            form=TransactionSplitForm, formset=BaseTransactionSplitFormSet,
            extra=2, max_num=20, validate_max=True)
        data = self.request.POST.copy() if self.request.method == 'POST' else None
        if data is not None and 'add_split' in data:
            try:
                count = int(data.get('splits-TOTAL_FORMS', '0'))
            except ValueError:
                count = 0
            data['splits-TOTAL_FORMS'] = str(min(max(2, count + 1), 20))
        split_selected = (form.data.get('split_categories') if form.is_bound
                          else form.initial.get('split_categories'))
        inactive = form.is_bound and not split_selected
        self.split_formset = factory(None if inactive else data, instance=form.instance,
            queryset=TransactionSplit.objects.none() if inactive else None, prefix='splits',
            form_kwargs={'user': self.request.user, 'allow_type_changes': True})
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['split_formset'] = self.split_formset
        return context

    def form_valid(self, form):
        # Adding a row is a native POST round trip, never a financial save.
        if 'add_split' in self.request.POST:
            return self.form_invalid(form)
        split_enabled = form.manage_splits and form.cleaned_data['split_categories']
        if split_enabled:
            self.split_formset.instance = form.instance
            if not self.split_formset.is_valid():
                return self.form_invalid(form)
            allocations = [row.cleaned_data for row in self.split_formset.forms
                           if row.cleaned_data and not row.cleaned_data.get('DELETE')]
            form.instance.category = allocations[0]['category']
        else:
            allocations = []
        original_pk = form.instance.pk
        try:
            response = self.save_with_ledger(form, allocations)
        except ProjectionLimitExceeded as error:
            # Restore the unsaved identity after a rolled-back create. Keep the
            # bound form and avoid a premature success message on any failure.
            form.instance.pk = original_pk
            form.instance._state.adding = original_pk is None
            self.object = form.instance if original_pk else None
            form.add_error(None, error)
            return self.form_invalid(form)
        if response.status_code < 300:
            return response
        success = self.get_success_message(form.cleaned_data)
        if success:
            messages.success(self.request, success)
        if getattr(self, 'projection_pending', False):
            _pending_projection_notice(self.request)
        return response

    def save_with_ledger(self, form, allocations):
        with db_transaction.atomic():
            repairing = bool(form.instance.pk and _excessive_schedule(
                self.get_queryset().get(pk=form.instance.pk)))
            try:
                form.instance.full_clean()
            except ValidationError as error:
                for field, values in error.message_dict.items():
                    for value in values:
                        form.add_error(field if field in form.fields else None, value)
                return self.form_invalid(form)
            response = ModelFormMixin.form_valid(self, form)
            if form.manage_splits:
                # Match by category so unchanged allocations retain their IDs,
                # including when categories are swapped between editor rows.
                desired = {row['category'].pk: row['amount'] for row in allocations}
                self.object.splits.exclude(category_id__in=desired).delete()
                existing = {row.category_id: row for row in self.object.splits.all()}
                for category_id, amount in desired.items():
                    row = existing.get(category_id)
                    if row is None:
                        TransactionSplit.objects.create(transaction=self.object, category_id=category_id, amount=amount)
                    elif row.amount != amount:
                        row.amount = amount
                        row.save(update_fields=['amount'])
            try:
                sync_user_ledger(self.request.user)
            except ProjectionLimitExceeded:
                if not repairing:
                    raise
                # Permit explicit repairs one source at a time. No projection
                # rows change while another legacy source still blocks sync.
                validate_occurrences(self.get_queryset().get(pk=self.object.pk))
                self.projection_pending = True
        return response

    def form_invalid(self, form):
        if form.manage_splits and form.data.get('split_categories'):
            self.split_formset.is_valid()
        return super().form_invalid(form)


# Combined validation must wrap success messaging: an invalid split is no save.
class TransactionCreateView(TransactionFormMixin, SuccessMessageMixin, CreateView):
    """Create a transaction owned by the logged-in user (FR07)."""

    success_message = gettext_lazy('Transaction "%(title)s" created.')

    def get_initial(self):
        initial = super().get_initial()
        kind = self.request.GET.get('transaction_type', '')
        if kind in Transaction.TransactionType.values:
            initial['transaction_type'] = kind
        if kind != Transaction.TransactionType.INCOME:
            for name, model, channel in (
                ('credit_card', CreditCard, Transaction.PaymentChannel.CREDIT_CARD),
                ('debit_card', DebitCard, Transaction.PaymentChannel.DEBIT_CARD),
            ):
                value = self.request.GET.get(name, '')
                if value.isdigit():
                    card = model.objects.filter(user=self.request.user, account__user=self.request.user, pk=value).first()
                    if card:
                        initial.update({'transaction_type': Transaction.TransactionType.EXPENSE,
                                        'payment_channel': channel, name: card})
                        return initial
        account_id = self.request.GET.get('account', '')
        if account_id.isdigit():
            account = BankAccount.objects.filter(
                user=self.request.user, pk=account_id,
            ).first()
            if account:
                initial.update({
                    'payment_channel': Transaction.PaymentChannel.ACCOUNT,
                    'bank_account': account,
                })
        return initial

class TransactionUpdateView(TransactionFormMixin, SuccessMessageMixin, UpdateView):
    """Update one of the logged-in user's own transactions (FR08)."""

    success_message = gettext_lazy('Transaction "%(title)s" updated.')

    def get_queryset(self):
        return super().get_queryset().filter(reward_redemption__isnull=True)

class TransactionDeleteView(ReturnContextMixin, LoginRequiredMixin, DeleteView):
    """Delete a transaction with confirmation (FR09)."""

    model = Transaction
    template_name = 'transactions/confirm_delete.html'
    context_object_name = 'transaction'
    success_url = reverse_lazy('transactions:list')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user, reward_redemption__isnull=True)

    def form_valid(self, form):
        title = self.object.title
        with db_transaction.atomic():
            repairing = _excessive_schedule(self.object)
            response = super().form_valid(form)
            try:
                sync_user_ledger(self.request.user)
            except ProjectionLimitExceeded:
                if not repairing:
                    raise
                _pending_projection_notice(self.request)
        messages.success(
            self.request,
            _('Transaction "%(title)s" deleted.') % {'title': title},
        )
        return response
