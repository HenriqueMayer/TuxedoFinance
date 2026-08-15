import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction as db_transaction
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from banking.models import BankAccount
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
    """Paginated list of the logged-in user's transactions (FR06, FR12, FR17).

    `select_related` avoids N+1 queries when rendering each row's category
    and banking instrument (NFR10).

    Optional filtering (PRD 8.1.5, zero-JS): `?q=` searches the text fields,
    `?month=YYYY-MM` filters by the month the money actually moves (see
    `_filter_by_billed_month`), `?date=YYYY-MM-DD` matches the exact
    `transaction_date`, and `?type=INCOME|EXPENSE|INVESTMENT` filters by
    `transaction_type`. All are plain GET params read straight from a
    `<form method="get">` in the template — invalid/unknown values are
    silently ignored rather than raising a 400, and the filters combine with
    AND when more than one is set.

    `?sort=newest|oldest|updated|highest|lowest` reorders the list. The amount
    sorts use the stored full positive `amount` shown as the row's headline,
    not a signed cash-flow value or one installment's monthly contribution.
    Every ordering ends with a unique primary-key tie-breaker so pagination is
    deterministic. An unknown value falls back to `newest`.
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

        transaction_type = self.request.GET.get('type')
        if transaction_type in Transaction.TransactionType.values:
            queryset = queryset.filter(transaction_type=transaction_type)

        transaction_date = self._selected_transaction_date()
        if transaction_date is not None:
            queryset = queryset.filter(date=transaction_date)

        queryset = queryset.order_by(*self.SORT_OPTIONS[self._selected_sort()])

        # Month last: it is the one filter that may fall back to a Python
        # fold, so everything expressible as SQL runs first and narrows the
        # rows that fold has to walk. It also has to run after `order_by`,
        # since the fold below is a plain Python list that keeps whatever
        # order the queryset already had.
        return self._filter_by_billed_month(queryset)

    def _filter_by_billed_month(self, queryset):
        """Narrow `queryset` to the rows that actually charge in `?month=`.

        The month asked for is the month the **money moves**, not the month of
        the purchase — the same question the dashboard answers, so the two
        screens can never disagree about which month a transaction belongs to.
        Two consequences, both of which the plain `transaction_date` filter
        this replaces got wrong:

          - a credit card purchase made on or after the card's best purchase
            day is listed under the month its bill is paid — 26 July on a card
            opening on the 24th is an August row, not a July one; and
          - a fixed transaction or an open installment plan is listed under
            **every** month it charges, not only the month it was recorded in.
            A subscription started in July shows under August, September, and
            every month after, which is exactly what makes it fixed.

        `Transaction.amount_for_month` owns both rules and neither survives
        translation to a SQL predicate: the billing shift compares the
        purchase day against the card's own `best_purchase_day`, and a fixed
        transaction recurs without bound. So the rows are folded in Python and
        a **list** comes back — `ListView` paginates one exactly like a
        queryset. That is the same trade `dashboard.services` makes for the
        same reason (NFR10): still a single round-trip, over one user's
        transactions already narrowed by the filters above.

        An absent or malformed value returns the queryset untouched and lazy,
        so an unfiltered list behaves exactly as it did before.
        """
        month = self.request.GET.get('month')
        if not month:
            return queryset

        return _filter_transactions_by_billed_month(queryset, month)

    def _selected_transaction_date(self):
        """Parse an exact ISO `?date=`, ignoring malformed values."""
        raw = self.request.GET.get('date', '').strip()
        if not raw:
            return None
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.isoformat() == raw else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transaction_type_choices'] = Transaction.TransactionType.choices
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['selected_month'] = self.request.GET.get('month', '')
        selected_date = self._selected_transaction_date()
        context['selected_date'] = selected_date.isoformat() if selected_date else ''
        context['selected_type'] = self.request.GET.get('type', '')
        context['selected_sort'] = self._selected_sort()
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
