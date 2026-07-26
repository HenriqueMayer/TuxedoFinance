from django.test import TestCase
from django.urls import reverse


class LandingViewTests(TestCase):
    """PRD FR01 — the public landing page is reachable without authentication."""

    def test_landing_page_is_public(self):
        response = self.client.get(reverse('pages:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/landing.html')
