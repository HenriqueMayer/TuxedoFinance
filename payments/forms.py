from django import forms

from payments.models import PaymentMethod

# PRD §9.4 — the exact input classes shared by every form in the project.
# `partials/form_field.html` renders the label/help/errors but never injects
# classes into `{{ field }}`; the owning form is responsible for styling its
# own widgets, which is what the `__init__` override below does.
INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 '
    'text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 '
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
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
    500 on submit. Every account is seeded with "Credit Card", "Debit Card",
    "Checking Account" and "PIX" (`payments/signals.py`), so reusing one of
    those names is among the first things a new user is likely to try.
    """

    class Meta:
        model = PaymentMethod
        fields = ('name', 'method_type')

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
