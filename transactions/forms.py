from django import forms

from categories.models import Category
from payments.models import PaymentMethod
from transactions.models import Transaction

# PRD §9.4 — the exact input classes shared by every form in the project.
# `partials/form_field.html` renders the label/help/errors but never injects
# classes into `{{ field }}`; the owning form is responsible for styling its
# own widgets, which is what the `__init__` override below does.
INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 '
    'text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 '
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)

# `is_fixed` visual toggle: a styled checkbox reusing the same PRD §9.1
# tokens (slate surface/border, indigo focus ring) since the design system
# does not define a dedicated checkbox/switch component yet.
CHECKBOX_CLASSES = (
    'h-5 w-5 rounded-md border-slate-700 bg-slate-900/60 text-indigo-500 '
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)


class TransactionForm(forms.ModelForm):
    """Transaction create/update form, scoped to the requesting user (FR07, R3).

    `category` and `payment_method` choices are restricted to the user's own
    records so a transaction can never reference another user's data.
    """

    class Meta:
        model = Transaction
        fields = (
            'title',
            'amount',
            'transaction_type',
            'category',
            'payment_method',
            'installments',
            'transaction_date',
            'is_fixed',
            'fixed_until',
            'notes',
        )
        widgets = {
            'transaction_date': forms.DateInput(attrs={'type': 'date'}),
            'fixed_until': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'installments': forms.NumberInput(
                attrs={'step': '1', 'min': '1', 'max': str(Transaction.MAX_INSTALLMENTS)},
            ),
        }
        labels = {
            'is_fixed': 'Fixed / recurring transaction',
            'installments': 'Installments',
            'fixed_until': 'Repeat until',
        }
        help_texts = {
            'transaction_date': (
                'The date of the purchase. On a credit card with a billing '
                'cycle, the dashboard still subtracts the money on the month '
                'the bill is paid, which may be a later month than this one.'
            ),
            'is_fixed': (
                'Toggle on for recurring transactions (e.g. subscriptions, rent); '
                'leave off for one-off, variable ones.'
            ),
            'installments': (
                'Credit card only: how many times the amount above is split '
                f'(1 to {Transaction.MAX_INSTALLMENTS}). Enter the full total in '
                'Amount — keep this at 1 for every other payment method.'
            ),
            'fixed_until': (
                'Fixed transactions only. Leave empty to repeat indefinitely. '
                'Set it to the last month this amount applies — when your salary '
                'or rent changes, end this one and add a new transaction starting '
                'the month after, so past months keep the old value.'
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(user=user)
        self.fields['payment_method'].queryset = PaymentMethod.objects.filter(user=user)
        # Optional in the form (the model column is NOT NULL with default 1):
        # leaving it blank means "single payment", not a validation error.
        self.fields['installments'].required = False
        for name, field in self.fields.items():
            if name == 'is_fixed':
                field.widget.attrs['class'] = CHECKBOX_CLASSES
            else:
                field.widget.attrs['class'] = INPUT_CLASSES

    def clean_installments(self):
        """Treat a *blank* installments box as a single payment.

        Only `None` (nothing submitted) is defaulted — an explicit `0` must
        fall through untouched so the model's `MinValueValidator(1)` rejects
        it in `_post_clean` instead of being silently rewritten to 1.
        """
        installments = self.cleaned_data.get('installments')
        return 1 if installments is None else installments

    def clean(self):
        """Validate the cross-field rules on installments and `fixed_until`.

        1. An installment plan requires a credit card payment method. The
           field is always rendered (the project is deliberately zero-JS, so
           it cannot appear/disappear as `payment_method` changes) — the rule
           is therefore enforced here, where it actually matters.
        2. `is_fixed` and an installment plan are conflicting recurrences: one
           repeats forever, the other stops after N months. Allowing both
           would make `amount_for_month` ambiguous, so they are rejected
           together rather than resolved by a silent precedence rule.
        3. `fixed_until` is meaningless without `is_fixed`, and cannot fall
           before the month the transaction starts.
        """
        cleaned_data = super().clean()
        self._clean_fixed_until(cleaned_data)

        payment_method = cleaned_data.get('payment_method')
        installments = cleaned_data.get('installments')

        if payment_method is None or installments is None:
            return cleaned_data

        is_credit_card = payment_method.method_type == PaymentMethod.MethodType.CREDIT_CARD
        if installments > 1 and not is_credit_card:
            self.add_error(
                'installments',
                'Installments are only available for credit card payments. '
                f'Keep this at 1 for "{payment_method}".',
            )
        elif installments > 1 and cleaned_data.get('is_fixed'):
            self.add_error(
                'installments',
                'A transaction cannot be both fixed and split into installments: '
                'a fixed transaction repeats every month, while an installment '
                'plan ends after the last installment. Pick one.',
            )

        return cleaned_data

    def _clean_fixed_until(self, cleaned_data):
        """Enforce the `fixed_until` rules (see `clean`, rule 3).

        Compared by **month**, not by day: recurrence is monthly, so an end
        date on the 5th and one on the 28th of the same month mean the same
        thing. Rejecting `2026-03-01` for a transaction dated `2026-03-15`
        would be a distinction the projection does not actually make.
        """
        end_date = cleaned_data.get('fixed_until')
        if end_date is None:
            return

        if not cleaned_data.get('is_fixed'):
            self.add_error(
                'fixed_until',
                'Only fixed transactions can have an end date. Either toggle '
                '"Fixed / recurring transaction" on, or clear this field.',
            )
            return

        start_date = cleaned_data.get('transaction_date')
        if start_date is not None and (end_date.year, end_date.month) < (
            start_date.year,
            start_date.month,
        ):
            self.add_error(
                'fixed_until',
                'The end date cannot be before the month the transaction '
                f'starts ({start_date:%B %Y}).',
            )
