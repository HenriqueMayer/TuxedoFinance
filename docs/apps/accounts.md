# `accounts`

Sign up, log in, log out — entirely built on Django's native `django.contrib.auth`. No custom `User` model. Public signup is controlled by the `ALLOW_SIGNUPS` environment setting (enabled by default).

## Files

| File | Contents |
|---|---|
| `accounts/forms.py` | `SignupForm`, `LoginForm` — thin, styled subclasses of Django's native forms |
| `accounts/views.py` | `LoginView`, `SignupView` |
| `accounts/urls.py` | `app_name = 'accounts'`; routes `login`, `signup`, `logout` |
| `accounts/models.py` | empty — `User` is Django's own, not redefined here |
| `accounts/admin.py` | empty — `User` is already registered by `django.contrib.auth`'s own admin config |

## Forms

### `SignupForm(UserCreationForm)`

```python
class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')
```

Adds `email` as a required field on top of Django's native `UserCreationForm` (which normally only asks for `username` + two password fields). `__init__` forces `email` to `required = True` and applies the shared input styling to every field's widget — `partials/form_field.html` renders labels/errors/help text but never injects classes itself, so every form is responsible for styling its own widgets.

### `LoginForm(AuthenticationForm)`

A pure styling subclass — no field/validation changes over Django's native `AuthenticationForm`. Invalid credentials surface through the form's own `error_messages['invalid_login']`, rendered by the template as a non-field error (never a raw 500 or an unhandled exception).

## Views

### `LoginView(SuccessMessageMixin, AuthLoginView)`

```python
class LoginView(SuccessMessageMixin, AuthLoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True
    success_message = 'Welcome back, %(username)s.'
```

- `redirect_authenticated_user=True` — an already-logged-in visitor who navigates to `/accounts/login/` is sent straight to `LOGIN_REDIRECT_URL` instead of seeing the form again.
- On success, redirects to `?next=` if present, otherwise `settings.LOGIN_REDIRECT_URL` (`dashboard:index`) — this is Django's built-in `LoginView` behavior, unmodified.
- `SuccessMessageMixin` reads `username` from the bound `AuthenticationForm`'s `cleaned_data` to fill in `success_message`.

### `SignupView(SuccessMessageMixin, CreateView)`

```python
class SignupView(SuccessMessageMixin, CreateView):
    form_class = SignupForm
    template_name = 'accounts/signup.html'
    success_url = reverse_lazy('dashboard:index')
    success_message = 'Welcome to CashFlow, %(username)s. Your account is ready.'

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response
```

Creates a standard `django.contrib.auth.models.User`. `form_valid` explicitly calls Django's `login()` after `super().form_valid(form)` saves the user, so signup redirects directly to the dashboard. Signup seeds only the approved default categories and creates the user's `UserPreference` with BRL as the bootstrap reporting currency. No synthetic financial records or shared credentials are provided. Banks, accounts and cards are never fabricated; the first-run Banking flow asks the user to create their real structure.

When `ALLOW_SIGNUPS=False`, the view does not validate or save a user. It returns
the localized registration-closed response instead. This server-side guard is
the source of truth; hiding links in the landing page and navbar is only a
matching navigation affordance. Existing users can still log in normally.

## User preferences

`UserPreference` is a one-to-one, user-owned model containing `base_currency`.
The authenticated `/accounts/settings/` screen uses `BaseCurrencyForm` to
validate supported codes and save the preference. Existing users are covered
by the `accounts.0001_userpreference` migration. Changing the value changes
consolidated display only; native financial amounts and currencies remain
unchanged. The settings route and form are localized in English and pt-BR.

## Routes

| Path | Name | View | Notes |
|---|---|---|---|
| `/accounts/login/` | `accounts:login` | `LoginView` | |
| `/accounts/signup/` | `accounts:signup` | `SignupView` | Creates an account only when `ALLOW_SIGNUPS=True`; otherwise returns a localized closed-registration response |
| `/accounts/logout/` | `accounts:logout` | Django's native `LogoutView` | **POST-only** |

`LogoutView` is used directly from `django.contrib.auth.views` with zero customization — modern Django's `LogoutView` rejects `GET` requests (returns `405`), so every logout control in the UI is a `<form method="post">` with a submit button, never a plain `<a href>` link (see `partials/navbar_app.html`).

## Templates

- `templates/accounts/login.html` — renders `LoginForm` via `partials/form_field.html`; preserves `?next=` as a hidden input so post-login redirect targets survive a failed first attempt; links to signup.
- `templates/accounts/signup.html` — renders `SignupForm`'s four fields (`username`, `email`, `password1`, `password2`); links to login when registration is open. The public landing page and nav omit signup calls to action when it is closed.

Both follow the identical "centered `max-w-md` card" layout used by every auth-adjacent screen in the project.
