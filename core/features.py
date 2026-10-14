# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Review gates suspend interfaces without changing financial source records."""
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


REVIEW_ITEMS = (
    {'key': 'wealth', 'title': _('Net worth'),
     'description': _('A clearer view of recorded assets and debts, with understandable historical limits.')},
    {'key': 'imports', 'title': _('Import statements'),
     'description': _('A simpler statement review and reconciliation flow. Existing confirmed import history remains available.')},
)


def feature_available(key):
    return key in settings.REVIEWED_FEATURES


def roadmap_url(key):
    return reverse('pages:roadmap') + '#' + key


def review_gate(key, view):
    @login_required
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not feature_available(key):
            # An old tab or direct POST cannot operate a suspended feature.
            return redirect(roadmap_url(key))
        return view(request, *args, **kwargs)
    return guarded
