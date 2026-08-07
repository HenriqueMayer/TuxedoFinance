from django.urls import path

from investments.views import (
    AssetCreateView,
    ExchangeRateCreateView,
    ExchangeRateDeleteView,
    ExchangeRateListView,
    InstitutionCreateView,
    InvestmentCreateView,
    InvestmentDeleteView,
    InvestmentListView,
    InvestmentProductCreateView,
    InvestmentUpdateView,
)

app_name = 'investments'

urlpatterns = [
    path('', InvestmentListView.as_view(), name='list'),
    path('create/', InvestmentCreateView.as_view(), name='create'),
    path('institutions/create/', InstitutionCreateView.as_view(), name='create_institution'),
    path('products/create/', InvestmentProductCreateView.as_view(), name='create_product'),
    path('assets/create/', AssetCreateView.as_view(), name='create_asset'),
    path('<int:pk>/edit/', InvestmentUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', InvestmentDeleteView.as_view(), name='delete'),
    path(
        'settings/exchange-rates/',
        ExchangeRateListView.as_view(),
        name='exchange_rates',
    ),
    path(
        'settings/exchange-rates/create/',
        ExchangeRateCreateView.as_view(),
        name='create_exchange_rate',
    ),
    path(
        'settings/exchange-rates/<int:pk>/delete/',
        ExchangeRateDeleteView.as_view(),
        name='delete_exchange_rate',
    ),
]
