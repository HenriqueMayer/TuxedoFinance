from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from banking.forms import (
    BankAccountForm,
    BankTransferForm,
    BankForm,
    CreditCardForm,
    DebitCardForm,
    ExchangeRateForm,
    LoyaltyEntryForm,
    LoyaltyProgramForm,
    RewardRedemptionForm,
)
from banking.models import (
    Bank,
    BankAccount,
    BankMovement,
    CardInvoice,
    CreditCard,
    DebitCard,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from banking.services import (
    cleanup_loyalty_entry_funding,
    create_reward_redemption,
    create_transfer,
    sync_loyalty_entry_funding,
)
from transactions.services import sync_user_ledger


class BankListView(LoginRequiredMixin, ListView):
    model = Bank
    template_name = 'banking/list.html'
    context_object_name = 'banks'

    def dispatch(self, request, *args, **kwargs):
        sync_user_ledger(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        search = self.request.GET.get('q', '').strip()
        accounts = BankAccount.objects.filter(user=self.request.user).prefetch_related(
            Prefetch(
                'debit_cards',
                queryset=DebitCard.objects.filter(user=self.request.user),
            ),
            Prefetch(
                'credit_cards',
                queryset=CreditCard.objects.filter(user=self.request.user),
            ),
        )
        queryset = Bank.objects.filter(user=self.request.user).prefetch_related(
            Prefetch('accounts', queryset=accounts),
            Prefetch(
                'loyalty_programs',
                queryset=LoyaltyProgram.objects.filter(user=self.request.user),
            ),
        )
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(accounts__name__icontains=search)
                | Q(accounts__debit_cards__name__icontains=search)
                | Q(accounts__credit_cards__name__icontains=search)
                | Q(loyalty_programs__name__icontains=search)
            ).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['independent_programs'] = LoyaltyProgram.objects.filter(
            user=self.request.user, bank__isnull=True
        ).prefetch_related('cards')
        return context


class BankDetailView(LoginRequiredMixin, DetailView):
    model = Bank
    template_name = 'banking/detail.html'
    context_object_name = 'bank'

    def dispatch(self, request, *args, **kwargs):
        sync_user_ledger(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        accounts = BankAccount.objects.filter(user=self.request.user).prefetch_related(
            Prefetch(
                'debit_cards',
                queryset=DebitCard.objects.filter(user=self.request.user),
            ),
            Prefetch(
                'credit_cards',
                queryset=CreditCard.objects.filter(user=self.request.user),
            ),
        )
        return Bank.objects.filter(user=self.request.user).prefetch_related(
            Prefetch('accounts', queryset=accounts),
            Prefetch(
                'loyalty_programs',
                queryset=LoyaltyProgram.objects.filter(user=self.request.user).prefetch_related(
                    'cards'
                ),
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account_ids = self.object.accounts.values_list('pk', flat=True)
        context['movements'] = BankMovement.objects.filter(
            user=self.request.user, account_id__in=account_ids
        ).select_related('account').order_by('-effective_date', '-created_at')[:20]
        context['invoices'] = CardInvoice.objects.filter(
            user=self.request.user, card__account_id__in=account_ids
        ).select_related('card').order_by('-reference_month')[:12]
        return context


class OwnedFormMixin(LoginRequiredMixin):
    template_name = 'banking/form.html'
    form_title = ''

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
        context['cancel_url'] = self.get_cancel_url()
        return context

    def get_cancel_url(self):
        return reverse('banking:list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            return super().form_valid(form)
        except IntegrityError:
            form.add_error(None, _('A record with these values already exists.'))
            return self.form_invalid(form)


class BankCreateView(OwnedFormMixin, CreateView):
    model = Bank
    form_class = BankForm
    form_title = _('New bank')
    success_url = reverse_lazy('banking:list')


class BankUpdateView(OwnedFormMixin, UpdateView):
    model = Bank
    form_class = BankForm
    form_title = _('Edit bank')

    def get_success_url(self):
        return reverse('banking:detail', args=[self.object.pk])

    def get_cancel_url(self):
        return reverse('banking:detail', args=[self.object.pk])


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

    def get_success_url(self):
        bank = self.get_bank()
        return reverse('banking:detail', args=[bank.pk]) if bank else reverse('banking:list')

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


class BankAccountCreateView(RelatedFormMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    form_title = _('New account')


class BankAccountUpdateView(RelatedFormMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    form_title = _('Edit account')


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


class LoyaltyProgramCreateView(RelatedFormMixin, CreateView):
    model = LoyaltyProgram
    form_class = LoyaltyProgramForm
    form_title = _('New loyalty program')


class LoyaltyProgramUpdateView(RelatedFormMixin, UpdateView):
    model = LoyaltyProgram
    form_class = LoyaltyProgramForm
    form_title = _('Edit loyalty program')


class OwnedDeleteView(LoginRequiredMixin, DeleteView):
    template_name = 'banking/confirm_delete.html'
    context_object_name = 'item'

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse('banking:list')

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                _('This item cannot be deleted because financial records still reference it.'),
            )
            return redirect(self.get_success_url())
        messages.success(self.request, _('Item deleted.'))
        return response


class BankDeleteView(OwnedDeleteView):
    model = Bank


class BankAccountDeleteView(OwnedDeleteView):
    model = BankAccount


class DebitCardDeleteView(OwnedDeleteView):
    model = DebitCard


class CreditCardDeleteView(OwnedDeleteView):
    model = CreditCard


class LoyaltyProgramDeleteView(OwnedDeleteView):
    model = LoyaltyProgram


class OperationFormMixin(LoginRequiredMixin, FormView):
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
        context['cancel_url'] = reverse('banking:list')
        return context


class BankTransferCreateView(OperationFormMixin):
    form_class = BankTransferForm
    form_title = _('Transfer between my accounts')

    def form_valid(self, form):
        create_transfer(user=self.request.user, **form.cleaned_data)
        messages.success(self.request, _('Transfer recorded without changing income or expenses.'))
        return super().form_valid(form)


class LoyaltyEntryCreateView(OwnedFormMixin, CreateView):
    model = LoyaltyEntry
    form_class = LoyaltyEntryForm
    form_title = _('New points or miles entry')
    success_url = reverse_lazy('banking:list')

    def get_initial(self):
        initial = super().get_initial()
        initial['date'] = timezone.localdate()
        for field in ('program', 'invoice'):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
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
    success_url = reverse_lazy('banking:list')

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

    def form_valid(self, form):
        with transaction.atomic():
            cleanup_loyalty_entry_funding(self.object)
            response = super().form_valid(form)
            sync_user_ledger(self.request.user)
        return response


class RewardRedemptionCreateView(OperationFormMixin):
    form_class = RewardRedemptionForm
    form_title = _('Convert points or miles to account balance')

    def form_valid(self, form):
        try:
            with transaction.atomic():
                create_reward_redemption(user=self.request.user, **form.cleaned_data)
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


class ExchangeRateListView(LoginRequiredMixin, ListView):
    model = ExchangeRate
    template_name = 'banking/exchange_rates.html'
    context_object_name = 'rates'

    def get_queryset(self):
        return ExchangeRate.objects.filter(user=self.request.user)


class ExchangeRateCreateView(OwnedFormMixin, CreateView):
    model = ExchangeRate
    form_class = ExchangeRateForm
    form_title = _('New exchange rate')
    success_url = reverse_lazy('banking:exchange_rates')
