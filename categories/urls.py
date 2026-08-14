from django.urls import path

from categories.views import (
    CategoryCreateView,
    CategoryDeleteView,
    CategoryListView,
    CategoryUpdateView,
    export_categories,
    import_categories,
)

app_name = 'categories'

urlpatterns = [
    path('', CategoryListView.as_view(), name='list'),
    path('create/', CategoryCreateView.as_view(), name='create'),
    path('export/', export_categories, name='export'),
    path('import/', import_categories, name='import'),
    path('<int:pk>/edit/', CategoryUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', CategoryDeleteView.as_view(), name='delete'),
]
