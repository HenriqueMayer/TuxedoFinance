from django import forms
from django.utils.translation import gettext_lazy as _

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
        self.fields['category'].queryset = Category.objects.filter(user=user)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(user=user).select_related('bank')
        self.fields['debit_card'].queryset = DebitCard.objects.filter(user=user).select_related('account__bank')
        self.fields['credit_card'].queryset = CreditCard.objects.filter(user=user).select_related('account__bank')
        self.fields['installments'].required = False
        self.fields['billing_override'].choices = [
            ('', _('Automatic (from card cycle)')),
            (str(Transaction.BillChoice.CURRENT.value), _('Current bill')),
            (str(Transaction.BillChoice.NEXT.value), _('Next bill')),
        ]
        for name, field in self.fields.items():
            field.widget.attrs['class'] = CHECKBOX_CLASSES if name == 'is_fixed' else INPUT_CLASSES

    def clean_installments(self):
        installments = self.cleaned_data.get('installments')
        return 1 if installments is None else installments
