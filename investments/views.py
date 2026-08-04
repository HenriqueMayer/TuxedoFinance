from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from investments.forms import InvestmentForm
from investments.models import Investment

ZERO = Decimal('0.00')


class InvestmentListView(LoginRequiredMixin, ListView):
    """List the logged-in user's investment entries with totals.

    Three stat cards on top — total deposited, total withdrawn, current
    balance — then the entries themselves (paginated, newest first). Two
    optional filters: `?kind=DEPOSIT|WITHDRAWAL` narrows the table, `?q=`
    does a case-insensitive search across `title`, `reason`, and `notes`.

    The current balance is computed from the **unfiltered** queryset, not
    from the filtered one, so a user looking at "only withdrawals" still
    sees the full portfolio number at the top — and is not misled into
    thinking the filtered slice is the whole picture.
    """

    model = Investment
    template_name = 'investments/list.html'
    context_object_name = 'investments'
    paginate_by = 10

    KIND_FILTER_OPTIONS = ('DEPOSIT', 'WITHDRAWAL')

    def get_queryset(self):
        queryset = Investment.objects.filter(user=self.request.user)

        kind = self.request.GET.get('kind', '').strip().upper()
        if kind in self.KIND_FILTER_OPTIONS:
            queryset = queryset.filter(kind=kind)

        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(reason__icontains=search)
                | Q(notes__icontains=search)
            )

        return queryset.order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Totals always come from the unfiltered queryset, so the user sees
        # the same portfolio number regardless of how the list below is
        # filtered. Two folds over the small in-memory list is fine.
        all_entries = Investment.objects.filter(user=self.request.user)
        total_deposits = sum(
            (entry.amount for entry in all_entries if entry.kind == Investment.Kind.DEPOSIT),
            start=ZERO,
        )
        total_withdrawals = sum(
            (entry.amount for entry in all_entries if entry.kind == Investment.Kind.WITHDRAWAL),
            start=ZERO,
        )
        context['total_deposits'] = total_deposits
        context['total_withdrawals'] = total_withdrawals
        context['current_balance'] = total_deposits - total_withdrawals
        context['kind_choices'] = Investment.Kind.choices
        context['selected_kind'] = self.request.GET.get('kind', '').strip().upper()
        context['search_query'] = self.request.GET.get('q', '').strip()
        return context


class InvestmentFormMixin(LoginRequiredMixin):
    """Shared plumbing for the create/update CBVs (per-user isolation, PRD R3)."""

    model = Investment
    form_class = InvestmentForm
    template_name = 'investments/form.html'
    success_url = reverse_lazy('investments:list')

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)


# `InvestmentFormMixin` precedes `SuccessMessageMixin` in the bases below for
# the same reason as in `payments/views.py` — keeping its `form_valid` last
# in the MRO so a save that turns into a failure never announces a success.
class InvestmentCreateView(InvestmentFormMixin, SuccessMessageMixin, CreateView):
    """Create an investment entry owned by the logged-in user."""

    success_message = 'Investment "%(title)s" created.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class InvestmentUpdateView(InvestmentFormMixin, SuccessMessageMixin, UpdateView):
    """Update one of the logged-in user's own investment entries."""

    success_message = 'Investment "%(title)s" updated.'


class InvestmentDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an investment entry with confirmation (zero-JS POST pattern)."""

    model = Investment
    template_name = 'investments/confirm_delete.html'
    context_object_name = 'investment'
    success_url = reverse_lazy('investments:list')

    def get_queryset(self):
        return Investment.objects.filter(user=self.request.user)

    def form_valid(self, form):
        title = self.object.title
        response = super().form_valid(form)
        messages.success(self.request, f'Investment "{title}" deleted.')
        return response
