import re

from django import forms
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from core.dates import configure_date_fields
from core.widgets import SegmentedChoice, SelectWithMetadata, SelectMultipleWithMetadata
from sandbox.forms import parse_month

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

    def _instrument_choice(self, name, kind):
        field = self.fields[name]
        widget_class = SelectMultipleWithMetadata if isinstance(field, forms.ModelMultipleChoiceField) else SelectWithMetadata
        widget = widget_class(attrs={**field.widget.attrs,
            'data-payment-choices': 'true', 'data-payment-kind': kind})

        def card_label(card):
            return f'{card.name} - {card.account.bank.name} > {card.account.name} ({card.account.currency})'

        def metadata(record):
            if kind == 'account':
                return {'data-choice-name': record.name,
                    'data-choice-detail': f'{record.bank.name} · {record.currency}',
                    'data-bank-color': record.bank.color}
            card = record.card if isinstance(record, CardInvoice) else record
            period = f' · {record.reference_month:%Y-%m}' if isinstance(record, CardInvoice) else ''
            return {'data-choice-name': card.name + period,
                'data-choice-detail': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})',
                'data-bank-color': card.account.bank.color,
                'data-card-color': card.color,
                'data-card-gradient-end': card.gradient_end,
                'data-card-gradient-angle': str(card.gradient_angle)}

        if kind == 'card':
            field.label_from_instance = lambda record: (
                f'{card_label(record.card)} · {record.reference_month:%Y-%m}'
                if isinstance(record, CardInvoice) else card_label(record))
        widget.choice_data = metadata
        widget.choices = field.choices
        field.widget = widget

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
    use_gradient = forms.BooleanField(required=False, label=_('Use a gradient'))
    is_card_form = True
    appearance_fields = ('color', 'use_gradient', 'gradient_end', 'gradient_angle')
    color_presets = (
        ('#253330', _('Graphite')),
        ('#5B3E7C', _('Plum')),
        ('#C6A173', _('Copper')),
        ('#315D50', _('Forest')),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instrument_choice('account', 'account')
        if self.user is not None:
            self.fields['account'].queryset = BankAccount.objects.filter(
                user=self.user
            ).select_related('bank')
        self.appearance_submitted = self.is_bound and any(
            self.add_prefix(name) in self.data for name in self.appearance_fields
        )
        if not self.instance.pk:
            self.fields['color'] = forms.ChoiceField(
                choices=self.color_presets, required=False, label=_('Card color'),
                initial='#253330', widget=SegmentedChoice(attrs={'class': 'entry-segment-options'}),
            )
        else:
            self.fields['color'].required = False
            self.fields['color'].label = _('Card color')
            self.fields['color'].widget = forms.TextInput(attrs={
                'type': 'color', 'class': INPUT_CLASSES,
            })
        self.fields['gradient_end'].label = _('Gradient end color')
        self.fields['gradient_end'].widget = forms.TextInput(attrs={
            'type': 'color', 'class': INPUT_CLASSES,
        })
        self.fields['gradient_angle'].label = _('Gradient angle')
        self.fields['gradient_angle'].required = False
        self.fields['gradient_angle'].widget.attrs.update({'min': 0, 'max': 359, 'step': 1})
        self.initial['use_gradient'] = bool(self.instance.gradient_end)
        self.initial['gradient_end'] = self.instance.gradient_end or self.instance.color
        self.fields['use_gradient'].widget.attrs['class'] = 'card-gradient-toggle'

    @property
    def card_record_fields(self):
        return [self[name] for name in self.fields if name not in self.appearance_fields]

    @property
    def card_preview_color(self):
        value = self['color'].value() or self.instance.color
        return value.upper() if re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)) else '#253330'

    @property
    def card_preview_end(self):
        if 'use_gradient' not in self.fields or not self['use_gradient'].value():
            return self.card_preview_color
        value = self['gradient_end'].value() or ''
        return value.upper() if re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)) else self.card_preview_color

    @property
    def card_preview_angle(self):
        try:
            value = int(self['gradient_angle'].value()) if 'gradient_angle' in self.fields else 135
        except (TypeError, ValueError):
            return 135
        return value if 0 <= value <= 359 else 135

    def clean_color(self):
        return (self.cleaned_data.get('color') or self.instance.color or '#253330').upper()

    def clean_gradient_angle(self):
        value = self.cleaned_data.get('gradient_angle')
        return self.instance.gradient_angle if value is None else value

    def clean(self):
        cleaned = super().clean()
        if not self.appearance_submitted:
            # Older integrations may still post the original financial form.
            cleaned['gradient_end'] = self.instance.gradient_end
            cleaned['gradient_angle'] = self.instance.gradient_angle
        elif not cleaned.get('use_gradient'):
            # Ignore inactive presentation inputs on create and edit, while
            # keeping native fields available after an invalid POST without JS.
            self._errors.pop('gradient_end', None)
            self._errors.pop('gradient_angle', None)
            cleaned['gradient_end'] = ''
            cleaned['gradient_angle'] = self.instance.gradient_angle
        elif not cleaned.get('gradient_end'):
            self.add_error('gradient_end', _('Choose a gradient end color.'))
        else:
            cleaned['gradient_end'] = cleaned['gradient_end'].upper()
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
        fields = ('account', 'name', 'color', 'gradient_end', 'gradient_angle')
        labels = {'account': _('Account'), 'name': _('Name')}


class CreditCardForm(CardForm):
    class Meta:
        model = CreditCard
        fields = ('account', 'name', 'card_type', 'closing_day', 'due_day', 'manual_settlement_from', 'color', 'gradient_end', 'gradient_angle')
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
        self._instrument_choice('account', 'account')
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
        self._instrument_choice('cards', 'card')
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
        for name in ('source_account', 'destination_account'):
            self._instrument_choice(name, 'account')
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
        self._instrument_choice('funding_account', 'account')
        for name in ('funding_credit_card', 'invoice'):
            self._instrument_choice(name, 'card')
        if self.user is not None:
            self.fields['program'].queryset = LoyaltyProgram.objects.filter(user=self.user)
            self.fields['invoice'].queryset = CardInvoice.objects.filter(
                user=self.user
            ).select_related('card__account__bank').order_by('-reference_month')
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
        for name in ('target_account', 'iof_account'):
            self._instrument_choice(name, 'account')
        self._instrument_choice('iof_credit_card', 'card')
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
            'from_currency': _('From currency (1 unit)'),
            'to_currency': _('To currency'),
            'rate': _('Value in the target currency'),
            'effective_date': _('Effective date'),
            'notes': _('Notes'),
        }


class InvoiceFilterForm(forms.Form):
    q = forms.CharField(required=False, label=_('Search'),
                        widget=forms.TextInput(attrs={'type': 'search', 'data-live-search': '', 'placeholder': _('Card, account or bank')}))
    month = forms.CharField(required=False, label=_('Invoice month'),
                            widget=forms.TextInput(attrs={'type': 'month', 'min': '1901-01', 'max': '9988-12', 'data-live-change': ''}))
    bank = forms.ModelChoiceField(required=False, queryset=Bank.objects.none(), label=_('Bank'), empty_label=_('All banks'))
    status = forms.ChoiceField(required=False, label=_('Status'), choices=[('', _('All statuses')), *CardInvoice.Status.choices])

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, auto_id='invoice-filter-%s', **kwargs)
        self.fields['bank'].queryset = Bank.objects.filter(user=user)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASSES
            if name != 'q':
                field.widget.attrs['data-live-change'] = ''
        # Keep malformed native month text recoverable after an invalid GET.
        if self.is_bound and self.errors.get('month'):
            self.fields['month'].widget = forms.TextInput(attrs={key: value for key, value in self.fields['month'].widget.attrs.items() if key != 'type'})

    def clean_month(self):
        value = self.cleaned_data['month']
        return parse_month(value) if value else None


class ExchangeRateFilterForm(forms.Form):
    q = forms.CharField(required=False, label=_('Search'),
                        widget=forms.TextInput(attrs={'type': 'search', 'data-live-search': '', 'placeholder': _('Currency or notes')}))
    from_currency = forms.ChoiceField(required=False, label=_('From currency (1 unit)'), choices=[('', _('All currencies')), *ExchangeRate._meta.get_field('from_currency').choices])
    to_currency = forms.ChoiceField(required=False, label=_('To currency'), choices=[('', _('All currencies')), *ExchangeRate._meta.get_field('to_currency').choices])
    date_from = forms.DateField(required=False, label=_('From date'))
    date_to = forms.DateField(required=False, label=_('To date'))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, auto_id='rate-filter-%s', **kwargs)
        configure_date_fields(self, user)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASSES
            if name != 'q':
                field.widget.attrs['data-live-change'] = ''

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            self.add_error('date_to', _('Choose an end date on or after the start date.'))
        return data
