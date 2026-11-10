from django.conf import settings
from django.db import models

from config.currencies import CURRENCIES, DEFAULT_CURRENCY

CURRENCY_CHOICES = [(code, currency.name) for code, currency in CURRENCIES.items()]
DATE_FORMAT_CHOICES = [("DMY", "DD/MM/YYYY"), ("MDY", "MM/DD/YYYY")]

# The blocks that Home can show. The owner chooses which ones and their order.
HOME_BLOCKS = ("left", "spending", "due", "worth")


def default_home_blocks():
    return list(HOME_BLOCKS)


class UserPreference(models.Model):
    """Presentation preferences of one user.

    They change how totals and dates are shown. They never change the currency
    or the date of a financial record.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferences"
    )
    base_currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY
    )
    date_format = models.CharField(max_length=3, choices=DATE_FORMAT_CHOICES, default="DMY")
    #: The shown blocks of Home, in order. A block that is not listed is hidden.
    home_blocks = models.JSONField(default=default_home_blocks)

    def __str__(self):
        return f"{self.user.username} ({self.base_currency})"

    @classmethod
    def for_user(cls, user):
        preference, _ = cls.objects.get_or_create(user=user)
        return preference
