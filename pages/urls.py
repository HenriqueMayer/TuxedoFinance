from django.urls import path

from pages.views import LandingView

app_name = 'pages'

urlpatterns = [
    path('', LandingView.as_view(), name='landing'),
]
