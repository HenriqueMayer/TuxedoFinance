from django.contrib.auth import login
from django.contrib.auth.views import LoginView as AuthLoginView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView

from accounts.forms import LoginForm, SignupForm


class LoginView(SuccessMessageMixin, AuthLoginView):
    """Native login view (PRD 3.2.1).

    `redirect_authenticated_user=True` sends an already-logged-in visitor
    straight to `LOGIN_REDIRECT_URL` instead of re-showing the form. Invalid
    credentials are handled by Django's own `AuthenticationForm` and shown
    as a non-field error in the template (PRD 3.3.2). `SuccessMessageMixin`
    reads `username` straight from the bound `AuthenticationForm`'s
    `cleaned_data` (PRD 8.1.3).
    """

    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True
    success_message = 'Welcome back, %(username)s.'


class SignupView(SuccessMessageMixin, CreateView):
    """Sign up view (PRD 3.1.2) built on Django's native auth.

    Uses `SignupForm` (a thin `UserCreationForm` subclass) to create a
    regular `django.contrib.auth.models.User`. On success the new user is
    auto-logged-in (PRD 3.1.4 — chosen over redirect-to-login for a
    seamless first-run experience) and sent straight to the dashboard.
    """

    form_class = SignupForm
    template_name = 'accounts/signup.html'
    success_url = reverse_lazy('dashboard:index')
    success_message = 'Welcome to CashFlow, %(username)s. Your account is ready.'

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response
