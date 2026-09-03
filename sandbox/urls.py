from django.urls import path

from sandbox.views import SalarySandboxView


app_name = 'sandbox'

urlpatterns = [
    path('', SalarySandboxView.as_view(), name='index'),
]
