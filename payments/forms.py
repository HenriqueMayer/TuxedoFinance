from django import forms

from payments.models import PaymentMethod

# PRD §9.4 — the exact input classes shared by every form in the project.
# `partials/form_field.html` renders the label/help/errors but never injects
# classes into `{{ field }}`; the owning form is responsible for styling its
# own widgets, which is what the `__init__` override below does.
INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-[#313335] px-3.5 py-2.5 '
    'text-slate-900 dark:text-neutral-100 placeholder:text-slate-400 dark:placeholder:text-neutral-500 '
    'focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)


class PaymentMethodForm(forms.ModelForm):
    """PaymentMethod create/update form (PRD FR11).

    No FK scoping is needed here (unlike `CategoryForm`'s `parent_category`)
    since `PaymentMethod` has no self-relationship — per-user isolation is
    already handled by the owning views (`get_queryset` + `form_valid`).

    The owning `user` is still required, so the form can enforce the model's
    `unique_payment_method_per_user` constraint itself. Django will not do it:
    `user` is not one of `Meta.fields`, and `Model.validate_unique()` skips any
    constraint that touches an excluded field. The duplicate therefore passed
    validation and only failed at INSERT, as an uncaught `IntegrityError` — a
    500 on submit. `PaymentMethod` is no longer seeded (PRD FR14), so a user's
    first methods are whatever they name them; a duplicate-name check still
    matters the moment they add a second card or a second PIX-named method.
    """

    class Meta:
        model = PaymentMethod
        fields = ('name', 'method_type', 'best_purchase_day', 'due_day')
        widgets = {
            'best_purchase_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
            'due_day': forms.NumberInput(attrs={'min': '1', 'max': '31'}),
        }
        labels = {
            'best_purchase_day': 'Best purchase day',
            'due_day': 'Due day',
        }
        help_texts = {
            'best_purchase_day': (
                'Credit cards only. The day the new statement opens — buying on '
                'this day or later moves the charge to the next month. This is '
                'the field that decides which month the dashboard subtracts a '
                'purchase from. Leave it empty to have purchases hit the month '
                'they were made.'
            ),
            'due_day': (
                'Credit cards only, optional. The day of the month the bill is '
                'paid, shown as a reminder — it never changes which month a '
                'purchase is subtracted from.'
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES

    def clean_name(self):
        """Reject a name this user already used, as a field error rather than a 500."""
        name = self.cleaned_data['name']
        # Matched exactly, like the database constraint it stands in for —
        # `iexact` here would reject names SQLite would happily have stored.
        duplicates = PaymentMethod.objects.filter(user=self.user, name=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError('You already have a payment method with this name.')
        return name

    def clean(self):
        """Restrict the billing cycle to credit cards.

        The two days are independent on purpose: `best_purchase_day` alone is
        enough to decide which month a purchase is paid in, and `due_day` is a
        reminder that moves no money, so either can be filled in without the
        other.

        The fields are always rendered — the project is deliberately zero-JS,
        so they cannot appear and disappear as `method_type` changes — which is
        why the credit-card rule is enforced here rather than in the widget.
        """
        cleaned_data = super().clean()
        method_type = cleaned_data.get('method_type')

        # Only reachable once `method_type` itself is valid; otherwise the user
        # already has an error on that field and a second one adds nothing.
        if method_type and method_type != PaymentMethod.MethodType.CREDIT_CARD:
            for field in ('best_purchase_day', 'due_day'):
                if cleaned_data.get(field) is not None:
                    self.add_error(
                        field,
                        'Only credit cards have a billing cycle — every other '
                        'payment method takes the money on the purchase date. '
                        'Clear this field.',
                    )

        return cleaned_data
