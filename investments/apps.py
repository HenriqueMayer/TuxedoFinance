from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InvestmentsConfig(AppConfig):
    name = 'investments'
    verbose_name = _('Investments')

    def ready(self):
        from investments import signals  # noqa: F401
