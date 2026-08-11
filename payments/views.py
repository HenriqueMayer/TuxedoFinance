from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from payments.forms import PaymentMethodForm
from payments.models import PaymentMethod


class PaymentMethodListView(LoginRequiredMixin, ListView):
    """List and filter the logged-in user's payment methods (FR11, FR12)."""

    model = PaymentMethod
    template_name = 'payments/list.html'
    context_object_name = 'payment_methods'

    def _selected_type(self):
        method_type = self.request.GET.get('type')
        return method_type if method_type in PaymentMethod.MethodType.values else ''

    def get_queryset(self):
        queryset = PaymentMethod.objects.filter(user=self.request.user)

        search = self.request.GET.get('q', '').strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        method_type = self._selected_type()
        if method_type:
            queryset = queryset.filter(method_type=method_type)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['method_type_choices'] = PaymentMethod.MethodType.choices
        context['selected_type'] = self._selected_type()
        return context


class PaymentMethodFormMixin(LoginRequiredMixin):
    """Shared plumbing for the create/update CBVs (per-user isolation, PRD R3)."""

    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = 'payments/form.html'
    success_url = reverse_lazy('payments:list')

    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        # The form needs the owner to check `unique_payment_method_per_user`;
        # see the docstring in `payments/forms.py` for why Django cannot.
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        """Last line of defence for the unique-name constraint.

        The form already rejects duplicates, but that check and the INSERT are
        not atomic: two submits of the same name — a double-clicked button is
        enough, since gunicorn runs several threads per worker — can both pass
        validation before either writes. The loser hits the constraint in the
        database, and without this it surfaces as a 500.
        """
        try:
            return super().form_valid(form)
        except IntegrityError:
            form.add_error('name', 'You already have a payment method with this name.')
            return self.form_invalid(form)


# `PaymentMethodFormMixin` must precede `SuccessMessageMixin` in the bases
# below. Its `form_valid` can turn a save into a *failure*, and the success
# message has to stay unwritten when it does — which only holds while the
# exception propagates through `SuccessMessageMixin.form_valid` instead of
# being caught underneath it. Reversing the two announces "created" over a
# form that is still showing an error.
class PaymentMethodCreateView(PaymentMethodFormMixin, SuccessMessageMixin, CreateView):
    """Create a payment method owned by the logged-in user (PRD 5.2.2)."""

    success_message = 'Payment method "%(name)s" created.'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class PaymentMethodUpdateView(PaymentMethodFormMixin, SuccessMessageMixin, UpdateView):
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
