# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Transfers between owned accounts."""

from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from banking.forms import BankTransferForm
from banking.services import create_transfer
from .base import OperationFormMixin


class BankTransferCreateView(OperationFormMixin):
    form_class = BankTransferForm
    form_title = _('Transfer between my accounts')

    def form_valid(self, form):
        create_transfer(user=self.request.user, **form.cleaned_data)
        messages.success(self.request, _('Transfer recorded without changing income or expenses.'))
        return super().form_valid(form)
