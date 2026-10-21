from django.shortcuts import redirect
from django.views.generic import TemplateView


class LandingView(TemplateView):
    """Public product overview; no financial records are queried."""

    template_name = 'pages/landing.html'

    def get(self, request, *args, **kwargs):
        # The cover belongs to public entry/logout; signed-in entry opens the workspace.
        if request.user.is_authenticated:
            return redirect('dashboard:index')
        return super().get(request, *args, **kwargs)
