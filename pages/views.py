from django.views.generic import TemplateView


class LandingView(TemplateView):
    """Public landing page. Full hero/sections ship in Sprint 2 (pages app)."""

    template_name = 'pages/landing.html'
