"""Protect initial holdings for every ORM deletion, including bulk/admin paths."""

from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _

from investments.models import Asset


@receiver(pre_delete, sender=Asset)
def protect_opening_position(sender, instance, using, **kwargs):
    # The collector runs all pre_delete receivers inside its atomic transaction.
    # Read the persisted row so a stale instance cannot erase a newer position.
    current = sender.objects.using(using).select_for_update().get(pk=instance.pk)
    if current.has_opening_position:
        raise ProtectedError(
            _('This asset has an opening position and cannot be deleted.'),
            [current],
        )
