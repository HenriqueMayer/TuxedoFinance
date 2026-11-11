"""Owner-scoped lookups for the API routers."""

from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils.translation import gettext as _


def owned(model, user, pk, *, select_related=()):
    """Return the record of ``model`` with ``pk`` that belongs to ``user``, or 404.

    Another owner's record gives the same answer as a missing one, so the API
    does not reveal that it exists.
    """
    queryset = model.objects.filter(user=user)
    if select_related:
        queryset = queryset.select_related(*select_related)
    record = queryset.filter(pk=pk).first()
    if record is None:
        raise Http404
    return record


def owned_choice(model, user, pk, field, *, select_related=()):
    """Return the owned record that a request names in ``field``, or a field error.

    Use this for a reference inside a request body: an unknown or foreign
    identifier is a validation error on that field, not a missing page.
    """
    queryset = model.objects.filter(user=user)
    if select_related:
        queryset = queryset.select_related(*select_related)
    record = queryset.filter(pk=pk).first()
    if record is None:
        raise ValidationError({field: _("Choose one of your own records.")})
    return record
