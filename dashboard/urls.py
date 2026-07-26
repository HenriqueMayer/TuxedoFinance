from django.urls import path

from dashboard.views import DashboardIndexView, DashboardReportsView

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardIndexView.as_view(), name='index'),
    path('reports/', DashboardReportsView.as_view(), name='reports'),
]
