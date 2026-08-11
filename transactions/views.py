from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from transactions.forms import TransactionForm
from transactions.models import Transaction


class TransactionListView(LoginRequiredMixin, ListView):
    """Paginated list of the logged-in user's transactions (FR06, FR12, FR17).

    `select_related` avoids N+1 queries when rendering each row's category
    and payment method (NFR10).

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
        'newest': ('-transaction_date', '-created_at', '-pk'),
        'oldest': ('transaction_date', 'created_at', 'pk'),
        'updated': ('-updated_at', '-pk'),
        'highest': ('-amount', '-transaction_date', '-created_at', '-pk'),
        'lowest': ('amount', '-transaction_date', '-created_at', '-pk'),
    }

    def _selected_sort(self):
        sort = self.request.GET.get('sort')
        return sort if sort in self.SORT_OPTIONS else 'newest'

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user).select_related(
            'category', 'payment_method'
        )

        # FR17: free-text search across everything the row displays, so
        # "salary" finds the transaction whether the word is in its title,
        # its notes, or the name of its category/payment method. Filtering
        # still starts from the user's own rows, so search can never reach
        # another user's data (PRD R3).
        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(notes__icontains=search)
                | Q(category__name__icontains=search)
                | Q(payment_method__name__icontains=search)
            )

        transaction_type = self.request.GET.get('type')
        if transaction_type in Transaction.TransactionType.values:
            queryset = queryset.filter(transaction_type=transaction_type)

        transaction_date = self._selected_transaction_date()
        if transaction_date is not None:
            queryset = queryset.filter(transaction_date=transaction_date)

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

        year_part, _, month_part = month.partition('-')
        if not (year_part.isdigit() and month_part.isdigit()):
            return queryset

        year, month_number = int(year_part), int(month_part)
        # `amount_for_month` is plain integer arithmetic on (year * 12 + month)
        # and would take month 13 without complaint, quietly answering for
        # January of the following year. An out-of-range month is a malformed
        # filter, not a different month, so it falls back to unfiltered like
        # every other bad value here.
        if not 1 <= month_number <= 12:
            return queryset

        return [txn for txn in queryset if txn.amount_for_month(year, month_number)]

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

    success_message = 'Transaction "%(title)s" created.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class TransactionUpdateView(SuccessMessageMixin, TransactionFormMixin, UpdateView):
    """Update one of the logged-in user's own transactions (FR08)."""

    success_message = 'Transaction "%(title)s" updated.'


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
        response = super().form_valid(form)
        messages.success(self.request, f'Transaction "{title}" deleted.')
        return response
