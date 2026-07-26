from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from payments.forms import PaymentMethodForm
from payments.models import PaymentMethod


class PaymentMethodListView(LoginRequiredMixin, ListView):
    """List the logged-in user's payment methods (PRD 5.2.1, FR11, FR12)."""

    model = PaymentMethod
    template_name = 'payments/list.html'
    context_object_name = 'payment_methods'

    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)


class PaymentMethodFormMixin(LoginRequiredMixin):
    """Shared plumbing for the create/update CBVs (per-user isolation, PRD R3)."""

    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = 'payments/form.html'
    success_url = reverse_lazy('payments:list')

    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)


class PaymentMethodCreateView(SuccessMessageMixin, PaymentMethodFormMixin, CreateView):
    """Create a payment method owned by the logged-in user (PRD 5.2.2)."""

    success_message = 'Payment method "%(name)s" created.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class PaymentMethodUpdateView(SuccessMessageMixin, PaymentMethodFormMixin, UpdateView):
    """Update one of the logged-in user's own payment methods (PRD 5.2.2)."""

    success_message = 'Payment method "%(name)s" updated.'


class PaymentMethodDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a payment method with confirmation (PRD 5.2.2).

    `Transaction.payment_method` uses `on_delete=PROTECT` (PRD §8.5), so
    deleting a payment method still referenced by a transaction raises
    `ProtectedError`. Catch it here and show a friendly message instead of
    a 500, mirroring `CategoryDeleteView` in `categories/views.py`.
    """

    model = PaymentMethod
    template_name = 'payments/confirm_delete.html'
    context_object_name = 'payment_method'
    success_url = reverse_lazy('payments:list')

    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)

    def form_valid(self, form):
        name = self.object.name
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'"{name}" cannot be deleted because it is still '
                'used by existing transactions.',
            )
            return redirect('payments:list')
        messages.success(self.request, f'Payment method "{name}" deleted.')
        return response
