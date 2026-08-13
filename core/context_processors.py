from accounts.models import UserPreference
from core.currencies import get_currency, DEFAULT_CURRENCY


def currency(request):
    """Expose the project-wide currency symbol to every template (PRD §8.5).

    Registered in `TEMPLATES[0]['OPTIONS']['context_processors']`, so
    `{{ CURRENCY_SYMBOL }}` is available on every screen without per-view
    plumbing. Change `settings.CURRENCY_SYMBOL` to switch currencies —
    never hardcode a symbol in a template.
    """
    code = DEFAULT_CURRENCY
    if request.user.is_authenticated:
        code = UserPreference.for_user(request.user).base_currency
    return {
        'CURRENCY_CODE': code,
        'CURRENCY_SYMBOL': get_currency(code).symbol,
    }
