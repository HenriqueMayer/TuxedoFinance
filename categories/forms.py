from django import forms
from django.utils.translation import gettext_lazy as _

from categories.models import Category

# PRD §9.4 — the exact input classes shared by every form in the project.
# `partials/form_field.html` renders the label/help/errors but never injects
# classes into `{{ field }}`; the owning form is responsible for styling its
# own widgets, which is what the `__init__` override below does.
INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-none focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)


class CategoryForm(forms.ModelForm):
    """Category create/update form, scoped to the requesting user (PRD FR12).

    `parent_category` choices are restricted to the user's own categories
    and, when editing, exclude the instance itself so a category can never
    become its own parent.

    `user` also lets the form enforce the model's `unique_category_per_user`
    constraint. Django will not do it: `user` is not one of `Meta.fields`, and
    `Model.validate_unique()` skips any constraint that touches an excluded
    field, so a duplicate name passed validation and only failed at INSERT, as
    an uncaught `IntegrityError` — a 500 on submit.
    """

    class Meta:
        model = Category
        fields = ('name', 'transaction_type', 'parent_category')
        labels = {
            'name': _('Name'),
            'transaction_type': _('Category type'),
            'parent_category': _('Parent category'),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        queryset = Category.objects.filter(user=user)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields['parent_category'].queryset = queryset
        self.fields['parent_category'].required = False
        self.fields['parent_category'].empty_label = _('No parent category')
        self.fields['transaction_type'].required = False
        self.fields['transaction_type'].choices = [
            ('', _('Unclassified (income and expense)')),
            *Category.TransactionType.choices,
        ]
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES

    def clean_name(self):
        """Reject a name this user already used, as a field error rather than a 500."""
        name = self.cleaned_data['name']
        # Matched exactly, like the database constraint it stands in for —
        # `iexact` here would reject names SQLite would happily have stored.
        duplicates = Category.objects.filter(user=self.user, name=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError(_('You already have a category with this name.'))
        return name


class CategoryImportForm(forms.Form):
    file = forms.FileField(
        label=_('CSV file'),
        help_text=_('Use a CSV file with the columns name, transaction_type and parent_category.'),
        widget=forms.ClearableFileInput(attrs={
            'accept': '.csv,text/csv',
            'class': INPUT_CLASSES,
        }),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        if not uploaded_file.name.lower().endswith('.csv'):
            raise forms.ValidationError(_('Select a CSV file.'))
        return uploaded_file
