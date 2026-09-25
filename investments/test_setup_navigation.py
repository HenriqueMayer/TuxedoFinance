# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank
from investments.models import Asset, InvestmentProduct


class InvestmentSetupNavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('setup-owner')
        self.client.force_login(self.user)

    def assert_primary(self, complete):
        for url in [reverse('investments:list'), reverse('investments:list') + '?section=cash',
                    reverse('investments:operations')]:
            response = self.client.get(url)
            self.assertEqual(response.context['setup_complete'], complete)
            target = 'investments:create' if complete else 'investments:settings'
            self.assertContains(response, f'href="{reverse(target)}" class="action-primary"')
            if not complete:
                self.assertNotContains(response, 'New operation')

    def test_primary_action_follows_setup_and_not_operation_count(self):
        self.assert_primary(False)
        response = self.client.get(reverse('investments:settings'))
        self.assertContains(response, f'href="{reverse("banking:create")}" class="action-primary"')
        self.assertNotContains(response, 'id="investment-products"')
        bank = Bank.objects.create(user=self.user, name='Investment bank')
        self.assert_primary(False)
        response = self.client.get(reverse('investments:settings'))
        self.assertContains(response, f'href="{reverse("investments:create_product")}" class="action-primary"')
        InvestmentProduct.objects.create(user=self.user, bank=bank, name='Brokerage')
        self.assert_primary(False)
        response = self.client.get(reverse('investments:settings'))
        self.assertContains(response, f'href="{reverse("investments:create_asset")}" class="action-primary"')
        asset = Asset.objects.create(user=self.user, name='Fund', code='FUND', currency='BRL')
        self.assert_primary(True)
        response = self.client.get(reverse('investments:settings'))
        self.assertNotContains(response, 'id="investment-setup"')
        self.assertContains(response, 'Investment bank')
        self.assertContains(response, reverse('investments:update_asset', args=[asset.pk]))
        asset.delete()
        self.assert_primary(False)

    def test_another_users_configuration_does_not_complete_setup(self):
        other = get_user_model().objects.create_user('other-setup')
        bank = Bank.objects.create(user=other, name='Private bank')
        InvestmentProduct.objects.create(user=other, bank=bank, name='Private product')
        Asset.objects.create(user=other, name='Private asset', code='PRIVATE')
        self.assert_primary(False)
        response = self.client.get(reverse('investments:settings'))
        self.assertNotContains(response, 'Private')

    def test_simulation_notice_has_no_destination_and_planning_keeps_its_link(self):
        for route in ['investments:list', 'investments:settings', 'investments:operations']:
            response = self.client.get(reverse(route))
            self.assertContains(response, 'aria-disabled="true"')
            self.assertContains(response, 'To simulate investment returns, open Planning')
            self.assertNotContains(response, 'data-workspace-shortcut')
            self.assertContains(response, reverse('sandbox:simulation'))

    def test_portuguese_setup_and_notice_are_translated(self):
        self.client.cookies['django_language'] = 'pt-br'
        response = self.client.get(reverse('investments:list'))
        self.assertContains(response, 'Configurar investimentos')
        self.assertContains(response, 'Planejamento → Simulação de rendimentos')
        self.assertNotContains(response, 'To simulate investment returns')
