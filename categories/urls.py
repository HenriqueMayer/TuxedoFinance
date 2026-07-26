from django.urls import path

from categories.views import (
    CategoryCreateView,
    CategoryDeleteView,
    CategoryListView,
    CategoryUpdateView,
)

app_name = 'categories'

urlpatterns = [
    path('', CategoryListView.as_view(), name='list'),
    path('create/', CategoryCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', CategoryUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', CategoryDeleteView.as_view(), name='delete'),
]
