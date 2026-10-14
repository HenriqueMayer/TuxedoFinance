from django.views.generic import TemplateView


class LandingView(TemplateView):
    """Public product overview; no financial records are queried."""

    template_name = 'pages/landing.html'
