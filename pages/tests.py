from django.test import TestCase


class LandingBrandTests(TestCase):
    def test_landing_uses_tuxedo_title_and_brand_story(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<title>Tuxedo Finance — Take control of your personal finances</title>', html=True)
        self.assertContains(response, 'brand/tuxedo-hero.jpg')
        self.assertContains(response, 'A tuxedo cat in a home office beside charts and the Tuxedo Finance wordmark.')
        content = response.content.decode()
        self.assertLess(content.index('Your finances deserve more than a'), content.index('Clear money, elegantly presented.'))

    def test_shared_shell_exposes_wordmark_and_favicon(self):
        response = self.client.get('/')

        self.assertContains(response, 'brand/favicon.ico')
        self.assertContains(response, 'brand/apple-touch-icon.png')
        self.assertContains(
            response,
            'brand/tuxedo-mark-256.png',
        )
        self.assertContains(
            response,
            '<span class="block text-sm tracking-[0.2em] uppercase font-medium">Tuxedo</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="block text-xs tracking-[0.15em] uppercase text-caramel mt-0.5">Finance</span>',
            html=True,
        )
