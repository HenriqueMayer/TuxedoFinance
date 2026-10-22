# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Loyalty program, entry and reward-redemption workflows."""

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Case, Count, DecimalField, Exists, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView
from core.navigation import return_url, with_return_url
from banking.forms import LoyaltyEntryForm, LoyaltyProgramForm, RewardRedemptionForm
from banking.models import (
    Bank,
    CreditCard,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from banking.services import (
    cleanup_loyalty_entry_funding,
    create_reward_redemption,
    update_reward_redemption,
    sync_loyalty_entry_funding,
)
from transactions.services import sync_user_ledger
from .base import (
    OperationFormMixin,
    OwnedDeleteView,
    OwnedFormMixin,
    RelatedFormMixin,
)
from .workspace import BankDetailView


class LoyaltySearchForm(forms.Form):
    """A bounded native GET search, independent of financial entry forms."""

    q = forms.CharField(label=_('Search'), required=False, max_length=200,
                        widget=forms.SearchInput(attrs={'id': 'loyalty-filter-q', 'data-live-search': '',
                                                       'placeholder': _('Name, bank or card')}))


def _loyalty_programs(user):
    # Search joins must never multiply point balances. Aggregate only owned
    # entries in a separate subquery before matching any linked card names.
    amount_field = DecimalField(max_digits=16, decimal_places=2)
    entries = LoyaltyEntry.objects.filter(user=user, program_id=OuterRef('pk')).order_by().values('program_id')
    totals = entries.annotate(total=Sum(Case(
        When(direction=LoyaltyEntry.Direction.CREDIT, then=F('amount')),
        default=-F('amount'), output_field=amount_field,
    ))).values('total')
    counts = entries.annotate(total=Count('pk')).values('total')
    cards = CreditCard.objects.filter(user=user, account__user=user, account__bank__user=user).select_related('account__bank').order_by('name', 'pk')
    return LoyaltyProgram.objects.filter(user=user).annotate(
        displayed_balance=Coalesce(Subquery(totals, output_field=amount_field), Value(0), output_field=amount_field),
        entry_count=Coalesce(Subquery(counts, output_field=IntegerField()), Value(0)),
    ).prefetch_related(
        Prefetch('bank', queryset=Bank.objects.filter(user=user), to_attr='display_bank'),
        Prefetch('cards', queryset=cards, to_attr='display_cards'),
    ).order_by('name', 'pk')


def _loyalty_entries(user):
    redemptions = RewardRedemption.objects.filter(loyalty_entry_id=OuterRef('pk'))
    owned_redemptions = redemptions.filter(user=user, program__user=user,
                                         target_account__user=user, target_account__bank__user=user)
    return LoyaltyEntry.objects.filter(user=user, program__user=user).annotate(
        generated_entry=Exists(redemptions),
        redemption_id=Subquery(owned_redemptions.values('pk')[:1]),
    ).order_by('-date', '-pk')


class LoyaltyProgramListView(LoginRequiredMixin, ListView):
    model = LoyaltyProgram
    template_name = 'banking/loyalty.html'
    context_object_name = 'programs'
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = LoyaltySearchForm(self.request.GET)
        programs = _loyalty_programs(self.request.user)
        if not self.filter_form.is_valid():
            return programs.none()
        query = self.filter_form.cleaned_data['q']
        if query:
            programs = programs.filter(
                Q(name__icontains=query) | Q(unit_name__icontains=query)
                | Q(bank__user=self.request.user, bank__name__icontains=query)
                | Q(cards__user=self.request.user, cards__account__user=self.request.user,
                    cards__account__bank__user=self.request.user, cards__name__icontains=query)
            ).distinct()
        return programs.prefetch_related(Prefetch('entries', queryset=_loyalty_entries(self.request.user)[:10],
                                                  to_attr='recent_entries'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(filter_form=self.filter_form,
                       has_filters=bool(self.request.GET.get('q', '')),
                       loyalty_clear_url=reverse('banking:programs'))
        return context


class LoyaltyEntryListView(LoginRequiredMixin, ListView):
    model = LoyaltyEntry
    template_name = 'banking/loyalty.html'
    context_object_name = 'entries'
    paginate_by = 30

    def get_queryset(self):
        self.program = get_object_or_404(_loyalty_programs(self.request.user), pk=self.kwargs['program_pk'])
        self.filter_form = LoyaltySearchForm(self.request.GET)
        self.filter_form.fields['q'].widget.attrs['placeholder'] = _('Search entry notes')
        entries = _loyalty_entries(self.request.user).filter(program=self.program)
        if not self.filter_form.is_valid():
            return entries.none()
        query = self.filter_form.cleaned_data['q']
        return entries.filter(notes__icontains=query) if query else entries

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(selected_program=self.program, filter_form=self.filter_form,
                       has_filters=bool(self.request.GET.get('q', '')),
                       loyalty_clear_url=reverse('banking:program_entries', args=[self.program.pk]))
        return context


class LoyaltyProgramCreateView(RelatedFormMixin, CreateView):
    model = LoyaltyProgram
    form_class = LoyaltyProgramForm
    form_title = _('New loyalty program')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        bank_id = self.request.GET.get('bank')
        if bank_id:
            bank = Bank.objects.filter(pk=bank_id, user=self.request.user).first()
            if bank is not None:
                kwargs['locked_bank'] = bank
        return kwargs


class LoyaltyProgramUpdateView(RelatedFormMixin, UpdateView):
    model = LoyaltyProgram
    form_class = LoyaltyProgramForm
    form_title = _('Edit loyalty program')


class LoyaltyProgramDeleteView(OwnedDeleteView):
    model = LoyaltyProgram


class LoyaltyEntryCreateView(OwnedFormMixin, CreateView):
    model = LoyaltyEntry
    form_class = LoyaltyEntryForm
    form_title = _('New points or miles entry')
    form_variant = 'loyalty_entry'
    success_url = reverse_lazy('banking:list')

    def get_initial(self):
        initial = super().get_initial()
        initial['date'] = timezone.localdate()
        for field in ('program', 'invoice'):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
        if initial.get('invoice'):
            initial['kind'] = LoyaltyEntry.Kind.INVOICE_AWARD
            initial['direction'] = LoyaltyEntry.Direction.CREDIT
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                sync_loyalty_entry_funding(self.object)
                sync_user_ledger(self.request.user)
            messages.success(self.request, _('Points entry recorded.'))
            return response
        except Exception as error:
            if hasattr(error, 'message_dict'):
                for field, values in error.message_dict.items():
                    target = field if field in form.fields else None
                    for value in values:
                        form.add_error(target, value)
                return self.form_invalid(form)
            raise


class LoyaltyEntryUpdateView(OwnedFormMixin, UpdateView):
    model = LoyaltyEntry
    form_class = LoyaltyEntryForm
    form_title = _('Edit points or miles entry')
    form_variant = 'loyalty_entry'
    success_url = reverse_lazy('banking:list')

    def get_queryset(self):
        return super().get_queryset().filter(reward_redemption__isnull=True)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                sync_loyalty_entry_funding(self.object)
                sync_user_ledger(self.request.user)
            messages.success(self.request, _('Points entry updated.'))
            return response
        except Exception as error:
            if hasattr(error, 'message_dict'):
                for field, values in error.message_dict.items():
                    target = field if field in form.fields else None
                    for value in values:
                        form.add_error(target, value)
                return self.form_invalid(form)
            raise


class LoyaltyEntryDeleteView(OwnedDeleteView):
    model = LoyaltyEntry

    def get_queryset(self):
        return super().get_queryset().filter(reward_redemption__isnull=True)

    def form_valid(self, form):
        with transaction.atomic():
            cleanup_loyalty_entry_funding(self.object)
            response = super().form_valid(form)
            sync_user_ledger(self.request.user)
        return response


class RewardRedemptionCreateView(OperationFormMixin):
    form_class = RewardRedemptionForm
    form_title = _('Convert points or miles to account balance')

    def get_return_fallback(self):
        if getattr(self, 'redemption', None):
            return reverse('banking:detail', args=[self.redemption.target_account.bank_id]) + '#reward-redemptions'
        return reverse('banking:list')

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.redemption = create_reward_redemption(user=self.request.user, **form.cleaned_data)
                sync_user_ledger(self.request.user)
        except Exception as error:
            if hasattr(error, 'message_dict'):
                for field, values in error.message_dict.items():
                    target = field if field in form.fields else None
                    for value in values:
                        form.add_error(target, value)
                return self.form_invalid(form)
            raise
        messages.success(self.request, _('Reward converted and IOF funding recorded.'))
        return super().form_valid(form)


class RewardRedemptionUpdateView(OwnedFormMixin, UpdateView):
    model = RewardRedemption
    form_class = RewardRedemptionForm

    def get_form_kwargs(self):
        return super().get_form_kwargs() | {'prefix': 'redemption'}

    def get(self, request, *args, **kwargs):
        redemption = self.get_object()
        url = reverse('banking:detail', args=[redemption.target_account.bank_id])
        target = f'{url}?edit_redemption={redemption.pk}#reward-redemption-{redemption.pk}'
        return redirect(with_return_url(target, return_url(request, '')))

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = update_reward_redemption(
                    redemption=self.object, user=self.request.user, **form.cleaned_data,
                )
                sync_user_ledger(self.request.user)
        except Exception as error:
            if not hasattr(error, 'message_dict'):
                raise
            for field, values in error.message_dict.items():
                for value in values:
                    form.add_error(field if field in form.fields else None, value)
            return self.form_invalid(form)
        messages.success(self.request, _('Reward redemption updated.'))
        url = reverse('banking:detail', args=[self.object.target_account.bank_id])
        return redirect(return_url(self.request, f'{url}#reward-redemption-{self.object.pk}'))

    def form_invalid(self, form):
        # Validation recovery stays inside the source section, with the bound
        # selections and errors rather than an independent transaction editor.
        original = self.get_object()
        view = BankDetailView()
        view.setup(self.request, pk=original.target_account.bank_id)
        view.object = view.get_object()
        context = view.get_context_data(editing_redemption=original, redemption_form=form)
        return render(self.request, 'banking/detail.html', context)
