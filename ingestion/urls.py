from django.urls import path
from ingestion import views
from core.features import review_gate

app_name = 'ingestion'
urlpatterns = [
    path('', review_gate('imports', views.index), name='index'),
    path('history/', views.history, name='history'),
    path('<int:pk>/mapping/', review_gate('imports', views.mapping), name='mapping'),
    path('<int:pk>/review/', review_gate('imports', views.review), name='review'),
    path('<int:pk>/confirm/', review_gate('imports', views.confirmation), name='confirmation'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/undo/', review_gate('imports', views.undo), name='undo'),
]
