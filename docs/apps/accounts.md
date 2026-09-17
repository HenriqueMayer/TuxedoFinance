# Accounts

The app provides signup, login, logout, and presentation preferences through
Django's native authentication. It uses the standard `User` model and a separate
one-to-one `UserPreference`; it does not define a custom user model.

## Authentication

`SignupForm` extends `UserCreationForm`, requires an email, and applies shared
widget styling. `LoginForm` extends `AuthenticationForm` with presentation and
localized validation copy. Django remains responsible for password validation,
authentication, sessions, and redirect validation.

`LoginView` redirects authenticated visitors to the dashboard. A successful login
honors a validated `next` destination or the configured default. Invalid
credentials appear as form errors.

`SignupView` checks `ALLOW_SIGNUPS` before processing the request. When disabled,
it returns the localized closed-registration screen with HTTP 403; login remains
available. When enabled, signup creates a native user, initializes preferences,
and logs the user in. The categories signal creates only the nine approved
default categories in the active interface language. Financial records are not
seeded, and later language changes do not rename stored categories.

Logout uses Django's native `LogoutView` and accepts POST only. Navigation
therefore uses a CSRF-protected form rather than a GET link.

## Presentation preferences

`UserPreference` stores `base_currency` and `date_format` (`DMY` or `MDY`).
`SettingsView` obtains the authenticated user's preference through `for_user()`;
that helper creates a missing preference with defaults. `BaseCurrencyForm`
validates the supported choices. Changing either setting affects presentation,
not native financial records or the language cookie.

The initial preference migration also initializes existing users. New users
default to BRL and `DD/MM/YYYY`. Currency and date format are independent of the
English or Portuguese interface language.

## Routes and templates

| Path | Route name | View / template |
|---|---|---|
| `/accounts/login/` | `accounts:login` | `LoginView`, `accounts/login.html` |
| `/accounts/signup/` | `accounts:signup` | `SignupView`, `accounts/signup.html` |
| `/accounts/settings/` | `accounts:settings` | `SettingsView`, `accounts/settings.html` |
| `/accounts/logout/` | `accounts:logout` | Native `LogoutView`; redirects to the landing page |

Templates use the shared field partial, error messages, and the normal
server-rendered form path. The login template retains `next` after a validation
failure. Public signup links reflect the server's registration policy.
