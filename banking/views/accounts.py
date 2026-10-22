# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bank and account administration."""

from urllib.parse import urlsplit
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, UpdateView
from banking.forms import BankAccountForm, BankForm, BankColorForm
from banking.models import Bank, BankAccount
from .base import OwnedDeleteView, OwnedFormMixin, RelatedFormMixin


class BankCreateView(OwnedFormMixin, CreateView):
    model = Bank
    form_class = BankForm
    form_title = _('New bank')
    success_url = reverse_lazy('banking:list')


class BankUpdateView(OwnedFormMixin, UpdateView):
    model = Bank
    form_class = BankForm
    form_title = _('Edit bank')

    def get_return_fallback(self):
        return reverse('banking:detail', args=[self.object.pk])

    def get_cancel_url(self):
        return reverse('banking:detail', args=[self.object.pk])


class BankColorUpdateView(BankUpdateView):
    form_class = BankColorForm
    form_title = _('Marker color')


class BankAccountCreateView(RelatedFormMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    form_title = _('New account')


class BankAccountUpdateView(RelatedFormMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    form_title = _('Edit account')


class BankDeleteView(OwnedDeleteView):
    model = Bank

    def get_success_url(self):
        destination = super().get_success_url()
        # Cancel and a protected deletion retain the open bank. Successful
        # removal must not send the user back to that now-deleted workspace.
        if urlsplit(destination).path == reverse('banking:detail', args=[self.object.pk]):
            return reverse('banking:list')
        return destination


class BankAccountDeleteView(OwnedDeleteView):
    model = BankAccount
