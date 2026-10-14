import csv
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Count, Q
from django.forms import inlineformset_factory
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.utils.translation import pgettext
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from banking.models import BankAccount, CreditCard, DebitCard
from categories.models import Category
from core.csv import export_row
from core.navigation import ReturnContextMixin, return_url
from transactions.forms import TransactionDateFilterForm, TransactionForm, TransactionSplitForm, BaseTransactionSplitFormSet
from transactions.models import Transaction, TransactionSplit
from transactions.services import sync_user_ledger


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


def _requested_billed_month(raw_month):
    """Return a valid ``(year, month)`` pair or ``None`` for no filter."""
    if len(raw_month) != 7:
        return None
    try:
        parsed = date.fromisoformat(raw_month + '-01')
    except ValueError:
        return None
    return (parsed.year, parsed.month) if parsed.isoformat()[:7] == raw_month else None


def _filter_transactions_by_billed_month(queryset, raw_month):
    requested_month = _requested_billed_month(raw_month)
    if requested_month is None:
        return queryset
    year, month_number = requested_month
    return [txn for txn in queryset if txn.amount_for_month(year, month_number)]


class TransactionListView(LoginRequiredMixin, ListView):
    """Progressive GET filters over owned economic events.

    Type-card counts precede category/recurrence refinement. A billed-month
    request folds amount_for_month once; otherwise aggregation and filtering
    remain in SQL. Ordering always has a unique tie-breaker, and amount sorting
    uses the stored full native amount, as displayed in the existing rows.
    """

    model = Transaction
    template_name = 'transactions/list.html'
    context_object_name = 'transactions'
    paginate_by = 10

    SORT_OPTIONS = {
        'newest': ('-date', '-created_at', '-pk'),
        'oldest': ('date', 'created_at', 'pk'),
        'updated': ('-updated_at', '-pk'),
        'highest': ('-amount', '-date', '-created_at', '-pk'),
        'lowest': ('amount', '-date', '-created_at', '-pk'),
    }

    def _selected_sort(self):
        sort = self.request.GET.get('sort')
        return sort if sort in self.SORT_OPTIONS else 'newest'

    def get(self, request, *args, **kwargs):
        self.date_filter_form = TransactionDateFilterForm(request.GET, user=request.user)
        if self.date_filter_form.is_valid():
            chosen = self.date_filter_form.cleaned_data['date']
            if chosen and request.GET.get('date') != chosen.isoformat():
                params = request.GET.copy()
                params['date'] = chosen.isoformat()
                return redirect(request.path + '?' + params.urlencode())
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user).select_related(
            'category', 'bank_account__bank', 'debit_card__account__bank',
            'credit_card__account__bank', 'reward_redemption__target_account'
        ).prefetch_related('splits__category')

        # FR17: free-text search across everything the row displays, so
        # "salary" finds the transaction whether the word is in its title,
        # its notes, or the name of its category/banking instrument. Filtering
        # still starts from the user's own rows, so search can never reach
        # another user's data (PRD R3).
        search = self.request.GET.get('q', '').strip()
        if search:
            matching = (
                Q(title__icontains=search)
                | Q(notes__icontains=search)
                | Q(category__name__icontains=search)
                | Q(splits__category__name__icontains=search)
                | Q(bank_account__name__icontains=search)
                | Q(bank_account__bank__name__icontains=search)
                | Q(debit_card__name__icontains=search)
                | Q(debit_card__account__name__icontains=search)
                | Q(debit_card__account__bank__name__icontains=search)
                | Q(credit_card__name__icontains=search)
                | Q(credit_card__account__name__icontains=search)
                | Q(credit_card__account__bank__name__icontains=search)
            )
            # Generated titles are translated at display time, including the
            # expenses backfilled from installations in either language.
            if search.casefold() in _('IOF on reward redemption').casefold():
                matching |= Q(reward_redemption__isnull=False)
            queryset = queryset.filter(matching).distinct()

        self.filters = QueryDict(mutable=True)
        if search:
            self.filters['q'] = search
        selected_date = self.date_filter_form.cleaned_data.get('date')
        if selected_date:
            self.filters['date'] = selected_date.isoformat()
            queryset = queryset.filter(date=selected_date)

        # Normalize the list's month independently of the unchanged CSV API.
        raw_month = self.request.GET.get('month', '').strip()
        try:
            selected_month = date.fromisoformat(raw_month + '-01')
        except ValueError:
            selected_month = None
        if selected_month and selected_month.isoformat()[:7] == raw_month:
            self.filters['month'] = raw_month
        self.filters['sort'] = self._selected_sort()
        queryset = queryset.order_by(*self.SORT_OPTIONS[self.filters['sort']])
        rows = _filter_transactions_by_billed_month(queryset, self.filters.get('month', ''))
        monthly = isinstance(rows, list)
        if monthly:
            counts = {kind: 0 for kind in Transaction.TransactionType.values}
            for item in rows:
                counts[item.transaction_type] += 1
        else:
            counts = dict(rows.order_by().values('transaction_type').annotate(
                count=Count('pk', distinct=True),
            ).values_list('transaction_type', 'count'))
        self.type_counts = counts
        self.has_transactions = bool(sum(counts.values())) or Transaction.objects.filter(
            user=self.request.user,
        ).exists()

        kind = self.request.GET.get('type', '')
        if kind in Transaction.TransactionType.values:
            self.filters['type'] = kind
            rows = ([item for item in rows if item.transaction_type == kind]
                    if monthly else rows.filter(transaction_type=kind))
        recurrence = self.request.GET.get('recurrence', '')
        predicates = {
            'fixed': Q(is_fixed=True),
            'installment': Q(is_fixed=False, installments__gt=1),
            'oneoff': Q(is_fixed=False, installments=1),
        }
        if recurrence in predicates and not (kind == 'INCOME' and recurrence == 'installment'):
            self.filters['recurrence'] = recurrence
            if monthly:
                rows = [item for item in rows if (
                    'fixed' if item.is_fixed else
                    'installment' if item.is_installment_plan else 'oneoff'
                ) == recurrence]
            else:
                rows = rows.filter(predicates[recurrence])

        if monthly:
            category_ids = {category.pk for item in rows for category, _amount in item.category_allocations_for(item.amount)}
        else:
            category_ids = set(rows.filter(splits__isnull=True).order_by().values_list('category_id', flat=True))
            category_ids.update(TransactionSplit.objects.filter(transaction__in=rows).values_list('category_id', flat=True))
        self.category_choices = list(Category.objects.filter(
            user=self.request.user, pk__in=category_ids,
        ).select_related('parent_category'))
        category = self.request.GET.get('category', '')
        if category in {str(item.pk) for item in self.category_choices}:
            self.filters['category'] = category
            rows = ([item for item in rows if any(str(cat.pk) == category for cat, _amount in item.category_allocations_for(item.amount))]
                    if monthly else rows.filter(Q(splits__isnull=True, category_id=category) | Q(splits__category_id=category)).distinct())
        return rows

    def _filter_url(self, **changes):
        params = self.filters.copy()
        for key, value in changes.items():
            if value:
                params[key] = value
            else:
                params.pop(key, None)
        return reverse('transactions:list') + '?' + params.urlencode()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        kind = self.filters.get('type', '')
        recurrence = self.filters.get('recurrence', '')
        context.update({
            'filter_params': self.filters,
            'search_query': self.filters.get('q', ''),
            'selected_month': self.filters.get('month', ''),
            'selected_date': self.filters.get('date', ''),
            'date_filter_form': self.date_filter_form,
            'selected_type': kind,
            'selected_sort': self.filters['sort'],
            'selected_category': self.filters.get('category', ''),
            'selected_recurrence': recurrence,
            'category_choices': self.category_choices,
            'has_transactions': self.has_transactions,
            'has_filters': any(key != 'sort' for key in self.filters) or self.filters['sort'] != 'newest',
            'type_cards': [{
                'label': label,
                'value': value,
                'selected': kind == value,
                'count': self.type_counts.get(value, 0) if value else sum(self.type_counts.values()),
                'url': self._filter_url(type=value, category=None, recurrence=(
                    None if value == 'INCOME' and recurrence == 'installment' else recurrence
                )),
            } for value, label in [('', _('All')), ('INCOME', pgettext('transaction type filter', 'Income')), ('EXPENSE', _('Expenses'))]],
            'recurrence_links': [{
                'label': label,
                'selected': recurrence == value,
                'url': self._filter_url(recurrence=value, category=None),
            } for value, label in [('', _('All')), ('fixed', pgettext('transaction recurrence filter', 'Fixed')),
                                  ('installment', pgettext('transaction recurrence filter', 'Installments')),
                                  ('oneoff', pgettext('transaction recurrence filter', 'One-off'))]
               if not (kind == 'INCOME' and value == 'installment')],
        })
        return context


class TransactionExportView(LoginRequiredMixin, View):
    """Download the user's transactions, optionally for one billed month."""

    def get(self, request):
        spreadsheet = request.GET.get('format') == 'spreadsheet'
        raw_month = request.GET.get('month', '')
        selected_month = _requested_billed_month(raw_month)
        transactions = Transaction.objects.filter(user=request.user).select_related(
            'category', 'bank_account__bank', 'debit_card__account__bank',
            'credit_card__account__bank',
        ).prefetch_related('splits__category').order_by('-date', '-created_at', '-pk')
        transactions = _filter_transactions_by_billed_month(transactions, raw_month)

        filename = 'transactions.csv'
        if selected_month:
            filename = f'transactions-{selected_month[0]}-{selected_month[1]:02d}.csv'
        if spreadsheet:
            filename = filename.removesuffix('.csv') + '-spreadsheet.csv'

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow((
            'transaction_date', 'billed_month', 'title', 'transaction_type',
            'category', 'payment_channel', 'bank', 'account', 'credit_card',
            'currency', 'amount', 'total_amount', 'installments', 'is_fixed',
            'fixed_until', 'notes', 'category_splits',
        ))

        for item in transactions:
            account = item.payment_account
            if selected_month:
                year, month_number = selected_month
                billed_month = date(year, month_number, 1)
                amount = item.amount_for_month(year, month_number)
            else:
                billed_month = item.billed_month
                amount = item.amount
            writer.writerow(export_row((
                item.date.isoformat(),
                billed_month.isoformat() if billed_month else '',
                item.display_title,
                item.transaction_type,
                item.category.name,
                item.payment_channel,
                account.bank.name if account else '',
                account.name if account else '',
                item.credit_card.name if item.credit_card_id else '',
                item.native_currency,
                amount,
                item.amount,
                item.installments,
                str(item.is_fixed).lower(),
                item.fixed_until.isoformat() if item.fixed_until else '',
                item.notes,
                json.dumps([{'category_id': category.pk, 'category': category.name, 'amount': str(value)} for category, value in (item.category_allocations_for_month(*selected_month) if selected_month else item.category_allocations_for(amount))], ensure_ascii=False) if item.splits.all() else '',
            ), spreadsheet=spreadsheet))
        return response


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
        with db_transaction.atomic():
            try:
                form.instance.full_clean()
            except ValidationError as error:
                for field, values in error.message_dict.items():
                    for value in values:
                        form.add_error(field if field in form.fields else None, value)
                return self.form_invalid(form)
            response = super().form_valid(form)
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
            sync_user_ledger(self.request.user)
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
            response = super().form_valid(form)
            sync_user_ledger(self.request.user)
        messages.success(
            self.request,
            _('Transaction "%(title)s" deleted.') % {'title': title},
        )
        return response
