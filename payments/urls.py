from django.urls import path

from payments.views import (
    PaymentMethodCreateView,
    PaymentMethodDeleteView,
    PaymentMethodListView,
    PaymentMethodUpdateView,
)

app_name = 'payments'

urlpatterns = [
    path('', PaymentMethodListView.as_view(), name='list'),
    path('create/', PaymentMethodCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', PaymentMethodUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', PaymentMethodDeleteView.as_view(), name='delete'),
]
