from django import forms

from investments.models import Investment

# PRD §9.4 — the exact input classes shared by every form in the project.
# `partials/form_field.html` renders the label/help/errors but never injects
# classes into `{{ field }}`; the owning form is responsible for styling its
# own widgets, which is what the `__init__` override below does.
INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-[#313335] px-3.5 py-2.5 '
    'text-slate-900 dark:text-neutral-100 placeholder:text-slate-400 dark:placeholder:text-neutral-500 '
    'focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)


class InvestmentForm(forms.ModelForm):
    """Create/update form for an `Investment` row.

    Per-user isolation is handled by the owning views (`get_queryset` +
    `form_valid`); the form has no queryset to filter. The widgets borrow
    the project's canonical `INPUT_CLASSES` so every field renders the same
    way as on the transactions / categories / payments forms.
    """

    class Meta:
        model = Investment
        fields = ('title', 'amount', 'kind', 'date', 'reason', 'notes')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'kind': 'Type',
        }
        help_texts = {
            'amount': (
                'Always positive. Pick "Deposit" or "Withdrawal" in Type to '
                'decide whether this row adds to or subtracts from the '
                'running investment balance.'
            ),
            'kind': (
                'A deposit moves money into the investment portfolio; a '
                'withdrawal moves it back out. The running balance is the '
                'sum of all deposits minus the sum of all withdrawals.'
            ),
            'reason': (
                'Optional. Useful for withdrawals in particular — record '
                'why the money left the portfolio so future reads of the '
                'log do not depend on your memory.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
