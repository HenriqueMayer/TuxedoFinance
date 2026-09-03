from django.urls import path

from investments import views


app_name = 'investments'

urlpatterns = [
    path('', views.InvestmentListView.as_view(), name='list'),
    path('create/', views.InvestmentCreateView.as_view(), name='create'),
    path('yield-preview/', views.yield_preview, name='yield_preview'),
    path('settings/', views.InvestmentSettingsView.as_view(), name='settings'),
    path('products/create/', views.InvestmentProductCreateView.as_view(), name='create_product'),
    path('products/<int:pk>/edit/', views.InvestmentProductUpdateView.as_view(), name='update_product'),
    path('products/<int:pk>/delete/', views.InvestmentProductDeleteView.as_view(), name='delete_product'),
    path('assets/create/', views.AssetCreateView.as_view(), name='create_asset'),
    path('assets/<int:pk>/edit/', views.AssetUpdateView.as_view(), name='update_asset'),
    path('assets/<int:pk>/delete/', views.AssetDeleteView.as_view(), name='delete_asset'),
    path('<int:pk>/edit/', views.InvestmentUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.InvestmentDeleteView.as_view(), name='delete'),
]
