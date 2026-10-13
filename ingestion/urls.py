from django.urls import path
from ingestion import views

app_name = 'ingestion'
urlpatterns = [
    path('', views.index, name='index'),
    path('<int:pk>/mapping/', views.mapping, name='mapping'),
    path('<int:pk>/review/', views.review, name='review'),
    path('<int:pk>/confirm/', views.confirmation, name='confirmation'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/undo/', views.undo, name='undo'),
]
