import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction as db_transaction
from django.db.models import Count, Q
from django.http import HttpResponse, QueryDict
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.utils.translation import pgettext
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from banking.models import BankAccount
from categories.models import Category
from transactions.forms import TransactionForm
from transactions.models import Transaction
from transactions.services import sync_user_ledger


def _requested_billed_month(raw_month):
    """Return a valid ``(year, month)`` pair or ``None`` for no filter."""
    year_part, _, month_part = raw_month.partition('-')
    if not (year_part.isdigit() and month_part.isdigit()):
        return None
    year, month_number = int(year_part), int(month_part)
    return (year, month_number) if 1 <= month_number <= 12 else None


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

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user).select_related(
            'category', 'bank_account__bank', 'debit_card__account__bank',
            'credit_card__account__bank'
        )

        # FR17: free-text search across everything the row displays, so
        # "salary" finds the transaction whether the word is in its title,
        # its notes, or the name of its category/banking instrument. Filtering
        # still starts from the user's own rows, so search can never reach
        # another user's data (PRD R3).
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(notes__icontains=search)
                | Q(category__name__icontains=search)
                | Q(bank_account__name__icontains=search)
                | Q(bank_account__bank__name__icontains=search)
                | Q(debit_card__name__icontains=search)
                | Q(debit_card__account__name__icontains=search)
                | Q(debit_card__account__bank__name__icontains=search)
                | Q(credit_card__name__icontains=search)
                | Q(credit_card__account__name__icontains=search)
                | Q(credit_card__account__bank__name__icontains=search)
            )

        self.filters = QueryDict(mutable=True)
        if search:
            self.filters['q'] = search
        raw_date = self.request.GET.get('date', '').strip()
        try:
            selected_date = date.fromisoformat(raw_date)
        except ValueError:
            selected_date = None
        if selected_date and selected_date.isoformat() == raw_date:
            self.filters['date'] = raw_date
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
                count=Count('pk'),
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

        category_ids = ({item.category_id for item in rows} if monthly else
                        rows.order_by().values('category_id'))
        self.category_choices = list(Category.objects.filter(
            user=self.request.user, pk__in=category_ids,
        ).select_related('parent_category'))
        category = self.request.GET.get('category', '')
        if category in {str(item.pk) for item in self.category_choices}:
            self.filters['category'] = category
            rows = ([item for item in rows if str(item.category_id) == category]
                    if monthly else rows.filter(category_id=category))
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
        raw_month = request.GET.get('month', '')
        selected_month = _requested_billed_month(raw_month)
        transactions = Transaction.objects.filter(user=request.user).select_related(
            'category', 'bank_account__bank', 'debit_card__account__bank',
            'credit_card__account__bank',
        ).order_by('-date', '-created_at', '-pk')
        transactions = _filter_transactions_by_billed_month(transactions, raw_month)

        filename = 'transactions.csv'
        if selected_month:
            filename = f'transactions-{selected_month[0]}-{selected_month[1]:02d}.csv'

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow((
            'transaction_date', 'billed_month', 'title', 'transaction_type',
            'category', 'payment_channel', 'bank', 'account', 'credit_card',
            'currency', 'amount', 'total_amount', 'installments', 'is_fixed',
            'fixed_until', 'notes',
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
            writer.writerow((
                item.date.isoformat(),
                billed_month.isoformat() if billed_month else '',
                item.title,
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
            ))
        return response


class TransactionFormMixin(LoginRequiredMixin):
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
        return kwargs


class TransactionCreateView(SuccessMessageMixin, TransactionFormMixin, CreateView):
    """Create a transaction owned by the logged-in user (FR07)."""

    success_message = gettext_lazy('Transaction "%(title)s" created.')

    def get_initial(self):
        initial = super().get_initial()
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

    def form_valid(self, form):
        form.instance.user = self.request.user
        with db_transaction.atomic():
            response = super().form_valid(form)
            sync_user_ledger(self.request.user)
        return response


class TransactionUpdateView(SuccessMessageMixin, TransactionFormMixin, UpdateView):
    """Update one of the logged-in user's own transactions (FR08)."""

    success_message = gettext_lazy('Transaction "%(title)s" updated.')

    def form_valid(self, form):
        with db_transaction.atomic():
            response = super().form_valid(form)
            sync_user_ledger(self.request.user)
        return response


class TransactionDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a transaction with confirmation (FR09)."""

    model = Transaction
    template_name = 'transactions/confirm_delete.html'
    context_object_name = 'transaction'
    success_url = reverse_lazy('transactions:list')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

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
