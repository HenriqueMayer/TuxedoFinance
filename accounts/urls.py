from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts.views import LoginView, SettingsView, SignupView

app_name = 'accounts'

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('settings/', SettingsView.as_view(), name='settings'),
    # Native LogoutView is POST-only by default and redirects to
    # `LOGOUT_REDIRECT_URL` ('pages:landing') — no customization needed;
    # the navbar already posts to this route via a <form> (never a link).
    path('logout/', LogoutView.as_view(), name='logout'),
]
