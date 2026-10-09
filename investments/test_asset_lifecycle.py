# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Asset availability changes must preserve holdings, ledgers and history."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from banking.models import Bank, BankAccount, BankMovement, ExchangeRate, LoyaltyEntry
from banking.services import get_planning_availability
from investments.forms import AssetForm, InvestmentForm
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import get_monthly_cash_positions, get_total_in_base_timeseries, sync_investment_ledger


class AssetLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('asset-lifecycle')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Lifecycle bank')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Fund')
        self.today = timezone.localdate()

    def asset(self, code='BAL', **kwargs):
        values = dict(user=self.user, name=code, code=code, currency='BRL',
                      asset_class='LIQUIDITY', valuation_mode='MONETARY')
        values.update(kwargs)
        return Asset.objects.create(**values)

    def operation(self, asset, **kwargs):
        values = dict(user=self.user, product=self.product, asset=asset, kind='YIELD',
                      amount=Decimal('10'), date=self.today)
        values.update(kwargs)
        return Investment.objects.create(**values)

    def data(self, asset, **kwargs):
        values = dict(product=self.product.pk, asset=asset.pk, kind='YIELD', amount='10',
                      yield_input_mode='YIELD_AMOUNT', fees='0', date=self.today.isoformat())
        values.update(kwargs)
        return values

    def test_unused_asset_has_delete_confirmation_and_can_be_deleted(self):
        asset = self.asset()
        self.assertFalse(asset.is_archived)
        url = reverse('investments:delete_asset', args=[asset.pk])
        self.assertContains(self.client.get(reverse('investments:settings')), f'href="{url}"')
        response = self.client.get(url)
        self.assertContains(response, 'This action cannot be undone.')
        self.assertTrue(Asset.objects.filter(pk=asset.pk).exists())
        self.assertRedirects(self.client.post(url), reverse('investments:settings'))
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())

    def test_archive_preserves_opening_positions_operations_cash_ledgers_and_totals(self):
        asset = self.asset(opening_balance=Decimal('100'), opening_product=self.product)
        account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash', currency='BRL')
        operation = self.operation(asset, kind='DEPOSIT', amount=Decimal('50'),
                                   source_account=account, cash_amount=Decimal('50'))
        sync_investment_ledger(operation)
        operations = list(Investment.objects.values())
        movements = list(BankMovement.objects.values())
        loyalty = list(LoyaltyEntry.objects.values())
        totals = get_total_in_base_timeseries(self.user, 'BRL')
        response = self.client.post(reverse('investments:archive_asset', args=[asset.pk]))
        self.assertRedirects(response,
            reverse('investments:settings') + f'?archived={asset.pk}#asset-{asset.pk}')
        asset.refresh_from_db()
        self.assertTrue(asset.is_archived)
        self.assertEqual(asset.opening_balance, Decimal('100'))
        self.assertEqual(asset.opening_product, self.product)
        self.assertEqual(list(Investment.objects.values()), operations)
        self.assertEqual(list(BankMovement.objects.values()), movements)
        self.assertEqual(list(LoyaltyEntry.objects.values()), loyalty)
        self.assertEqual(get_total_in_base_timeseries(self.user, 'BRL'), totals)
        portfolio = self.client.get(reverse('investments:list'))
        self.assertEqual(portfolio.context['simulated_total'], Decimal('150'))
        self.assertEqual(portfolio.context['portfolio_groups'], [])
        self.assertTrue(portfolio.context['has_archived_positions'])
        self.assertContains(portfolio, 'No active positions in this section.')
        self.assertFalse(portfolio.context['setup_complete'])
        history = self.client.get(reverse('investments:operations'), {'asset': asset.pk})
        self.assertEqual(history.context['paginator'].count, 1)
        self.assertIn(asset, history.context['asset_choices'])

    def test_archive_hides_both_position_sections_and_restore_shows_them_again(self):
        asset = self.asset(opening_balance=Decimal('100'), opening_product=self.product)
        cash = InvestmentProduct.objects.create(user=self.user, bank=self.bank,
            name='Cash pot', purpose='MONTHLY_CASH')
        self.operation(asset, product=cash, amount=Decimal('40'))
        availability = get_planning_availability(self.user)['available_total']
        self.assertEqual(availability, Decimal('40'))
        chart = get_total_in_base_timeseries(self.user, 'BRL')
        self.client.post(reverse('investments:archive_asset', args=[asset.pk]))
        for section, total in [('portfolio', Decimal('100')), ('cash', Decimal('40'))]:
            with self.subTest(section=section):
                response = self.client.get(reverse('investments:list'), {'section': section},
                    HTTP_HX_REQUEST='true', HTTP_HX_BOOSTED='true', HTTP_HX_TARGET='main-content')
                self.assertEqual(response.context['portfolio_groups'], [])
                self.assertEqual(response.context['simulated_total'], total)
                self.assertEqual(response.context['native_totals'], [('BRL', total)])
                self.assertContains(response, 'Their balances remain in totals and history.')
                self.assertNotContains(response, 'Ready for your first operation')
                self.assertNotContains(response, 'Start by configuring your investments</h2>')
        self.assertEqual(get_monthly_cash_positions(self.user)[0]['balance'], Decimal('40'))
        self.assertEqual(get_planning_availability(self.user)['available_total'], availability)
        self.assertEqual(get_total_in_base_timeseries(self.user, 'BRL'), chart)
        history = self.client.get(reverse('investments:operations'), {'section': 'cash', 'asset': asset.pk})
        self.assertEqual(history.context['paginator'].count, 1)
        self.client.post(reverse('investments:restore_asset', args=[asset.pk]))
        for section in ['portfolio', 'cash']:
            response = self.client.get(reverse('investments:list'), {'section': section})
            self.assertFalse(response.context['has_archived_positions'])
            self.assertEqual(response.context['portfolio_groups'][0]['products'][0]['assets'][0]['id'], asset.pk)

    def test_archived_rows_prune_empty_groups_without_hiding_native_totals_or_missing_fx(self):
        self.product.purpose = 'MONTHLY_CASH'
        self.product.save()
        active = self.asset('ACTIVE', opening_balance=Decimal('25'), opening_product=self.product)
        self.asset('ARCHIVED', is_archived=True, currency='USD',
            opening_balance=Decimal('10'), opening_product=self.product)
        empty_product = InvestmentProduct.objects.create(user=self.user, bank=self.bank,
            name='Hidden cash product', purpose='MONTHLY_CASH')
        self.asset('HIDDEN-PRODUCT', is_archived=True, currency='USD',
            opening_balance=Decimal('3'), opening_product=empty_product)
        empty_bank = Bank.objects.create(user=self.user, name='Hidden cash bank')
        empty_bank_product = InvestmentProduct.objects.create(user=self.user, bank=empty_bank,
            name='Hidden bank product', purpose='MONTHLY_CASH')
        self.asset('HIDDEN-BANK', is_archived=True, currency='USD',
            opening_balance=Decimal('4'), opening_product=empty_bank_product)
        response = self.client.get(reverse('investments:list'), {'section': 'cash'})
        groups = response.context['portfolio_groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual([product['id'] for product in groups[0]['products']], [self.product.pk])
        self.assertEqual([asset['id'] for asset in groups[0]['products'][0]['assets']], [active.pk])
        self.assertEqual(response.context['simulated_total'], Decimal('25'))
        self.assertEqual(response.context['native_totals'], [('BRL', Decimal('25')), ('USD', Decimal('17'))])
        self.assertEqual(response.context['missing_rate_currencies'], ['USD'])
        self.assertContains(response, 'Current total incomplete')
        self.assertNotContains(response, 'Hidden cash product')
        self.assertNotContains(response, 'Hidden cash bank')
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL',
            rate=Decimal('5'), effective_date=self.today)
        response = self.client.get(reverse('investments:list'), {'section': 'cash'})
        self.assertEqual(response.context['simulated_total'], Decimal('110'))
        self.assertEqual(response.context['missing_rate_currencies'], [])
        self.assertEqual(len(response.context['valuation_rates']), 1)

    def test_zero_balance_history_remains_protected_after_archiving(self):
        asset = self.asset()
        self.operation(asset, amount=Decimal('100'))
        self.operation(asset, kind='WITHDRAWAL', amount=Decimal('100'))
        self.client.post(reverse('investments:archive_asset', args=[asset.pk]))
        self.assertEqual(self.client.get(reverse('investments:list')).context['simulated_total'], 0)
        response = self.client.post(reverse('investments:delete_asset', args=[asset.pk]))
        self.assertRedirects(response, reverse('investments:settings'))
        with self.assertRaises(ProtectedError), transaction.atomic():
            Asset.objects.filter(pk=asset.pk).delete()
        self.assertEqual(asset.operations.count(), 2)

    def test_opening_position_only_cannot_be_deleted_and_offers_archive(self):
        asset = self.asset(opening_quantity=Decimal('2'), opening_unit_price=Decimal('10'),
                           opening_product=self.product, valuation_mode='UNITS')
        response = self.client.get(reverse('investments:delete_asset', args=[asset.pk]))
        self.assertContains(response, reverse('investments:archive_asset', args=[asset.pk]))
        self.client.post(reverse('investments:archive_asset', args=[asset.pk]))
        with self.assertRaises(ProtectedError), transaction.atomic():
            Asset.objects.get(pk=asset.pk).delete()
        asset.refresh_from_db()
        self.assertEqual(asset.opening_quantity, Decimal('2'))
        self.assertEqual(asset.opening_unit_price, Decimal('10'))

    def test_new_choices_shortcuts_and_posts_reject_archived_assets(self):
        asset = self.asset(is_archived=True)
        active = self.asset('ACTIVE')
        response = self.client.get(reverse('investments:create'), {'asset': asset.pk})
        self.assertNotIn('asset', response.context['form'].initial)
        self.assertEqual(list(response.context['form'].fields['asset'].queryset), [active])
        response = self.client.post(reverse('investments:create'), self.data(asset))
        self.assertEqual(response.status_code, 200)
        self.assertIn('asset', response.context['form'].errors)
        self.assertEqual(response.context['form'].data['asset'], str(asset.pk))
        self.assertFalse(Investment.objects.exists())
        operation = Investment(user=self.user, product=self.product, asset=asset,
                               kind='YIELD', amount=Decimal('10'), date=self.today)
        with self.assertRaisesMessage(ValidationError, 'Restore this asset'):
            operation.full_clean()
        self.assertFalse(BankMovement.objects.exists())

    def test_historical_edit_and_invalid_response_keep_current_archived_selection(self):
        asset = self.asset()
        operation = self.operation(asset)
        self.client.post(reverse('investments:archive_asset', args=[asset.pk]))
        url = reverse('investments:update', args=[operation.pk])
        response = self.client.get(url)
        self.assertIn(asset, response.context['form'].fields['asset'].queryset)
        self.assertContains(response, 'The asset is archived. You can edit this operation')
        response = self.client.post(url, self.data(asset, amount='-1'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('amount', response.context['form'].errors)
        self.assertIn(asset, response.context['form'].fields['asset'].queryset)
        response = self.client.post(url, self.data(asset, amount='15', reason='Corrected history'))
        self.assertRedirects(response, reverse('investments:operations'))
        operation.refresh_from_db()
        self.assertEqual(operation.asset_id, asset.pk)
        self.assertEqual(operation.amount, Decimal('15'))
        self.assertTrue(Asset.objects.get(pk=asset.pk).is_archived)

    def test_edit_cannot_switch_to_another_archived_asset(self):
        original = self.asset('ACTIVE')
        archived = self.asset(is_archived=True)
        operation = self.operation(original)
        form = InvestmentForm(self.data(archived), user=self.user, instance=operation)
        self.assertFalse(form.is_valid())
        self.assertIn('asset', form.errors)
        operation.asset = archived
        with self.assertRaisesMessage(ValidationError, 'Restore this asset'):
            operation.full_clean()
        operation.refresh_from_db()
        self.assertEqual(operation.asset_id, original.pk)

    def test_restore_reenables_setup_and_choices_and_unused_archived_asset_can_be_deleted(self):
        asset = self.asset(is_archived=True)
        response = self.client.get(reverse('investments:settings'))
        self.assertEqual(response.context['assets'], [])
        self.assertEqual(response.context['archived_assets'], [asset])
        response = self.client.post(reverse('investments:restore_asset', args=[asset.pk]))
        self.assertRedirects(response, reverse('investments:settings') + f'#asset-{asset.pk}')
        asset.refresh_from_db()
        self.assertFalse(asset.is_archived)
        self.assertTrue(self.client.get(reverse('investments:list')).context['setup_complete'])
        self.assertIn(asset, InvestmentForm(user=self.user).fields['asset'].queryset)
        self.client.post(reverse('investments:archive_asset', args=[asset.pk]))
        self.client.post(reverse('investments:delete_asset', args=[asset.pk]))
        self.assertFalse(Asset.objects.filter(pk=asset.pk).exists())

    def test_archive_and_restore_require_post_owner_login_and_csrf(self):
        asset = self.asset()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        for route in ('archive_asset', 'restore_asset'):
            url = reverse('investments:' + route, args=[asset.pk])
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(strict.post(url).status_code, 403)
        other = get_user_model().objects.create_user('other-asset-owner')
        self.client.force_login(other)
        for route in ('archive_asset', 'restore_asset'):
            self.assertEqual(self.client.post(reverse('investments:' + route, args=[asset.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('investments:settings')), asset.name)
        self.client.logout()
        self.assertEqual(self.client.post(reverse('investments:archive_asset', args=[asset.pk])).status_code, 302)
        asset.refresh_from_db()
        self.assertFalse(asset.is_archived)

    def test_archived_asset_code_and_editor_preserve_availability(self):
        asset = self.asset(is_archived=True)
        values = dict(name='Renamed', code=asset.code, asset_class=asset.asset_class,
            currency=asset.currency, valuation_mode=asset.valuation_mode, opening_balance='0',
            opening_quantity='0', opening_unit_price='0', is_archived='')
        form = AssetForm(values, user=self.user, instance=asset)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(Asset.objects.get(pk=asset.pk).is_archived)
        duplicate = AssetForm(values, user=self.user)
        self.assertFalse(duplicate.is_valid())
        self.assertIn('code', duplicate.errors)

    def test_portuguese_archive_labels_and_record_identifiers_are_unlocalized(self):
        asset = self.asset(pk=1001, is_archived=True)
        operation = self.operation(asset, pk=1001)
        self.client.cookies['django_language'] = 'pt-br'
        response = self.client.get(reverse('investments:settings'))
        self.assertContains(response, 'Ativos arquivados')
        self.assertContains(response, 'Restaurar')
        self.assertContains(response, 'id="asset-1001"')
        self.assertContains(response, 'id="asset-availability-1001"')
        self.assertNotContains(response, 'asset-1.001')
        editor = self.client.get(reverse('investments:update', args=[operation.pk]))
        self.assertContains(editor, 'name="operation_id" value="1001"')
        preview = self.client.post(reverse('investments:yield_preview'), self.data(asset,
            operation_id=operation.pk, yield_input_mode='ENDING_BALANCE', ending_balance='15'))
        self.assertIsNotNone(preview.context['preview'])
