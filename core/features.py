# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Review gates suspend interfaces without changing financial source records."""
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse


def feature_available(key):
    return key in settings.REVIEWED_FEATURES


def review_destination(key):
    # Hidden planned features must not become dead tabs or a second navigation.
    return reverse('transactions:list' if key == 'imports' else 'dashboard:index')


def review_gate(key, view):
    @login_required
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not feature_available(key):
            # An old tab or direct POST cannot operate a suspended feature.
            return redirect(review_destination(key))
        return view(request, *args, **kwargs)
    return guarded
