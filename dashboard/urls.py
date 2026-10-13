from django.urls import path

from dashboard.details import chart_details
from dashboard.views import DashboardIndexView, DashboardReportsView
from dashboard.wealth import wealth_view

app_name = 'dashboard'

urlpatterns = [
    path('wealth/', wealth_view, name='wealth'),
    path('chart-details/', chart_details, name='chart_details'),
    path('', DashboardIndexView.as_view(), name='index'),
    path('reports/', DashboardReportsView.as_view(), name='reports'),
]
