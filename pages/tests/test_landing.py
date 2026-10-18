"""Landing coverage for pages."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class LandingBrandTests(TestCase):
    def test_landing_has_factual_content_and_paper_layer_map(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<title>Tuxedo Finance</title>', html=True)
        self.assertContains(response, 'data-paper-bowtie')
        self.assertContains(response, 'Your finances,<br> made <span>clear</span>.')
        self.assertContains(response, 'A ledger-paper bow tie that reveals the workspace map.')
        self.assertContains(response, 'js/paper-layers.js')
        self.assertContains(response, 'id="public-bowtie-map"')
        self.assertContains(response, 'data-bowtie-map-link=', count=5)
        self.assertContains(response, 'href="#feature-transactions"')
        self.assertContains(response, 'href="#feature-accounts"')
        self.assertContains(response, 'href="#feature-investments"')
        self.assertNotContains(response, 'Unfold map')
        self.assertNotContains(response, 'data-bowtie-fragment')
        self.assertContains(response, 'A local application to record income and expenses')
        for label in ('Transactions and categories', 'Accounts and cards',
                      'Recurrences and installments', 'Investments', 'Reports',
                      'Budgets and goals', 'Salary sandbox'):
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
        self.assertContains(response, 'Suas finanças<br> de forma <span>clara</span>.')
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
        for route in ('dashboard:index', 'transactions:list', 'banking:list',
                      'investments:list', 'planning:index'):
            self.assertContains(response, f'href="{reverse(route)}"')

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
            '<span class="block text-sm font-semibold tracking-tight">Tuxedo Finance</span>',
            html=True,
        )
