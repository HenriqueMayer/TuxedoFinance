from django.urls import path

from investments.views import (
    AssetCreateView,
    AssetDeleteView,
    AssetUpdateView,
    ExchangeRateCreateView,
    ExchangeRateDeleteView,
    ExchangeRateListView,
    InstitutionCreateView,
    InstitutionDeleteView,
    InstitutionUpdateView,
    InvestmentCreateView,
    InvestmentDeleteView,
    InvestmentListView,
    InvestmentProductCreateView,
    InvestmentProductDeleteView,
    InvestmentProductUpdateView,
    InvestmentSettingsView,
    InvestmentUpdateView,
)

app_name = 'investments'

urlpatterns = [
    path('', InvestmentListView.as_view(), name='list'),
    path('create/', InvestmentCreateView.as_view(), name='create'),
    path('settings/', InvestmentSettingsView.as_view(), name='settings'),
    path('institutions/create/', InstitutionCreateView.as_view(), name='create_institution'),
    path(
        'institutions/<int:pk>/edit/',
        InstitutionUpdateView.as_view(),
        name='update_institution',
    ),
    path(
        'institutions/<int:pk>/delete/',
        InstitutionDeleteView.as_view(),
        name='delete_institution',
    ),
    path('products/create/', InvestmentProductCreateView.as_view(), name='create_product'),
    path(
        'products/<int:pk>/edit/',
        InvestmentProductUpdateView.as_view(),
        name='update_product',
    ),
    path(
        'products/<int:pk>/delete/',
        InvestmentProductDeleteView.as_view(),
        name='delete_product',
    ),
    path('assets/create/', AssetCreateView.as_view(), name='create_asset'),
    path(
        'assets/<int:pk>/edit/',
        AssetUpdateView.as_view(),
        name='update_asset',
    ),
    path(
        'assets/<int:pk>/delete/',
        AssetDeleteView.as_view(),
        name='delete_asset',
    ),
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
