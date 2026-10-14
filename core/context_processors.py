from accounts.models import UserPreference
from core.currencies import get_currency, DEFAULT_CURRENCY
from django.conf import settings
from core.workspace_navigation import workspace_navigation
from core.features import feature_available


def currency(request):
    """Expose the authenticated user's reporting currency to templates."""
    code = DEFAULT_CURRENCY
    date_format = 'd/m/Y'
    if request.user.is_authenticated:
        preference = UserPreference.for_user(request.user)
        code = preference.base_currency
        date_format = 'm/d/Y' if preference.date_format == 'MDY' else 'd/m/Y'
    return {
        'CURRENCY_CODE': code,
        'CURRENCY_SYMBOL': get_currency(code).symbol,
        'ALLOW_SIGNUPS': settings.ALLOW_SIGNUPS,
        'USER_DATE_FORMAT': date_format,
        'IMPORTS_AVAILABLE': feature_available('imports'),
        **workspace_navigation(request),
    }
