from django.urls import path

from sandbox.views import SalarySandboxView


app_name = 'sandbox'

urlpatterns = [
    path('clt-pj/', SalarySandboxView.as_view(), name='clt_pj'),
]
