# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Analytical page composition reuses the domain-owned reporting calculations."""
from urllib.parse import quote, urlsplit

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_safe

from dashboard.views import DashboardReportsView
from investments.views.portfolio import InvestmentChartsView


class AnalyticsFinanceView(DashboardReportsView):
    template_name = 'analytics/finance.html'


class AnalyticsInvestmentsView(InvestmentChartsView):
    template_name = 'analytics/investments.html'


@login_required
@require_safe
def legacy_analytics(request, *, destination):
    """A legacy boosted fragment must navigate, never nest another workspace."""
    target = reverse(destination)
    query = request.META.get('QUERY_STRING', '')
    if query:
        target += '?' + query
    if request.headers.get('HX-Request') == 'true':
        # HTMX supplies the current document fragment, which HTTP request paths
        # omit. Keep it only when it belongs to this legacy chart document.
        try:
            current = urlsplit(request.headers.get('HX-Current-URL', ''))
        except ValueError:
            current = None
        if current and current.path == request.path and current.fragment:
            target += '#' + quote(current.fragment, safe='%-._~')
        response = HttpResponse(status=200)
        response['HX-Redirect'] = target
        return response
    # Fragment identifiers remain browser-owned: a redirect with no fragment
    # retains the requested chart anchor in an ordinary browser navigation.
    return HttpResponseRedirect(target)
