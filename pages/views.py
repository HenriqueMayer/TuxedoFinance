from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from core.features import REVIEW_ITEMS


class LandingView(TemplateView):
    """Public product overview; no financial records are queried."""

    template_name = 'pages/landing.html'


class RoadmapView(LoginRequiredMixin, TemplateView):
    template_name = 'pages/roadmap.html'

    def get_context_data(self, **kwargs):
        from ingestion.models import ImportBatch
        context = super().get_context_data(**kwargs)
        context['review_items'] = REVIEW_ITEMS
        context['has_import_history'] = ImportBatch.objects.filter(
            user=self.request.user, status__in=['CONFIRMED', 'UNDONE']).exists()
        return context
