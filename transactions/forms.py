from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import UserPreference
from banking.models import BankAccount, CreditCard, DebitCard
from categories.models import Category
from transactions.models import Transaction


INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-[#313335] px-3.5 py-2.5 '
    'text-slate-900 dark:text-neutral-100 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)
CHECKBOX_CLASSES = (
    'h-5 w-5 rounded-md border-slate-300 dark:border-slate-600 bg-white dark:bg-[#313335] text-indigo-500 '
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)


class TransactionSelect(forms.Select):
    """Expose safe, server-scoped choice metadata to the progressive UI."""

    choice_data = None

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if self.choice_data and value:
            option['attrs'].update(self.choice_data.get(str(value), {}))
        return option


class TransactionForm(forms.ModelForm):
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
            'payment_channel': _(
                'Select one channel, then select only its matching instrument below.'
            ),
            'bank_account': _('Required for Bank account and PIX channels.'),
            'debit_card': _('Required only for the Debit card channel.'),
            'credit_card': _('Required only for the Credit card channel.'),
            'installments': _(
                'Credit card only. Enter the full purchase total above.'
            ),
            'billing_override': _(
                'Credit card only. Automatic follows the card closing day.'
            ),
            'is_fixed': _(
                'Repeats monthly; it cannot also be an installment plan.'
            ),
            'fixed_until': _('Optional last recurrence month, inclusive.'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        date_order = UserPreference.for_user(user).date_format if user is not None else 'DMY'
        display_format = '%m/%d/%Y' if date_order == 'MDY' else '%d/%m/%Y'
        placeholder = 'MM/DD/YYYY' if date_order == 'MDY' else 'DD/MM/YYYY'
        for name in ('date', 'fixed_until'):
            field = self.fields[name]
            field.input_formats = [display_format, '%Y-%m-%d']
            field.widget = forms.DateInput(
                format=display_format,
                attrs={'placeholder': placeholder, 'inputmode': 'numeric'},
            )
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
            {str(account.pk): {'data-pix-enabled': str(account.pix_enabled).lower()} for account in accounts},
        )
        self._set_choice_data(
            'debit_card',
            {
                str(card.pk): {'data-account-label': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})'}
                for card in debit_cards
            },
        )
        self._set_choice_data(
            'credit_card',
            {
                str(card.pk): {'data-account-label': f'{card.account.bank.name} > {card.account.name} ({card.account.currency})'}
                for card in credit_cards
            },
        )
        for name, field in self.fields.items():
            field.widget.attrs['class'] = CHECKBOX_CLASSES if name == 'is_fixed' else INPUT_CLASSES
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

    def _set_choice_data(self, field_name, choice_data):
        field = self.fields[field_name]
        widget = TransactionSelect(attrs=field.widget.attrs.copy())
        widget.choice_data = choice_data
        widget.choices = field.choices
        field.widget = widget

    def clean_installments(self):
        installments = self.cleaned_data.get('installments')
        return 1 if installments is None else installments
