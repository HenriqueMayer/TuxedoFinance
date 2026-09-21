from django.urls import path
from sandbox import views

app_name = 'sandbox'
urlpatterns = [
    path('', views.index, name='index'),
    path('simulation/', views.simulation, name='simulation'),
    path('drafts/', views.drafts, name='drafts'),
    path('drafts/compare/', views.compare, name='compare'),
    path('drafts/<int:pk>/', views.draft_detail, name='draft_detail'),
    path('drafts/<int:pk>/duplicate/', views.draft_duplicate, name='draft_duplicate'),
    path('drafts/<int:pk>/delete/', views.draft_delete, name='draft_delete'),
]
