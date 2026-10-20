# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Position personalization never reinterprets its financial evidence."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserPreference
from banking.models import Bank, BankMovement, CardInvoice
from investments.appearance import icon_identity, position_appearance_map, save_position_appearance
from investments.models import Asset, Investment, InvestmentProduct, PositionAppearance, PositionPlanningSetting
from investments.positions import get_portfolio_valuation
from planning.models import FinancialGoal, GoalAllocation


class PositionAppearanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('position-appearance-owner')
        UserPreference.for_user(self.user)
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Appearance bank')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank,
            name='Monthly reserve', purpose='MONTHLY_CASH')
        self.asset = Asset.objects.create(user=self.user, name='Shared balance', code='SHARED',
            asset_class='LIQUIDITY', valuation_mode='MONETARY', currency='BRL',
            opening_product=self.product, opening_balance=Decimal('100'), opening_date=date(2026, 1, 1))
        self.url = reverse('investments:position_detail', args=[self.product.pk, self.asset.pk])

    def finances(self):
        return {model._meta.label: list(model.objects.order_by('pk').values()) for model in
                (Asset, InvestmentProduct, Investment, BankMovement, CardInvoice, PositionPlanningSetting)}

    def test_legacy_positions_have_general_icon_without_creating_settings(self):
        before = self.finances()
        response = self.client.get(reverse('investments:list'))
        self.assertContains(response, '💰')
        self.assertContains(response, '#position-personalization')
        self.assertFalse(PositionAppearance.objects.exists())
        self.assertEqual(before, self.finances())
        self.assertEqual(icon_identity('not-an-icon')['emoji'], '💰')

    def test_personalization_changes_only_the_selected_position_and_preserves_origin(self):
        second_bank = Bank.objects.create(user=self.user, name='Another appearance bank')
        second = InvestmentProduct.objects.create(user=self.user, bank=second_bank,
            name='Other application', purpose='MONTHLY_CASH')
        operation = Investment.objects.create(user=self.user, product=second, asset=self.asset,
            kind='YIELD', amount=Decimal('25'), date=date(2026, 1, 2))
        before = self.finances()
        value_before = get_portfolio_valuation(self.user)['total']
        destination = '/investments/?scope=cash&q=Shared#position-1-1-mobile'
        response = self.client.post(self.url, {'action': 'appearance', 'appearance-icon': 'reserve', 'next': destination,
            'amount': '999999', 'opening_balance': '999999', 'purpose': 'INVESTMENT', 'planning_enabled': 'on'})
        self.assertRedirects(response, destination, fetch_redirect_response=False)
        other_url = reverse('investments:position_detail', args=[second.pk, self.asset.pk])
        response = self.client.post(other_url, {'action': 'appearance', 'appearance-icon': 'home'})
        self.assertRedirects(response, other_url + '#position-personalization', fetch_redirect_response=False)
        self.assertEqual(PositionAppearance.objects.get(product=self.product).icon, 'reserve')
        self.assertEqual(PositionAppearance.objects.get(product=second).icon, 'home')
        self.assertEqual(before, self.finances())
        self.assertEqual(get_portfolio_valuation(self.user)['total'], value_before)
        history = self.client.get(reverse('investments:operations'), {'product': second.pk})
        self.assertContains(history, '🏠')
        self.assertContains(history, operation.asset.code)
        listing = self.client.get(reverse('investments:list'))
        self.assertContains(listing, '🛟')
        self.assertContains(listing, '🏠')
        updated = self.client.get(reverse('investments:position_update', args=[second.pk, self.asset.pk]))
        self.assertContains(updated, '🏠')

    def test_repeated_post_is_idempotent_and_rejects_external_return(self):
        for _ in range(2):
            response = self.client.post(self.url, {'action': 'appearance', 'appearance-icon': 'piggy', 'next': '//outside.test/'})
            self.assertEqual(response.url, self.url + '#position-personalization')
        self.assertEqual(PositionAppearance.objects.count(), 1)

    def test_invalid_icon_and_action_preserve_saved_selection_and_finances(self):
        save_position_appearance(self.user, self.product, self.asset, 'home')
        before = self.finances()
        response = self.client.post(self.url, {'action': 'appearance', 'appearance-icon': '<script>alert(1)</script>'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['appearance_form'].errors.get('icon'))
        self.assertContains(response, 'aria-invalid="true"')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(PositionAppearance.objects.get().icon, 'home')
        self.assertEqual(before, self.finances())
        self.assertEqual(self.client.post(self.url, {'action': 'deposit', 'appearance-icon': 'goal'}).status_code, 400)

    def test_foreign_or_unrelated_pairs_cannot_be_personalized(self):
        stranger = get_user_model().objects.create_user('appearance-stranger')
        private_bank = Bank.objects.create(user=stranger, name='Private appearance bank')
        private = InvestmentProduct.objects.create(user=stranger, bank=private_bank, name='Private product')
        private_url = reverse('investments:position_detail', args=[private.pk, self.asset.pk])
        self.assertEqual(self.client.post(private_url, {'action': 'appearance', 'appearance-icon': 'home'}).status_code, 404)
        owned = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Unused owned product')
        unrelated_url = reverse('investments:position_detail', args=[owned.pk, self.asset.pk])
        self.assertEqual(self.client.post(unrelated_url, {'action': 'appearance', 'appearance-icon': 'home'}).status_code, 404)
        with self.assertRaises(ValidationError):
            save_position_appearance(self.user, owned, self.asset, 'home')
        with self.assertRaises(ValidationError):
            save_position_appearance(self.user, private, self.asset, 'home')
        self.assertFalse(PositionAppearance.objects.exists())

    def test_icon_allowlist_and_unique_position_are_enforced_in_database(self):
        save_position_appearance(self.user, self.product, self.asset, 'general')
        with self.assertRaises(IntegrityError), transaction.atomic():
            PositionAppearance.objects.create(user=self.user, product=self.product, asset=self.asset, icon='home')
        with self.assertRaises(IntegrityError), transaction.atomic():
            PositionAppearance.objects.filter(user=self.user).update(icon='invalid')

    def test_goal_source_shows_its_position_identity_without_changing_reservation(self):
        goal = FinancialGoal.objects.create(user=self.user, name='Safety goal', target_amount='200', currency='BRL')
        allocation = GoalAllocation.objects.create(user=self.user, goal=goal, product=self.product,
                                                   asset=self.asset, amount='40')
        before = self.finances()
        allocation_before = list(GoalAllocation.objects.values())
        save_position_appearance(self.user, self.product, self.asset, 'reserve')
        response = self.client.get(reverse('planning:goal_detail', args=[goal.pk]))
        self.assertContains(response, '🛟')
        self.assertContains(response, self.asset.name)
        self.assertEqual(list(GoalAllocation.objects.values()), allocation_before)
        self.assertEqual(response.context['row']['allocations'][0]['allocation'], allocation)
        self.assertEqual(before, self.finances())

    def test_guided_icon_selection_and_invalid_recovery_are_atomic(self):
        payload = {'institution': self.bank.pk, 'name': 'Guided appearance', 'valuation_mode': 'MONETARY',
            'purpose': 'INVESTMENT', 'currency': 'BRL', 'opening_balance': '0', 'icon': 'travel'}
        response = self.client.post(reverse('investments:guided_create'), {**payload, 'icon': 'unknown'})
        self.assertTrue(response.context['form'].errors.get('icon'))
        self.assertFalse(Asset.objects.filter(name=payload['name']).exists())
        response = self.client.post(reverse('investments:guided_create'), payload)
        self.assertEqual(response.status_code, 302)
        created = Asset.objects.get(name=payload['name'])
        self.assertEqual(PositionAppearance.objects.get(asset=created).icon, 'travel')
        self.assertFalse(Investment.objects.exists())
        self.assertFalse(BankMovement.objects.exists())
        self.assertContains(self.client.get(response.url), '✈️')

    def test_native_form_requires_csrf_and_appearance_cache_is_scoped_to_owner(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {'action': 'appearance', 'appearance-icon': 'home'}).status_code, 403)
        save_position_appearance(self.user, self.product, self.asset, 'reserve')
        with patch('investments.templatetags.investment_identity.position_appearance_map',
                   wraps=position_appearance_map) as lookup:
            self.client.get(reverse('investments:list'))
            self.assertEqual(lookup.call_count, 1)
        self.client.logout()
        anonymous = self.client.get(self.url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertNotIn('🛟', anonymous.content.decode())
