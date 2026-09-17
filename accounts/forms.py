from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from accounts.models import CURRENCY_CHOICES, DATE_FORMAT_CHOICES, UserPreference

# PRD §9.4 — the exact input classes shared by every form in the project.
# `partials/form_field.html` renders the label/help/errors but never injects
# classes into `{{ field }}`; the owning form is responsible for styling its
# own widgets, which is what the `__init__` overrides below do.
INPUT_CLASSES = (
    'w-full rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm text-forest '
    'placeholder:text-forest/40 focus:border-caramel focus:outline-none focus:ring-2 focus:ring-caramel/30 '
    'dark:border-cream/20 dark:bg-night dark:text-cream dark:placeholder:text-night-muted'
)


class SignupForm(UserCreationForm):
    """Native `UserCreationForm` (PRD 3.1.1) with an added `email` field.

    Keeps `django.contrib.auth.models.User` as-is (no custom user model,
    per house rules) and only styles the inherited widgets with the
    design-system input classes.
    """

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES


class LoginForm(AuthenticationForm):
    """Native `AuthenticationForm` (PRD 3.2.1), styled per the design system.

    Invalid credentials surface through the form's own
    `error_messages['invalid_login']`, rendered as a non-field error.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES


class BaseCurrencyForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = ('base_currency', 'date_format')
        labels = {'base_currency': _('Base currency'), 'date_format': _('Date format')}
        help_texts = {
            'base_currency': _(
                'Used only for consolidated totals and reports. Native account and event amounts stay unchanged.'
            )
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['base_currency'].choices = CURRENCY_CHOICES
        self.fields['date_format'].choices = DATE_FORMAT_CHOICES
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
