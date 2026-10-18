# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bank workspaces, account presentation and planning participation."""

from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    Prefetch,
    Q,
    Sum,
    When,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView
from core.navigation import return_url
from banking.forms import RewardRedemptionForm
from banking.models import (
    Bank,
    BankAccount,
    BankMovement,
    CardInvoice,
    CreditCard,
    DebitCard,
    LoyaltyProgram,
    RewardRedemption,
)
from banking.services import get_planning_availability, set_position_planning
from transactions.services import sync_user_ledger
from .base import _canonical_id


def _programs(user):
    return LoyaltyProgram.objects.filter(user=user).annotate(
        displayed_balance=Sum(
            Case(When(entries__direction='CREDIT', then=F('entries__amount')),
                 default=-F('entries__amount'), output_field=DecimalField()),
            default=0,
        )
    )


def _accounts(user):
    # Account cards are rendered by both full pages and planning fragments.
    # Legacy cross-owner card references must stay private in either response.
    return BankAccount.objects.filter(user=user).prefetch_related(
        Prefetch('debit_cards', queryset=DebitCard.objects.filter(user=user)),
        Prefetch('credit_cards', queryset=CreditCard.objects.filter(user=user)),
    )


def _bank_index(user):
    """Owned identity/counts for the inline bank index, without loading balances twice."""
    return Bank.objects.filter(user=user).annotate(
        account_count=Count('accounts', filter=Q(accounts__user=user), distinct=True),
        owned_credit_count=Count(
            'accounts__credit_cards',
            filter=Q(accounts__user=user, accounts__credit_cards__user=user), distinct=True,
        ),
        owned_debit_count=Count(
            'accounts__debit_cards',
            filter=Q(accounts__user=user, accounts__debit_cards__user=user), distinct=True,
        ),
    ).annotate(card_count=F('owned_credit_count') + F('owned_debit_count')).order_by('name', 'pk')


def _decorate_banks(banks, availability):
    rows = {row['account'].pk: row for row in availability['account_rows']}
    for bank in banks:
        bank.planning_rows = []
        for account in bank.accounts.all():
            row = dict(rows[account.pk])
            row['account'] = account
            bank.planning_rows.append(row)
        bank.cash_pots = [row for row in availability['cash_pots'] if row['product'].bank_id == bank.pk]
        bank.included_rows = [row for row in bank.planning_rows if row['account'].planning_enabled]
        bank.reserved_rows = [row for row in bank.planning_rows if not row['account'].planning_enabled]
        bank.included_pots = [row for row in bank.cash_pots if row['planning_enabled']]
        bank.reserved_pots = [row for row in bank.cash_pots if not row['planning_enabled']]
        bank.account_count = len(bank.planning_rows)
        bank.card_count = sum(len(account.credit_cards.all()) + len(account.debit_cards.all()) for account in bank.accounts.all())


def _planning_destination(request, bank_id, anchor):
    fallback = reverse('banking:list') if request.POST.get('return_to') == 'list' else reverse('banking:detail', args=[bank_id])
    target = urlsplit(return_url(request, fallback))
    if target.path not in (reverse('banking:list'), reverse('banking:detail', args=[bank_id])):
        return urlunsplit(target)
    query = dict(parse_qsl(target.query, keep_blank_values=True))
    if target.path == reverse('banking:list'):
        query['open'] = str(bank_id)
    # A native POST must return to the row it just moved into Reserves too.
    if request.POST.get('enabled') == '0':
        query['reserves'] = str(bank_id)
    return urlunsplit((target.scheme, target.netloc, target.path, urlencode(query), anchor))


def _position_response(request, bank_id, *, reserve_open=False):
    bank = get_object_or_404(Bank.objects.prefetch_related(
        Prefetch('accounts', queryset=_accounts(request.user))), pk=bank_id, user=request.user)
    availability = get_planning_availability(request.user)
    _decorate_banks([bank], availability)
    return render(request, 'banking/_positions_response.html', {'bank': bank, 'availability': availability,
        'return_to': request.POST.get('return_to', 'detail'), 'reserve_open': reserve_open,
        'planning_return_url': return_url(request, reverse('banking:detail', args=[bank_id]))})


@login_required
@require_POST
def account_planning(request, pk):
    account = get_object_or_404(BankAccount, pk=pk, user=request.user)
    enabled = request.POST.get('enabled')
    if enabled not in {'0', '1'}:
        return HttpResponseBadRequest('Invalid planning selection.')
    account.planning_enabled = enabled == '1'
    account.save(update_fields=['planning_enabled', 'updated_at'])
    if request.headers.get('HX-Target') == f'bank-positions-{account.bank_id}':
        return _position_response(request, account.bank_id, reserve_open=True)
    if request.headers.get('HX-Target') == f'account-row-{account.pk}':
        availability = get_planning_availability(request.user)
        row = next(row for row in availability['account_rows'] if row['account'].pk == account.pk)
        row['account'] = _accounts(request.user).get(pk=account.pk)
        return render(request, 'banking/_planning_response.html', {
            'row': row, 'availability': availability,
            'return_to': request.POST.get('return_to', 'detail'),
            'account_origin': return_url(request, reverse('banking:detail', args=[account.bank_id])),
            'planning_return_url': return_url(request, reverse('banking:detail', args=[account.bank_id])),
        })
    messages.success(request, _('Planning availability updated. The account balance is unchanged.'))
    return redirect(_planning_destination(request, account.bank_id, f'account-row-{account.pk}'))


@login_required
@require_POST
def position_planning(request, product_pk, asset_pk):
    from investments.models import Asset, InvestmentProduct
    product = get_object_or_404(InvestmentProduct, user=request.user, bank__user=request.user, pk=product_pk)
    get_object_or_404(Asset, user=request.user, pk=asset_pk)
    enabled = request.POST.get('enabled')
    if enabled not in {'0', '1'}:
        return HttpResponseBadRequest('Invalid planning selection.')
    try:
        set_position_planning(request.user, product_pk, asset_pk, enabled == '1')
    except ValidationError:
        raise Http404
    if request.headers.get('HX-Target') == f'bank-positions-{product.bank_id}':
        return _position_response(request, product.bank_id, reserve_open=True)
    messages.success(request, _('Planning availability updated. The position balance is unchanged.'))
    return redirect(_planning_destination(request, product.bank_id, f'cash-position-{product_pk}-{asset_pk}'))


class BankListView(LoginRequiredMixin, ListView):
    model = Bank
    template_name = 'banking/list.html'
    context_object_name = 'banks'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            sync_user_ledger(request.user)
            # Older native planning returns use ?open=. Resolve that owned
            # destination to the same canonical URL used by the inline tabs.
            selected = request.GET.get('open') if request.method == 'GET' else None
            if selected:
                if not _canonical_id(selected):
                    raise Http404
                bank = get_object_or_404(Bank, pk=selected, user=request.user)
                query = request.GET.copy()
                query.pop('open')
                destination = reverse('banking:detail', args=[bank.pk])
                if query:
                    destination += '?' + query.urlencode()
                return redirect(destination)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        accounts = _accounts(self.request.user)
        queryset = Bank.objects.filter(user=self.request.user).prefetch_related(
            Prefetch('accounts', queryset=accounts),
            Prefetch(
                'loyalty_programs',
                queryset=_programs(self.request.user),
            ),
        )
        return queryset.order_by('name', 'pk')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
        accounts = _accounts(self.request.user)
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
        context['banks'] = _bank_index(self.request.user)
        context['selected_bank'] = self.object
        context['reserve_open'] = self.request.GET.get('reserves') == str(self.object.pk)
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
            # Only an explicit origin is posted: without one, saving a changed
            # target account must still return to its new receiving bank.
            context['redemption_origin'] = return_url(self.request, '')
            context['redemption_cancel_url'] = return_url(self.request,
                reverse('banking:detail', args=[self.object.pk]) + f'#reward-redemption-{editing.pk}')
        return context
