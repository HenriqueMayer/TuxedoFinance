from accounts.models import UserPreference
from core.currencies import get_currency, DEFAULT_CURRENCY
from django.conf import settings


def currency(request):
    """Expose the authenticated user's reporting currency to templates."""
    code = DEFAULT_CURRENCY
    if request.user.is_authenticated:
        code = UserPreference.for_user(request.user).base_currency
    return {
        'CURRENCY_CODE': code,
        'CURRENCY_SYMBOL': get_currency(code).symbol,
        'ALLOW_SIGNUPS': settings.ALLOW_SIGNUPS,
    }
