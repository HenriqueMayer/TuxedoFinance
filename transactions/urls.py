from django.urls import path

from transactions.views import (
    TransactionCreateView,
    TransactionDeleteView,
    TransactionExportView,
    TransactionListView,
    TransactionUpdateView,
)

app_name = 'transactions'

urlpatterns = [
    path('', TransactionListView.as_view(), name='list'),
    path('export/', TransactionExportView.as_view(), name='export'),
    path('create/', TransactionCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', TransactionUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', TransactionDeleteView.as_view(), name='delete'),
]
