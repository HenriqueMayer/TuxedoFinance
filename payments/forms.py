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
    """

    class Meta:
        model = PaymentMethod
        fields = ('name', 'method_type')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
