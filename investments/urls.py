from django.urls import path

from investments.views import (
    InvestmentCreateView,
    InvestmentDeleteView,
    InvestmentListView,
    InvestmentUpdateView,
)

app_name = 'investments'

urlpatterns = [
    path('', InvestmentListView.as_view(), name='list'),
    path('create/', InvestmentCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', InvestmentUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', InvestmentDeleteView.as_view(), name='delete'),
]
