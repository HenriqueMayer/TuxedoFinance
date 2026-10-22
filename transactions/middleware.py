# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Recover deliberately refused projections without presenting stale balances."""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from transactions.projection import ProjectionLimitExceeded


class LedgerProjectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, ProjectionLimitExceeded):
            return None
        # The exception leaves any owning atomic workflow before reaching here.
        # The ordinary transaction list does not synchronize, so it remains an
        # authorized recovery path for editing existing excessive schedules.
        messages.error(request, _(
            'Ledger synchronization was stopped. No changes were saved. '
            'Review recurring transaction dates in Transactions before trying again.'
        ))
        target = reverse('transactions:list')
        # XHR follows a 302 before HTMX can read its headers. Return the
        # deliberate full-navigation instruction directly for island requests.
        enhanced = request.headers.get('HX-Request') == 'true' or request.headers.get('X-Tuxedo-Assets')
        response = HttpResponse() if enhanced else redirect(target)
        response['HX-Redirect'] = target
        return response
