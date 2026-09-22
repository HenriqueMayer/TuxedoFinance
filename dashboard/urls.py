from django.urls import path

from dashboard.details import chart_details
from dashboard.views import DashboardIndexView, DashboardReportsView

app_name = 'dashboard'

urlpatterns = [
    path('chart-details/', chart_details, name='chart_details'),
    path('', DashboardIndexView.as_view(), name='index'),
    path('reports/', DashboardReportsView.as_view(), name='reports'),
]
