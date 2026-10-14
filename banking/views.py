from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, DecimalField, F, Prefetch, Q, Sum, When
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView
from core.currencies import CURRENCIES
from core.navigation import ReturnContextMixin, return_url, with_return_url

from banking.forms import (
    BankAccountForm,
    BankTransferForm,
    BankForm,
    BankColorForm,
    CreditCardForm,
    DebitCardForm,
    ExchangeRateForm,
    InvoicePaymentForm,
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
    InvoicePayment,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from banking.services import (
    cleanup_loyalty_entry_funding,
    create_reward_redemption,
    update_reward_redemption,
    create_transfer,
    sync_loyalty_entry_funding,
    get_planning_availability,
)
from transactions.services import sync_user_ledger
from banking.settlements import save_invoice_payment, delete_invoice_payment


def _programs(user):
    return LoyaltyProgram.objects.filter(user=user).annotate(
        displayed_balance=Sum(
            Case(When(entries__direction='CREDIT', then=F('entries__amount')),
                 default=-F('entries__amount'), output_field=DecimalField()),
            default=0,
        )
    )


def _decorate_banks(banks, availability):
    rows = {row['account'].pk: row for row in availability['account_rows']}
    for bank in banks:
        bank.planning_rows = []
        for account in bank.accounts.all():
            row = dict(rows[account.pk])
            row['account'] = account
            bank.planning_rows.append(row)
        bank.cash_pots = [row for row in availability['cash_pots'] if row['product'].bank_id == bank.pk]


@login_required
@require_POST
def account_planning(request, pk):
    account = get_object_or_404(BankAccount, pk=pk, user=request.user)
    enabled = request.POST.get('enabled')
    if enabled not in {'0', '1'}:
        return HttpResponseBadRequest('Invalid planning selection.')
    account.planning_enabled = enabled == '1'
    account.save(update_fields=['planning_enabled', 'updated_at'])
    if request.headers.get('HX-Target') == f'account-row-{account.pk}':
        availability = get_planning_availability(request.user)
        row = next(row for row in availability['account_rows'] if row['account'].pk == account.pk)
        return render(request, 'banking/_planning_response.html', {
            'row': row, 'availability': availability,
            'return_to': request.POST.get('return_to', 'detail'),
        })
    messages.success(request, _('Planning availability updated. The account balance is unchanged.'))
    url = reverse('banking:list') if request.POST.get('return_to') == 'list' else reverse('banking:detail', args=[account.bank_id])
    return redirect(f'{url}#account-row-{account.pk}')


class BankListView(LoginRequiredMixin, ListView):
    model = Bank
    template_name = 'banking/list.html'
    context_object_name = 'banks'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
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
                queryset=_programs(self.request.user),
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
        context['independent_programs'] = _programs(self.request.user).filter(bank__isnull=True).prefetch_related('cards')
        context['availability'] = get_planning_availability(self.request.user)
        _decorate_banks(context['banks'], context['availability'])
        return context


class BankDetailView(LoginRequiredMixin, DetailView):
    model = Bank
    template_name = 'banking/detail.html'
    context_object_name = 'bank'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
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
                queryset=_programs(self.request.user).prefetch_related(
                    'cards'
                ),
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account_ids = [account.pk for account in self.object.accounts.all()]
        context['availability'] = get_planning_availability(self.request.user)
        _decorate_banks([self.object], context['availability'])
        context['movements'] = BankMovement.objects.filter(
            user=self.request.user, account_id__in=account_ids
        ).select_related('account').order_by('-effective_date', '-created_at')[:20]
        context['invoices'] = CardInvoice.objects.filter(
            user=self.request.user, card__account_id__in=account_ids
        ).select_related('card__account').order_by('-reference_month')[:12]
        # A card-funded IOF is part of an aggregate invoice, not a separate
        # cash movement. Show its source in both receiving and funding banks.
        redemption_query = RewardRedemption.objects.filter(user=self.request.user).filter(
            Q(target_account_id__in=account_ids)
            | Q(iof_account_id__in=account_ids)
            | Q(iof_credit_card__account_id__in=account_ids)
        ).select_related(
            'program', 'target_account__bank', 'iof_account__bank',
            'iof_credit_card__account__bank',
        ).order_by('-date', '-created_at', '-pk')
        editing = kwargs.get('editing_redemption')
        if not editing and self.request.GET.get('edit_redemption'):
            if not self.request.GET['edit_redemption'].isdigit():
                raise Http404
            editing = get_object_or_404(redemption_query, pk=self.request.GET['edit_redemption'])
        redemptions = list(redemption_query[:20])
        if editing and editing not in redemptions:
            redemptions.insert(0, editing)
        for redemption in redemptions:
            if redemption.iof_credit_card_id:
                card = redemption.iof_credit_card
                redemption.iof_reference_month = card.statement_month(redemption.date)
                redemption.iof_due_date = card.due_date_for(redemption.iof_reference_month)
        context['redemptions'] = redemptions
        if editing:
            context['editing_redemption'] = editing
            context['redemption_form'] = kwargs.get('redemption_form') or RewardRedemptionForm(
                user=self.request.user, instance=editing, prefix='redemption',
            )
        return context


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


class InvoiceListView(LoginRequiredMixin, ListView):
    template_name = 'banking/invoices.html'
    context_object_name = 'invoices'
    paginate_by = 30

    def get_queryset(self):
        sync_user_ledger(self.request.user)
        invoices = CardInvoice.objects.filter(user=self.request.user).select_related('card__account__bank').prefetch_related('payments')
        card_id = self.request.GET.get('card', '')
        if card_id:
            if (not card_id.isascii() or not card_id.isdigit()
                    or len(card_id) > 19 or int(card_id) > 9223372036854775807):
                raise Http404
            self.card = get_object_or_404(CreditCard, user=self.request.user, pk=card_id)
            invoices = invoices.filter(card=self.card)
        return invoices

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {'selected_card': getattr(self, 'card', None)}


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
    return render(request, 'banking/invoice_detail.html', {'invoice': invoice, 'form': form, 'sources': [(item, amount) for item, amount in sources if amount],
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
    invoice_id = payment.invoice_id
    if request.method == 'POST':
        delete_invoice_payment(payment)
        return redirect('banking:invoice_detail', pk=invoice_id)
    return render(request, 'banking/payment_delete.html', {'payment': payment})


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
        return redirect(f'{url}?edit_redemption={redemption.pk}#reward-redemption-{redemption.pk}')

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
        return redirect(f'{url}#reward-redemption-{self.object.pk}')

    def form_invalid(self, form):
        # Validation recovery stays inside the source section, with the bound
        # selections and errors rather than an independent transaction editor.
        original = self.get_object()
        view = BankDetailView()
        view.setup(self.request, pk=original.target_account.bank_id)
        view.object = view.get_object()
        context = view.get_context_data(editing_redemption=original, redemption_form=form)
        return render(self.request, 'banking/detail.html', context)


class ExchangeRateListView(LoginRequiredMixin, ListView):
    model = ExchangeRate
    template_name = 'banking/exchange_rates.html'
    context_object_name = 'rates'

    def get_queryset(self):
        return ExchangeRate.objects.filter(user=self.request.user)


class ExchangeRateFormMixin(OwnedFormMixin):
    model = ExchangeRate
    form_class = ExchangeRateForm
    success_url = reverse_lazy('banking:exchange_rates')

    def get_cancel_url(self):
        return reverse('banking:exchange_rates')


class ExchangeRateCreateView(ExchangeRateFormMixin, CreateView):
    form_title = _('New exchange rate')

    def get_initial(self):
        initial = super().get_initial()
        for name in ('from_currency', 'to_currency'):
            value = self.request.GET.get(name, '')
            if value in CURRENCIES:
                initial[name] = value
        try:
            initial['effective_date'] = date.fromisoformat(self.request.GET.get('effective_date', ''))
        except ValueError:
            pass
        # A diagnostic may preselect the pair/date, never guess the price.
        return initial


class ExchangeRateUpdateView(ExchangeRateFormMixin, UpdateView):
    form_title = _('Edit exchange rate')


class ExchangeRateDeleteView(OwnedDeleteView):
    model = ExchangeRate

    def get_success_url(self):
        return reverse('banking:exchange_rates')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.get_success_url()
        context['delete_message'] = _(
            'This action cannot be undone. Current valuations may change or show missing rates. '
            'Conversions already saved in transfers and investments will be preserved.'
        )
        return context
