# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Invoice consultations and explicitly confirmed payments."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView
from core.navigation import return_url, with_return_url
from banking.forms import InvoiceFilterForm, InvoicePaymentForm
from banking.models import (
    Bank,
    CardInvoice,
    CreditCard,
    InvoicePayment,
)
from transactions.services import sync_user_ledger
from banking.settlements import save_invoice_payment, delete_invoice_payment
from .base import _canonical_id


class InvoiceListView(LoginRequiredMixin, ListView):
    template_name = 'banking/invoices.html'
    context_object_name = 'invoices'
    paginate_by = 30

    def get_queryset(self):
        sync_user_ledger(self.request.user)
        invoices = CardInvoice.objects.filter(user=self.request.user, card__user=self.request.user,
            card__account__user=self.request.user, card__account__bank__user=self.request.user
        ).select_related('card__account__bank').prefetch_related('payments')
        self.card = None
        if 'card_pk' in self.kwargs:
            self.card = get_object_or_404(CreditCard.objects.select_related('account__bank'),
                user=self.request.user, account__user=self.request.user,
                account__bank__user=self.request.user, pk=self.kwargs['card_pk'])
            invoices = invoices.filter(card=self.card)
        bank_id = self.request.GET.get('bank', '')
        if bank_id:
            if not _canonical_id(bank_id):
                raise Http404
            get_object_or_404(Bank, user=self.request.user, pk=bank_id)
        self.filter_form = InvoiceFilterForm(self.request.GET or None, user=self.request.user)
        if self.filter_form.is_bound:
            if not self.filter_form.is_valid():
                return invoices.none()
            data = self.filter_form.cleaned_data
            if data['month']:
                invoices = invoices.filter(reference_month=data['month'])
            if data['bank']:
                invoices = invoices.filter(card__account__bank=data['bank'])
            if data['status']:
                invoices = invoices.filter(status=data['status'])
            if data['q']:
                invoices = invoices.filter(Q(card__name__icontains=data['q']) | Q(card__account__name__icontains=data['q']) | Q(card__account__bank__name__icontains=data['q']))
        return invoices.order_by('-reference_month', 'card__account__bank__name', 'card__name', 'pk')

    def get_context_data(self, **kwargs):
        # Active means applied, while raw bound input stays available for
        # validation recovery and Clear even when the criteria are rejected.
        active_filter_count = (sum(bool(self.filter_form.cleaned_data.get(name))
            for name in self.filter_form.fields if name != 'q')
            if self.filter_form.is_bound and self.filter_form.is_valid() else 0)
        clear_url = (reverse('banking:card_invoices', args=[self.card.pk]) if self.card else reverse('banking:invoices'))
        origin = return_url(self.request, '')
        return super().get_context_data(**kwargs) | {'selected_card': self.card,
            'filter_form': self.filter_form, 'has_filters': any(self.request.GET.get(name) for name in self.filter_form.fields),
            'active_filter_count': active_filter_count, 'invoice_clear_url': with_return_url(clear_url, origin),
            'invoice_origin': origin}


class InvoiceCardListView(InvoiceListView):
    context_object_name = 'cards'

    def get(self, request, *args, **kwargs):
        # Existing card-filter bookmarks become explicit page navigation. Using
        # distinct paths also keeps live-filter history within its owning view.
        card_id = request.GET.get('card', '')
        if card_id:
            if not _canonical_id(card_id):
                raise Http404
            card = get_object_or_404(CreditCard, user=request.user, account__user=request.user,
                account__bank__user=request.user, pk=card_id)
            query = request.GET.copy()
            query.pop('card')
            target = reverse('banking:card_invoices', args=[card.pk])
            return redirect(target + ('?' + query.urlencode() if query else ''))
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        invoices = super().get_queryset()
        cards = CreditCard.objects.filter(user=self.request.user, account__user=self.request.user,
            account__bank__user=self.request.user).select_related('account__bank').annotate(
                invoice_count=Count('invoices', filter=Q(invoices__in=invoices)))
        if self.filter_form.is_bound:
            if not self.filter_form.is_valid():
                return cards.none()
            data = self.filter_form.cleaned_data
            if data['bank']:
                cards = cards.filter(account__bank=data['bank'])
            if data['q']:
                cards = cards.filter(Q(name__icontains=data['q']) | Q(account__name__icontains=data['q'])
                                     | Q(account__bank__name__icontains=data['q']))
            if data['month'] or data['status']:
                cards = cards.filter(invoice_count__gt=0)
        return cards.order_by('account__bank__name', 'account__name', 'name', 'pk')


def _payment_errors(form, error):
    if hasattr(error, 'message_dict'):
        for field, messages_ in error.message_dict.items():
            for message in messages_:
                form.add_error(field if field in form.fields else None, message)
    else:
        form.add_error(None, error)


@login_required
def invoice_detail(request, pk):
    sync_user_ledger(request.user)
    invoice = get_object_or_404(CardInvoice.objects.select_related('card__account__bank').prefetch_related('payments__account'), pk=pk, user=request.user)
    form = InvoicePaymentForm(request.POST or None, user=request.user, invoice=invoice)
    if request.method == 'POST' and form.is_valid():
        try:
            save_invoice_payment(form.save(commit=False))
        except ValidationError as error:
            _payment_errors(form, error)
        else:
            messages.success(request, _('Invoice payment confirmed.'))
            # Keep the payment outcome beside its remaining obligation. An
            # origin is for Cancel; recording a payment remains on this invoice.
            target = with_return_url(reverse('banking:invoice_detail', args=[pk]), return_url(request, ''))
            return redirect(target + '#invoice-summary')
    from transactions.models import Transaction
    items = Transaction.objects.filter(user=request.user, credit_card=invoice.card).select_related('category')
    sources = [(item, item.amount_for_month(invoice.reference_month.year, invoice.reference_month.month)) for item in items]
    # Nested editors return to this invoice with its explicit outer origin;
    # request.path alone would discard the filtered consultation after an edit.
    invoice_context_url = with_return_url(reverse('banking:invoice_detail', args=[pk]), return_url(request, ''))
    return render(request, 'banking/invoice_detail.html', {'invoice': invoice, 'form': form, 'sources': [(item, amount) for item, amount in sources if amount],
        'invoice_context_url': invoice_context_url,
        'return_url': return_url(request, reverse('banking:invoices'))})


@login_required
def invoice_payment_edit(request, pk):
    payment = get_object_or_404(InvoicePayment.objects.select_related('invoice__card__account'), pk=pk, user=request.user)
    form = InvoicePaymentForm(request.POST or None, instance=payment, user=request.user, invoice=payment.invoice)
    if request.method == 'POST' and form.is_valid():
        try:
            save_invoice_payment(form.save(commit=False))
        except ValidationError as error:
            _payment_errors(form, error)
        else:
            return redirect(return_url(request, reverse('banking:invoice_detail', args=[payment.invoice_id])))
    destination = return_url(request, reverse('banking:invoice_detail', args=[payment.invoice_id]))
    return render(request, 'banking/form.html', {'form': form, 'form_title': _('Edit confirmed payment'), 'cancel_url': destination, 'return_url': destination})


@login_required
def invoice_payment_delete(request, pk):
    payment = get_object_or_404(InvoicePayment.objects.select_related('invoice__card__account'), pk=pk, user=request.user)
    destination = return_url(request, reverse('banking:invoice_detail', args=[payment.invoice_id]))
    if request.method == 'POST':
        delete_invoice_payment(payment)
        return redirect(destination)
    return render(request, 'banking/payment_delete.html', {'payment': payment, 'return_url': destination})
