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
    `?month=YYYY-MM` filters by `transaction_date`'s year/month, and
    `?type=INCOME|EXPENSE|INVESTMENT` filters by `transaction_type`. All are
    plain GET params read straight from a `<form method="get">` in the
    template — invalid/unknown values are silently ignored rather than
    raising a 400, and the three combine with AND when more than one is set.
    """

    model = Transaction
    template_name = 'transactions/list.html'
    context_object_name = 'transactions'
    paginate_by = 10

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

        month = self.request.GET.get('month')
        if month:
            year_part, _, month_part = month.partition('-')
            if year_part.isdigit() and month_part.isdigit():
                queryset = queryset.filter(
                    transaction_date__year=int(year_part),
                    transaction_date__month=int(month_part),
                )

        transaction_type = self.request.GET.get('type')
        if transaction_type in Transaction.TransactionType.values:
            queryset = queryset.filter(transaction_type=transaction_type)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transaction_type_choices'] = Transaction.TransactionType.choices
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['selected_month'] = self.request.GET.get('month', '')
        context['selected_type'] = self.request.GET.get('type', '')
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
