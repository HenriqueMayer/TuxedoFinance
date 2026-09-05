from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class LandingBrandTests(TestCase):
    def test_landing_has_factual_content_and_cat_portrait(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<title>Tuxedo Finance</title>', html=True)
        self.assertContains(response, 'brand/tuxedo-hero.jpg')
        self.assertContains(response, 'A black-and-white cat wearing a bow tie at a desk.')
        self.assertContains(response, 'A local application to record income and expenses')
        for label in ('Transactions and categories', 'Accounts and cards',
                      'Recurrences and installments', 'Investments', 'Reports', 'Salary sandbox'):
            self.assertContains(response, label)
        for removed in ('Sample dashboard preview', 'Understand your cash flow',
                        'Clear money, elegantly presented.', 'Ready to see your cash flow clearly?',
                        'Your money, in black and white.', 'in under 30 seconds'):
            self.assertNotContains(response, removed)

    @override_settings(LANGUAGE_CODE='pt-br')
    def test_landing_translates_primary_copy_to_brazilian_portuguese(self):
        response = self.client.get('/', HTTP_ACCEPT_LANGUAGE='pt-br')
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Language'], 'pt-br')
        self.assertContains(response, 'Aplicação local para registrar receitas e despesas')
        self.assertContains(response, 'Transações e categorias')
        self.assertContains(response, 'Funcionalidades')
        self.assertContains(response, 'Simulação salarial')
        self.assertContains(response, 'Criar conta')
        self.assertNotIn('A local application', content)

    @override_settings(ALLOW_SIGNUPS=True)
    def test_visitor_can_login_or_create_account(self):
        response = self.client.get('/')
        self.assertContains(response, f'href="{reverse("accounts:login")}"')
        self.assertContains(response, f'href="{reverse("accounts:signup")}"')
        self.assertNotContains(response, 'Open dashboard')

    @override_settings(ALLOW_SIGNUPS=False)
    def test_closed_registration_keeps_login(self):
        response = self.client.get('/')
        self.assertContains(response, f'href="{reverse("accounts:login")}"')
        self.assertNotContains(response, reverse('accounts:signup'))

    def test_authenticated_homepage_links_to_dashboard(self):
        user = get_user_model().objects.create_user(username='landing-user')
        self.client.force_login(user)
        response = self.client.get('/')
        self.assertContains(response, 'Open dashboard')
        self.assertNotContains(response, reverse('accounts:signup'))
        self.assertNotContains(response, reverse('accounts:login'))

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
            '<span class="block text-xs tracking-[0.15em] uppercase text-caramel-ink dark:text-caramel-light mt-0.5">Finance</span>',
            html=True,
        )
