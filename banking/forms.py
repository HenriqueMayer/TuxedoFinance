from django import forms
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from core.dates import configure_date_fields

from banking.models import (
    Bank,
    BankAccount,
    BankTransfer,
    CardInvoice,
    CreditCard,
    DebitCard,
    ExchangeRate,
    InvoicePayment,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)


INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-hidden focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)


class OwnedModelForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        configure_date_fields(self, user)
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
        fields = ('name', 'color')
        labels = {'name': _('Name'), 'color': _('Marker color')}
        widgets = {'color': forms.TextInput(attrs={'type': 'color', 'list': 'bank-color-palette'})}

    def clean_color(self):
        return (self.cleaned_data.get('color') or self.instance.color or '#B88D57').upper()

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if self.user and self._duplicate(Bank.objects.filter(user=self.user, name=name)):
            raise forms.ValidationError(_('You already have a bank with this name.'))
        return name


class BankColorForm(BankForm):
    class Meta(BankForm.Meta):
        fields = ('color',)


class BankAccountForm(OwnedModelForm):
    class Meta:
        model = BankAccount
        fields = (
            'bank', 'name', 'currency', 'opening_balance', 'opening_date', 'pix_enabled',
            'planning_enabled', 'reserved_amount',
        )
        widgets = {
            'opening_balance': forms.NumberInput(attrs={'step': '0.01'}),
            'reserved_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
        help_texts = {
            'opening_balance': _('Balance immediately before the first ledger movement.'),
            'opening_date': _('Balance at the start of this date, before its movements. Legacy dates may remain unknown.'),
            'planning_enabled': _('Include this account in monthly planning. Negative balances remain visible.'),
            'reserved_amount': _('Keep this amount outside planning. The account balance and history do not change.'),
        }
        labels = {
            'bank': _('Bank'),
            'name': _('Name'),
            'currency': _('Currency'),
            'opening_balance': _('Opening balance'),
            'opening_date': _('Opening balance date'),
            'pix_enabled': _('Pix enabled'),
            'planning_enabled': _('Use in monthly planning'),
            'reserved_amount': _('Reserved amount'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reserved_amount'].required = False
        if self.user is not None:
            self.fields['bank'].queryset = Bank.objects.filter(user=self.user)

    def clean_reserved_amount(self):
        return self.cleaned_data.get('reserved_amount') or 0

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
            opening_date = cleaned.get('opening_date')
            if opening_date and original.movements.filter(effective_date__lt=opening_date).exists():
                self.add_error('opening_date', _('Review earlier movements before changing the opening balance date.'))
        elif cleaned.get('opening_balance') and not cleaned.get('opening_date'):
            self.add_error('opening_date', _('Enter the date of a new opening balance.'))
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
        fields = ('account', 'name', 'card_type', 'closing_day', 'due_day', 'manual_settlement_from')
        widgets = {
            'closing_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
            'due_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
        }
        help_texts = {
            'closing_day': _('Purchases on or after this day enter the next statement.'),
            'due_day': _('Clamped to the last day in shorter months.'),
            'manual_settlement_from': format_lazy('{} {}', CreditCard._meta.get_field('manual_settlement_from').help_text, _('Existing confirmed invoices keep their mode if this date is changed or cleared.')),
        }
        labels = {
            'account': _('Account'),
            'name': _('Name'),
            'card_type': _('Card type'),
            'closing_day': _('Closing day'),
            'due_day': _('Due day'),
            'manual_settlement_from': _('Confirm payments from'),
        }

    def clean_manual_settlement_from(self):
        value = self.cleaned_data.get('manual_settlement_from')
        original = CreditCard.objects.filter(pk=self.instance.pk).values_list('manual_settlement_from', flat=True).first() if self.instance.pk else None
        if value and value != original and value < timezone.localdate():
            raise forms.ValidationError(_('Choose today or a future date to preserve historical automatic payments.'))
        return value


class InvoicePaymentForm(OwnedModelForm):
    confirmation_key = forms.UUIDField(widget=forms.HiddenInput)
    class Meta:
        model = InvoicePayment
        fields = ('account', 'amount', 'date', 'notes')
        labels = {'account': _('Payment account'), 'amount': _('Amount paid'), 'date': _('Payment date'), 'notes': _('Notes')}
        widgets = {'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}), 'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, invoice, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.invoice = invoice
        self.initial['confirmation_key'] = self.instance.confirmation_key
        self.fields['account'].queryset = BankAccount.objects.filter(user=self.user, currency=invoice.account.currency).select_related('bank')

    def save(self, commit=True):
        payment = super().save(commit=False)
        if not payment.pk:
            payment.confirmation_key = self.cleaned_data['confirmation_key']
        if commit:
            payment.save()
        return payment


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
        self.locked_bank = kwargs.pop('locked_bank', None)
        super().__init__(*args, **kwargs)
        if self.user is not None:
            self.fields['bank'].queryset = Bank.objects.filter(user=self.user)
            cards = CreditCard.objects.filter(user=self.user).select_related('account__bank')
            if self.locked_bank is not None:
                self.fields['bank'].queryset = self.fields['bank'].queryset.filter(
                    pk=self.locked_bank.pk
                )
                self.fields['bank'].initial = self.locked_bank.pk
                self.fields['bank'].disabled = True
                cards = cards.filter(account__bank=self.locked_bank)
            bank_value = self.data.get('bank') if self.is_bound else None
            if not bank_value:
                bank_value = (
                    self.locked_bank
                    or self.initial.get('bank')
                    or self.instance.bank_id
                )
            if hasattr(bank_value, 'pk'):
                bank_value = bank_value.pk
            if bank_value:
                bank = Bank.objects.filter(pk=bank_value, user=self.user).first()
                if bank is not None:
                    cards = cards.filter(account__bank=bank)
            self.fields['cards'].queryset = cards

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
        bank = self.cleaned_data.get('bank')
        if bank and cards.exclude(account__bank=bank).exists():
            raise forms.ValidationError(_('Every selected card must belong to the selected bank.'))
        return cards

    def clean_bank(self):
        bank = self.cleaned_data.get('bank')
        if self.locked_bank is not None and bank != self.locked_bank:
            raise forms.ValidationError(_('The program must belong to the selected bank.'))
        return bank


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
    def clean(self):
        cleaned = super().clean()
        pair_date = {field: cleaned.get(field) for field in (
            'from_currency', 'to_currency', 'effective_date',
        )}
        if self.user and all(pair_date.values()) and self._duplicate(
            ExchangeRate.objects.filter(user=self.user, **pair_date)
        ):
            raise forms.ValidationError(_('A record with these values already exists.'))
        return cleaned

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
