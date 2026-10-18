# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import translation

from categories.models import Category


class EvolutionLocalizationTests(TestCase):
    def test_new_workspaces_render_their_portuguese_interface(self):
        self.addCleanup(translation.activate, translation.get_language())
        user = get_user_model().objects.create_user('local-language-review')
        Category.objects.create(user=user, name='Graph language review')
        self.client.force_login(user)
        self.client.cookies['django_language'] = 'pt-br'
        for path, heading in (
            ('/imports/', 'Transações'),
            ('/planning/', 'Planejar este mês'),
            ('/planning/goals/', 'Metas'),
            ('/planning/signals/', 'Sinais locais'),
            ('/dashboard/wealth/', 'Dashboard'),
            ('/banking/invoices/', 'Faturas'),
            ('/categories/?view=tree', 'Categorias'),
            ('/investments/prices/', 'Cotações observadas'),
        ):
            with self.subTest(path=path):
                response = self.client.get(path, follow=True)
                self.assertContains(response, heading)
                self.assertContains(response, 'lang="pt-br"')
                self.assertNotContains(response, 'fonts.googleapis.com')
        response = self.client.get('/banking/credit-cards/create/')
        self.assertContains(response, 'Faturas confirmadas existentes mantêm seu modo')
