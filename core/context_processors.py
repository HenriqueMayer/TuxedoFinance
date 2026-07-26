from django.conf import settings


def currency(request):
    """Expose the project-wide currency symbol to every template (PRD §8.5).

    Registered in `TEMPLATES[0]['OPTIONS']['context_processors']`, so
    `{{ CURRENCY_SYMBOL }}` is available on every screen without per-view
    plumbing. Change `settings.CURRENCY_SYMBOL` to switch currencies —
    never hardcode a symbol in a template.
    """
    return {'CURRENCY_SYMBOL': settings.CURRENCY_SYMBOL}


def debug_flag(request):
    """Expose `settings.DEBUG` to every template as `DEBUG` (PRD §10.6).

    Used by `base.html` to pick the Tailwind Play CDN in development or the
    compiled `css/output.css` bundle (served by WhiteNoise) in production.
    Deliberately independent from Django's built-in `debug` context
    processor, which only injects its variables for requests coming from
    `INTERNAL_IPS` — unsuitable for this always-on template switch.
    """
    return {'DEBUG': settings.DEBUG}
