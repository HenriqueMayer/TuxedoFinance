# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Debit and credit card administration."""

from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, UpdateView
from banking.forms import CreditCardForm, DebitCardForm
from banking.models import CreditCard, DebitCard
from .base import OwnedDeleteView, RelatedFormMixin


class DebitCardCreateView(RelatedFormMixin, CreateView):
    model = DebitCard
    form_class = DebitCardForm
    form_title = _('New debit card')


class DebitCardUpdateView(RelatedFormMixin, UpdateView):
    model = DebitCard
    form_class = DebitCardForm
    form_title = _('Edit debit card')


class CreditCardCreateView(RelatedFormMixin, CreateView):
    model = CreditCard
    form_class = CreditCardForm
    form_title = _('New credit card')


class CreditCardUpdateView(RelatedFormMixin, UpdateView):
    model = CreditCard
    form_class = CreditCardForm
    form_title = _('Edit credit card')


class DebitCardDeleteView(OwnedDeleteView):
    model = DebitCard


class CreditCardDeleteView(OwnedDeleteView):
    model = CreditCard
