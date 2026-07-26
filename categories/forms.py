from django import forms

from categories.models import Category

# PRD §9.4 — the exact input classes shared by every form in the project.
# `partials/form_field.html` renders the label/help/errors but never injects
# classes into `{{ field }}`; the owning form is responsible for styling its
# own widgets, which is what the `__init__` override below does.
INPUT_CLASSES = (
    'w-full rounded-xl border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 '
    'text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 '
    'focus:outline-none focus:ring-2 focus:ring-indigo-500/40'
)


class CategoryForm(forms.ModelForm):
    """Category create/update form, scoped to the requesting user (PRD FR12).

    `parent_category` choices are restricted to the user's own categories
    and, when editing, exclude the instance itself so a category can never
    become its own parent.
    """

    class Meta:
        model = Category
        fields = ('name', 'parent_category')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Category.objects.filter(user=user)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields['parent_category'].queryset = queryset
        self.fields['parent_category'].required = False
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
