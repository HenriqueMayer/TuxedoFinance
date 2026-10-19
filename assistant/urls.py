# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.urls import path
from assistant import views

app_name = 'assistant'
urlpatterns = [
    path('', views.index, name='index'),
    path('context/', views.context_snapshot, name='context'),
    path('conversations/new/', views.create, name='create'),
    path('<uuid:pk>/', views.detail, name='detail'),
    path('<uuid:pk>/delete/', views.delete, name='delete'),
    path('<uuid:pk>/messages/', views.send, name='send'),
]
