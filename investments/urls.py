from django.urls import path

from investments import views


app_name = 'investments'

urlpatterns = [
    path('', views.InvestmentListView.as_view(), name='list'),
    path('add/', views.guided_investment, name='guided_create'),
    path('positions/<int:product_pk>/<int:asset_pk>/', views.position_detail, name='position_detail'),
    path('positions/<int:product_pk>/<int:asset_pk>/update/', views.position_update, name='position_update'),
    path('charts/', views.InvestmentChartsView.as_view(), name='charts'),
    path('operations/', views.InvestmentOperationsView.as_view(), name='operations'),
    path('prices/', views.PriceObservationListView.as_view(), name='prices'),
    path('prices/create/', views.PriceObservationCreateView.as_view(), name='create_price'),
    path('prices/<int:pk>/edit/', views.PriceObservationUpdateView.as_view(), name='update_price'),
    path('prices/<int:pk>/delete/', views.PriceObservationDeleteView.as_view(), name='delete_price'),
    path('create/', views.InvestmentCreateView.as_view(), name='create'),
    path('yield-preview/', views.yield_preview, name='yield_preview'),
    path('settings/', views.InvestmentSettingsView.as_view(), name='settings'),
    path('products/create/', views.InvestmentProductCreateView.as_view(), name='create_product'),
    path('products/<int:pk>/edit/', views.InvestmentProductUpdateView.as_view(), name='update_product'),
    path('products/<int:pk>/delete/', views.InvestmentProductDeleteView.as_view(), name='delete_product'),
    path('assets/create/', views.AssetCreateView.as_view(), name='create_asset'),
    path('assets/<int:pk>/edit/', views.AssetUpdateView.as_view(), name='update_asset'),
    path('assets/<int:pk>/delete/', views.AssetDeleteView.as_view(), name='delete_asset'),
    path('assets/<int:pk>/archive/', views.archive_asset, name='archive_asset'),
    path('assets/<int:pk>/restore/', views.restore_asset, name='restore_asset'),
    path('<int:pk>/edit/', views.InvestmentUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.InvestmentDeleteView.as_view(), name='delete'),
]
