"""Explicitly saved, private planning inputs; never financial ledger records."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ScenarioDraft(models.Model):
    class Kind(models.TextChoices):
        BUDGET = 'budget', _('Monthly plan')
        YIELD = 'yield', _('Yield simulation')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scenario_drafts')
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-pk']

    def __str__(self):
        return self.name
