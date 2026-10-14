# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.urls import path
from planning import views

app_name = 'planning'
urlpatterns = [
    path('', views.index, name='index'),
    path('budgets/', views.budgets, name='budgets'),
    path('budgets/create/', views.budget_form, name='budget_create'),
    path('budgets/<int:pk>/edit/', views.budget_form, name='budget_update'),
    path('budgets/<int:pk>/delete/', views.budget_delete, name='budget_delete'),
    path('budgets/copy/', views.budget_copy, name='budget_copy'),
    path('goals/', views.goals, name='goals'),
    path('goals/create/', views.goal_form, name='goal_create'),
    path('goals/<int:pk>/', views.goal_detail, name='goal_detail'),
    path('goals/<int:pk>/edit/', views.goal_form, name='goal_update'),
    path('goals/<int:pk>/archive/', views.goal_archive, name='goal_archive'),
    path('goals/<int:goal_pk>/reserve/', views.allocation_form, name='allocation_create'),
    path('goals/<int:goal_pk>/reserves/<int:pk>/edit/', views.allocation_form, name='allocation_update'),
    path('reserves/<int:pk>/delete/', views.allocation_delete, name='allocation_delete'),
    path('signals/', views.signals, name='signals'),
    path('signals/settings/', views.signals_settings, name='signals_settings'),
    path('signals/review/', views.signal_decision, name='signal_decision'),
]
