# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import translation


class EvolutionLocalizationTests(TestCase):
    def test_new_workspaces_render_their_portuguese_interface(self):
        self.addCleanup(translation.activate, translation.get_language())
        user = get_user_model().objects.create_user('local-language-review')
        self.client.force_login(user)
        self.client.cookies['django_language'] = 'pt-br'
        for path, heading in (
            ('/imports/', 'Importações de extratos'),
            ('/planning/budgets/', 'Orçamentos por categoria'),
            ('/planning/goals/', 'Metas'),
            ('/planning/signals/', 'Sinais locais'),
            ('/dashboard/wealth/', 'Patrimônio líquido'),
            ('/banking/invoices/', 'Faturas'),
            ('/investments/prices/', 'Cotações observadas'),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, heading)
                self.assertContains(response, 'lang="pt-br"')
                self.assertNotContains(response, 'fonts.googleapis.com')
        response = self.client.get('/banking/credit-cards/create/')
        self.assertContains(response, 'Faturas confirmadas existentes mantêm seu modo')
