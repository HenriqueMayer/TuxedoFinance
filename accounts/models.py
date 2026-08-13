from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.currencies import CURRENCIES, DEFAULT_CURRENCY


CURRENCY_NAMES = {
    'BRL': _('Brazilian Real'), 'USD': _('US Dollar'), 'EUR': _('Euro'),
    'GBP': _('British Pound'), 'JPY': _('Japanese Yen'), 'CHF': _('Swiss Franc'),
}
CURRENCY_CHOICES = [(code, CURRENCY_NAMES[code]) for code in CURRENCIES]


class UserPreference(models.Model):
    """Private presentation preferences owned by exactly one user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='preferences',
    )
    base_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY,
    )

    def __str__(self):
        return f'{self.user.username} ({self.base_currency})'

    @classmethod
    def for_user(cls, user):
        preference, _ = cls.objects.get_or_create(user=user)
        return preference
