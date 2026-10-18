# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Shared owned-record form, operation and deletion behavior."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, FormView
from core.navigation import ReturnContextMixin, return_url
from banking.models import (
    BankAccount,
    CreditCard,
    DebitCard,
    LoyaltyProgram,
)
from transactions.services import sync_user_ledger


def _canonical_id(value):
    return bool(value and value.isascii() and value.isdecimal() and value[0] != '0'
                and len(value) <= 19 and (len(value) < 19 or value <= '9223372036854775807'))


class OwnedFormMixin(ReturnContextMixin, LoginRequiredMixin):
    template_name = 'banking/form.html'
    form_title = ''
    form_variant = ''

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        for field in ('bank', 'account'):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = self.form_title
        context['form_variant'] = self.form_variant
        context['cancel_url'] = self.get_return_url()
        # A rendered fallback is for Cancel. Posting it as an explicit origin
        # would mask defaults that become known only after creating the record.
        context['return_url'] = return_url(self.request, '')
        return context

    def get_return_fallback(self):
        return self.get_cancel_url()

    def get_cancel_url(self):
        return reverse('banking:list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                if isinstance(form.instance, CreditCard):
                    sync_user_ledger(self.request.user)
                return response
        except IntegrityError:
            form.add_error(None, _('A record with these values already exists.'))
            return self.form_invalid(form)


class RelatedFormMixin(OwnedFormMixin):
    def get_bank(self):
        obj = self.object
        if isinstance(obj, BankAccount):
            return obj.bank
        if isinstance(obj, (DebitCard, CreditCard)):
            return obj.account.bank
        if isinstance(obj, LoyaltyProgram):
            return obj.bank
        return None

    def get_return_fallback(self):
        bank = self.get_bank()
        return reverse('banking:detail', args=[bank.pk]) if bank else self.get_cancel_url()

    def get_cancel_url(self):
        if getattr(self, 'object', None) and self.object.pk:
            bank = self.get_bank()
            if bank:
                return reverse('banking:detail', args=[bank.pk])
        bank_id = self.request.GET.get('bank')
        account_id = self.request.GET.get('account')
        if account_id:
            bank_id = BankAccount.objects.filter(
                pk=account_id, user=self.request.user
            ).values_list('bank_id', flat=True).first()
        return reverse('banking:detail', args=[bank_id]) if bank_id else reverse('banking:list')


class OwnedDeleteView(ReturnContextMixin, LoginRequiredMixin, DeleteView):
    template_name = 'banking/confirm_delete.html'
    context_object_name = 'item'

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_return_fallback(self):
        return reverse('banking:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.get_return_url()
        return context

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                _('This item cannot be deleted because financial records still reference it.'),
            )
            return redirect(self.get_return_url())
        messages.success(self.request, _('Item deleted.'))
        return response


class OperationFormMixin(ReturnContextMixin, LoginRequiredMixin, FormView):
    template_name = 'banking/form.html'
    form_title = ''
    success_url = reverse_lazy('banking:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial['date'] = timezone.localdate()
        for field in ('source_account', 'destination_account', 'program', 'invoice'):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = self.form_title
        context['cancel_url'] = self.get_return_url()
        context['return_url'] = return_url(self.request, '')
        return context
