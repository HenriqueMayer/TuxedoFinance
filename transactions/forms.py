from django import forms
from django.utils.translation import gettext_lazy as _

from core.dates import configure_date_fields, date_order
from core.widgets import SegmentedChoice, SelectWithMetadata
from banking.models import BankAccount, CreditCard, DebitCard
from categories.models import Category
from transactions.models import Transaction, TransactionSplit


INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-none focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)
CHECKBOX_CLASSES = (
    'h-5 w-5 rounded-md border-forest/20 bg-white accent-caramel '
    'focus:outline-none focus:ring-2 focus:ring-caramel/30 dark:border-cream/20 dark:bg-night'
)


class TransactionSelect(SelectWithMetadata):
    """Expose safe, server-scoped choice metadata to the progressive UI."""


class TransactionForm(forms.ModelForm):
    split_categories = forms.BooleanField(
        required=False, label=_('Split between categories'),
        help_text=_('Allocate the full amount between categories. This remains one transaction and one payment.'),
    )

    class Meta:
        model = Transaction
        fields = (
            'title', 'amount', 'transaction_type', 'category', 'payment_channel',
            'bank_account', 'debit_card', 'credit_card', 'installments',
            'billing_override', 'date', 'is_fixed', 'fixed_until', 'notes',
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'fixed_until': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'installments': forms.NumberInput(
                attrs={'step': '1', 'min': '1', 'max': str(Transaction.MAX_INSTALLMENTS)}
            ),
        }
        labels = {
            'title': _('Title'),
            'amount': _('Amount'),
            'transaction_type': _('Transaction type'),
            'category': _('Category'),
            'payment_channel': _('Payment channel'),
            'bank_account': _('Bank account (Account or PIX)'),
            'debit_card': _('Debit card'),
            'credit_card': _('Credit card'),
            'installments': _('Installments'),
            'billing_override': _('Bill choice'),
            'date': _('Transaction date'),
            'is_fixed': _('Fixed / recurring transaction'),
            'fixed_until': _('Repeat until'),
            'notes': _('Notes'),
        }
        help_texts = {
            'is_fixed': _(
                'Repeats monthly; it cannot also be an installment plan.'
            ),
            'fixed_until': _('Optional last recurrence month, inclusive.'),
        }

    def __init__(self, *args, user=None, manage_splits=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.manage_splits = manage_splits
        if user is not None:
            self.instance.user = user
        if not self.is_bound and self.instance.pk:
            self.initial.setdefault('split_categories', self.instance.splits.exists())
        split_selected = (self.data.get('split_categories') if self.is_bound
                          else self.initial.get('split_categories'))
        if self.manage_splits and split_selected:
            # The first reviewed allocation supplies the structural fallback
            # category; the full split owns reporting classification.
            self.fields['category'].required = False
        configure_date_fields(self, user)
        self.fields['category'].queryset = Category.objects.filter(user=user)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(user=user).select_related('bank')
        self.fields['debit_card'].queryset = DebitCard.objects.filter(user=user).select_related('account__bank')
        self.fields['credit_card'].queryset = CreditCard.objects.filter(user=user).select_related('account__bank')
        self.fields['debit_card'].label_from_instance = lambda card: (
            f'{card.name} - {card.account.bank.name} > {card.account.name} ({card.account.currency})'
        )
        self.fields['credit_card'].label_from_instance = lambda card: (
            f'{card.name} - {card.account.bank.name} > {card.account.name} ({card.account.currency})'
        )
        self.fields['installments'].required = False
        self.fields['credit_card'].help_text = _(
            'Invoices follow the selected card settlement settings. Automatic mode records settlement on the due date; confirmed mode changes cash only after a confirmed payment. The app does not pay the bank.'
        )
        self.fields['billing_override'].choices = [
            ('', _('Automatic (from card cycle)')),
            (str(Transaction.BillChoice.CURRENT.value), _('Current bill')),
            (str(Transaction.BillChoice.NEXT.value), _('Next bill')),
        ]
        categories = list(self.fields['category'].queryset.select_related('parent_category'))
        accounts = list(self.fields['bank_account'].queryset)
        debit_cards = list(self.fields['debit_card'].queryset)
        credit_cards = list(self.fields['credit_card'].queryset)
        self._set_choice_data(
            'category',
            {
                str(category.pk): {
                    'data-search': ' '.join(
                        part for part in (category.parent_category.name if category.parent_category else '', category.name)
                    ),
                    'data-transaction-type': category.transaction_type or '',
                }
                for category in categories
            },
        )
        self._set_choice_data(
            'bank_account',
            {
                str(account.pk): {
                    'data-pix-enabled': str(account.pix_enabled).lower(),
                    'data-choice-name': account.name,
                    'data-choice-detail': f'{account.bank.name} · {account.currency}',
                    'data-bank-color': account.bank.color,
                }
                for account in accounts
            },
        )
        self._set_choice_data(
            'debit_card',
            {
                str(card.pk): {
                    'data-account-label': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})',
                    'data-card-name': card.name,
                    'data-choice-name': card.name,
                    'data-choice-detail': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})',
                    'data-bank-color': card.account.bank.color,
                    'data-card-color': card.color,
                    'data-card-gradient-end': card.gradient_end,
                    'data-card-gradient-angle': str(card.gradient_angle),
                }
                for card in debit_cards
            },
        )
        self._set_choice_data(
            'credit_card',
            {
                str(card.pk): {
                    'data-account-label': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})',
                    'data-card-name': card.name,
                    'data-choice-name': card.name,
                    'data-choice-detail': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})',
                    'data-bank-color': card.account.bank.color,
                    'data-card-color': card.color,
                    'data-card-gradient-end': card.gradient_end,
                    'data-card-gradient-angle': str(card.gradient_angle),
                    'data-best-purchase-day': str(card.best_purchase_day),
                    'data-settlement-description': (
                        _('New invoices due on or after %(date)s require confirmed payments. Existing invoices retain their recorded mode. The app does not pay the bank.')
                        % {'date': card.manual_settlement_from.strftime('%m/%d/%Y' if date_order(user) == 'MDY' else '%d/%m/%Y')}
                        if card.manual_settlement_from else
                        _('New invoices use automatic accounting on the due date. Existing invoices retain their recorded mode. The app does not pay the bank.')
                    ),
                }
                for card in credit_cards
            },
        )
        for name, field in self.fields.items():
            field.widget.attrs['class'] = CHECKBOX_CLASSES if name in ('is_fixed', 'split_categories') else INPUT_CLASSES
            described_by = []
            if field.help_text:
                described_by.append(f'{field.widget.attrs.get("id", "id_" + name)}-help')
            if self.is_bound and self.errors.get(name):
                field.widget.attrs['aria-invalid'] = 'true'
                described_by.extend(
                    f'{field.widget.attrs.get("id", "id_" + name)}-error-{index}'
                    for index in range(1, len(self.errors[name]) + 1)
                )
            if described_by:
                field.widget.attrs['aria-describedby'] = ' '.join(described_by)
        for name in ('transaction_type', 'payment_channel'):
            field = self.fields[name]
            field.choices = [(value, label) for value, label in field.choices if value]
            field.widget = SegmentedChoice(attrs={
                key: value for key, value in field.widget.attrs.items() if key != 'class'
            })
            field.widget.attrs['class'] = 'entry-segment-options'
            field.widget.choices = field.choices
        self.fields['amount'].widget.attrs['data-money-input'] = ''
        for name in ('bank_account', 'debit_card', 'credit_card'):
            self.fields[name].widget.attrs.update({
                'data-payment-choices': 'true',
                'data-payment-kind': 'account' if name == 'bank_account' else 'card',
            })
        for name, field in self.fields.items():
            if name not in ('transaction_type', 'payment_channel'):
                field.widget.attrs['class'] = CHECKBOX_CLASSES if name in ('is_fixed', 'split_categories') else 'entry-input'

    def _set_choice_data(self, field_name, choice_data):
        field = self.fields[field_name]
        widget = TransactionSelect(attrs=field.widget.attrs.copy())
        widget.choice_data = choice_data
        widget.choices = field.choices
        field.widget = widget

    def clean_installments(self):
        installments = self.cleaned_data.get('installments')
        return 1 if installments is None else installments

    def clean(self):
        cleaned = super().clean()
        if self.manage_splits and cleaned.get('split_categories'):
            cleaned['category'] = None
        if self.instance.pk and not self.manage_splits:
            splits = list(self.instance.splits.select_related('category'))
            if splits and cleaned.get('amount') != sum((row.amount for row in splits), 0):
                self.add_error('amount', _('Clear the category split before changing the total amount.'))
            if any(row.category.transaction_type and row.category.transaction_type != cleaned.get('transaction_type') for row in splits):
                self.add_error('transaction_type', _('Clear incompatible category splits before changing the transaction type.'))
        return cleaned


class TransactionSplitForm(forms.ModelForm):
    class Meta:
        model = TransactionSplit
        fields = ('category', 'amount')
        labels = {'category': _('Category'), 'amount': _('Category amount')}
        widgets = {'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'})}

    def __init__(self, *args, user=None, transaction_type=None, allow_type_changes=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_type_changes = allow_type_changes
        from django.db.models import Q
        categories = Category.objects.filter(user=user).select_related('parent_category')
        if not allow_type_changes:
            categories = categories.filter(Q(transaction_type__isnull=True) | Q(transaction_type='') | Q(transaction_type=transaction_type))
        self.fields['category'].queryset = categories
        widget = TransactionSelect()
        widget.choice_data = {str(category.pk): {'data-transaction-type': category.transaction_type or ''}
                              for category in categories}
        widget.choices = self.fields['category'].choices
        self.fields['category'].widget = widget
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
        if self.is_bound:
            raw_amount = self.data.get(self.add_prefix('amount'))
            if raw_amount not in (None, ''):
                try:
                    self.fields['amount'].clean(raw_amount)
                except forms.ValidationError:
                    # Inspect only the decimal field here. Full form validation
                    # must wait until the formset adds its owned hidden IDs.
                    self.fields['amount'].widget = forms.TextInput(attrs={
                        **self.fields['amount'].widget.attrs, 'inputmode': 'decimal',
                    })

    def validate_constraints(self):
        if not self.allow_type_changes:
            return super().validate_constraints()
        # Combined editing validates the final allocation set. Checking each
        # old row against the database would incorrectly reject category swaps.
        exclude = self._get_validation_exclusions()
        exclude.add('transaction')
        try:
            self.instance.validate_constraints(exclude=exclude)
        except forms.ValidationError as error:
            self._update_errors(error)


class BaseTransactionSplitFormSet(forms.BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        # A hidden identifier cannot select another transaction's allocation.
        form.fields['id'].queryset = self.get_queryset()
        form.fields['DELETE'].label = _('Remove category')
        form.fields['DELETE'].widget.attrs['class'] = CHECKBOX_CLASSES

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        rows = [form.cleaned_data for form in self.forms if form.cleaned_data and not form.cleaned_data.get('DELETE')]
        if len(rows) < 2:
            raise forms.ValidationError(_('Use at least two categories, or clear the split.'))
        if len({row['category'].pk for row in rows}) != len(rows):
            raise forms.ValidationError(_('Choose each category only once.'))
        if any(row['category'].transaction_type and row['category'].transaction_type != self.instance.transaction_type for row in rows):
            raise forms.ValidationError(_('Choose categories compatible with the transaction type.'))
        if self.instance.amount is not None:
            for form in self.forms:
                if form.cleaned_data and not form.cleaned_data.get('DELETE') and form.cleaned_data['amount'] > self.instance.amount:
                    form.add_error('amount', _('Category amount cannot exceed the transaction total.'))
            if any(self.errors):
                return
        if sum((row.get('amount', 0) for row in rows), 0) != self.instance.amount:
            raise forms.ValidationError(_('Category amounts must add up to the transaction total.'))


class TransactionDateFilterForm(forms.Form):
    date = forms.DateField(required=False, label=_("Transaction date"))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        configure_date_fields(self, user)
        self.fields['date'].widget.attrs.update({'id': 'filter-date', 'class': INPUT_CLASSES})
