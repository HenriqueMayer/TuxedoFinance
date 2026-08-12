from django import forms
from django.utils.translation import gettext_lazy as _

from banking.models import (
    Bank,
    BankAccount,
    BankTransfer,
    CardInvoice,
    CreditCard,
    DebitCard,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)


INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-300 dark:border-slate-600 '
    'bg-white dark:bg-[#313335] px-3.5 py-2.5 text-slate-900 '
    'dark:text-neutral-100 placeholder:text-slate-400 '
    'dark:placeholder:text-neutral-500 focus:border-indigo-500 '
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)


class OwnedModelForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            self.instance.user = user
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES

    def _duplicate(self, queryset):
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        return queryset.exists()


class BankForm(OwnedModelForm):
    class Meta:
        model = Bank
        fields = ('name',)
        labels = {'name': _('Name')}

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.user and self._duplicate(Bank.objects.filter(user=self.user, name=name)):
            raise forms.ValidationError(_('You already have a bank with this name.'))
        return name


class BankAccountForm(OwnedModelForm):
    class Meta:
        model = BankAccount
        fields = ('bank', 'name', 'currency', 'opening_balance', 'pix_enabled')
        widgets = {
            'opening_balance': forms.NumberInput(attrs={'step': '0.01'}),
        }
        help_texts = {
            'opening_balance': _('Balance immediately before the first ledger movement.'),
        }
        labels = {
            'bank': _('Bank'),
            'name': _('Name'),
            'currency': _('Currency'),
            'opening_balance': _('Opening balance'),
            'pix_enabled': _('Pix enabled'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.user is not None:
            self.fields['bank'].queryset = Bank.objects.filter(user=self.user)

    def clean(self):
        cleaned = super().clean()
        bank = cleaned.get('bank')
        name = cleaned.get('name')
        currency = cleaned.get('currency')
        if bank and name and currency and self._duplicate(
            BankAccount.objects.filter(bank=bank, name=name, currency=currency)
        ):
            self.add_error('name', _('This bank already has an account with this name and currency.'))
        if self.instance.pk:
            original = BankAccount.objects.get(pk=self.instance.pk)
            has_history = (
                original.movements.exists()
                or original.transactions.exists()
                or original.debit_cards.filter(transactions__isnull=False).exists()
                or original.credit_cards.filter(transactions__isnull=False).exists()
            )
            if has_history and currency != original.currency:
                self.add_error('currency', _('Currency cannot change after financial activity.'))
            if has_history and bank != original.bank:
                self.add_error('bank', _('The bank cannot change after financial activity.'))
        return cleaned


class CardForm(OwnedModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.user is not None:
            self.fields['account'].queryset = BankAccount.objects.filter(
                user=self.user
            ).select_related('bank')

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get('account')
        name = cleaned.get('name')
        if account and name and self._duplicate(
            self._meta.model.objects.filter(account=account, name=name)
        ):
            self.add_error('name', _('This account already has a card with this name.'))
        if self.instance.pk and account:
            original = self._meta.model.objects.get(pk=self.instance.pk)
            has_history = original.transactions.exists()
            if isinstance(original, CreditCard):
                has_history = has_history or original.invoices.exists()
            if has_history and account != original.account:
                self.add_error('account', _('The account cannot change after card activity.'))
        return cleaned


class DebitCardForm(CardForm):
    class Meta:
        model = DebitCard
        fields = ('account', 'name')
        labels = {'account': _('Account'), 'name': _('Name')}


class CreditCardForm(CardForm):
    class Meta:
        model = CreditCard
        fields = ('account', 'name', 'closing_day', 'due_day')
        widgets = {
            'closing_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
            'due_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
        }
        help_texts = {
            'closing_day': _('Purchases on or after this day enter the next statement.'),
            'due_day': _('Clamped to the last day in shorter months.'),
        }
        labels = {
            'account': _('Account'),
            'name': _('Name'),
            'closing_day': _('Closing day'),
            'due_day': _('Due day'),
        }


class LoyaltyProgramForm(OwnedModelForm):
    class Meta:
        model = LoyaltyProgram
        fields = ('name', 'bank', 'cards', 'unit_name')
        widgets = {'cards': forms.SelectMultiple(attrs={'size': '6'})}
        help_texts = {
            'bank': _('Optional. Independent programs may have no bank.'),
            'cards': _('Optional. Select one or more eligible credit cards.'),
        }
        labels = {
            'name': _('Name'),
            'bank': _('Bank'),
            'cards': _('Cards'),
            'unit_name': _('Unit name'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.user is not None:
            self.fields['bank'].queryset = Bank.objects.filter(user=self.user)
            self.fields['cards'].queryset = CreditCard.objects.filter(
                user=self.user
            ).select_related('account__bank')

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.user and self._duplicate(
            LoyaltyProgram.objects.filter(user=self.user, name=name)
        ):
            raise forms.ValidationError(_('You already have a loyalty program with this name.'))
        return name

    def clean_cards(self):
        cards = self.cleaned_data['cards']
        if self.user is not None and cards.exclude(user=self.user).exists():
            raise forms.ValidationError(_('Every card must belong to you.'))
        return cards


class BankTransferForm(OwnedModelForm):
    class Meta:
        model = BankTransfer
        fields = (
            'source_account',
            'destination_account',
            'source_amount',
            'destination_amount',
            'date',
            'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'source_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'destination_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'destination_amount': _('For another currency, enter the amount actually received.'),
        }
        labels = {
            'source_account': _('Source account'),
            'destination_account': _('Destination account'),
            'source_amount': _('Source amount'),
            'destination_amount': _('Destination amount'),
            'date': _('Date'),
            'notes': _('Notes'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = BankAccount.objects.none()
        if self.user is not None:
            accounts = BankAccount.objects.filter(user=self.user).select_related('bank')
        self.fields['source_account'].queryset = accounts
        self.fields['destination_account'].queryset = accounts


class LoyaltyEntryForm(OwnedModelForm):
    class Meta:
        model = LoyaltyEntry
        fields = (
            'program',
            'direction',
            'kind',
            'amount',
            'date',
            'invoice',
            'funding_account',
            'funding_credit_card',
            'cash_amount',
            'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'cash_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'program': _('Program'),
            'direction': _('Direction'),
            'kind': _('Kind'),
            'amount': _('Points or miles'),
            'date': _('Date'),
            'invoice': _('Invoice'),
            'funding_account': _('Funding account'),
            'funding_credit_card': _('Funding credit card'),
            'cash_amount': _('Amount paid'),
            'notes': _('Notes'),
        }
        help_texts = {
            'invoice': _('Required only for points awarded from a selected credit-card invoice.'),
            'funding_account': _('For purchased points, choose this or a credit card.'),
            'cash_amount': _('Required only when purchasing points.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.user is not None:
            self.fields['program'].queryset = LoyaltyProgram.objects.filter(user=self.user)
            self.fields['invoice'].queryset = CardInvoice.objects.filter(
                user=self.user
            ).select_related('card').order_by('-reference_month')
            self.fields['funding_account'].queryset = BankAccount.objects.filter(
                user=self.user
            ).select_related('bank')
            self.fields['funding_credit_card'].queryset = CreditCard.objects.filter(
                user=self.user
            ).select_related('account__bank')


class RewardRedemptionForm(OwnedModelForm):
    class Meta:
        model = RewardRedemption
        fields = (
            'program',
            'points',
            'target_account',
            'target_amount',
            'iof_amount',
            'iof_account',
            'iof_credit_card',
            'date',
            'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'points': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'target_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'iof_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'target_amount': _('Money credited in the target account currency.'),
            'iof_amount': _('If positive, choose exactly one account or credit card below.'),
        }
        labels = {
            'program': _('Program'),
            'points': _('Points'),
            'target_account': _('Target account'),
            'target_amount': _('Target amount'),
            'iof_amount': _('Iof amount'),
            'iof_account': _('Iof account'),
            'iof_credit_card': _('Iof credit card'),
            'date': _('Date'),
            'notes': _('Notes'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.user is not None:
            self.fields['program'].queryset = LoyaltyProgram.objects.filter(user=self.user)
            accounts = BankAccount.objects.filter(user=self.user).select_related('bank')
            self.fields['target_account'].queryset = accounts
            self.fields['iof_account'].queryset = accounts
            self.fields['iof_credit_card'].queryset = CreditCard.objects.filter(
                user=self.user
            ).select_related('account__bank')


class ExchangeRateForm(OwnedModelForm):
    class Meta:
        model = ExchangeRate
        fields = ('from_currency', 'to_currency', 'rate', 'effective_date', 'notes')
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'rate': forms.NumberInput(attrs={'step': '0.00000001', 'min': '0.00000001'}),
        }
        help_texts = {'rate': _('How many target-currency units equal one source unit.')}
        labels = {
            'from_currency': _('From currency'),
            'to_currency': _('To currency'),
            'rate': _('Rate'),
            'effective_date': _('Effective date'),
            'notes': _('Notes'),
        }
