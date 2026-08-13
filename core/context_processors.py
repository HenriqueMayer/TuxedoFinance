from django.conf import settings


def currency(request):
    """Expose the project-wide currency symbol to every template (PRD §8.5).

    Registered in `TEMPLATES[0]['OPTIONS']['context_processors']`, so
    `{{ CURRENCY_SYMBOL }}` is available on every screen without per-view
    plumbing. Change `settings.CURRENCY_SYMBOL` to switch currencies —
    never hardcode a symbol in a template.
    """
    return {'CURRENCY_SYMBOL': settings.CURRENCY_SYMBOL}
