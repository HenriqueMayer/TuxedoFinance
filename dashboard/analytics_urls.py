# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.urls import path

from dashboard.analytics import AnalyticsFinanceView, AnalyticsInvestmentsView

app_name = 'analytics'

urlpatterns = [
    path('', AnalyticsFinanceView.as_view(), name='index'),
    path('investments/', AnalyticsInvestmentsView.as_view(), name='investments'),
]
