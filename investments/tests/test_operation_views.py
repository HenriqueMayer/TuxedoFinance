"""Operation views coverage for investments."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from banking.models import Bank, BankAccount, BankMovement, ExchangeRate
from investments.forms import InvestmentForm
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import get_portfolio_groups, get_total_in_base_timeseries, refresh_fx_snapshot, sync_investment_ledger
from investments.tests.fixtures import InvestmentFixtureMixin


User = get_user_model()


BASE = 'BRL'


class InvestmentFormAndViewTests(InvestmentFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)

    def test_funding_choice_preserves_edits_and_legacy_native_posts(self):
        self.assertEqual(InvestmentForm(user=self.user).initial['funding_source'], '')
        operation = self.operation(kind=Investment.Kind.DEPOSIT,
            source_account=self.account, cash_amount=Decimal('100'))
        operation.save()
        self.assertEqual(InvestmentForm(instance=operation, user=self.user).initial['funding_source'], 'ACCOUNT')
        data = {'product': self.product.pk, 'asset': self.asset.pk, 'kind': 'DEPOSIT',
            'quantity': '1', 'unit_price': '100', 'cash_amount': '100', 'fees': '0',
            'source_account': self.account.pk, 'date': '2026-09-25'}
        form = InvestmentForm(data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['funding_source'], 'ACCOUNT')
        mismatched = InvestmentForm({**data, 'funding_source': 'POINTS'}, user=self.user)
        self.assertFalse(mismatched.is_valid())
        self.assertIn('source_program', mismatched.errors)
        points = {**data, 'source_account': '', 'source_program': self.program.pk, 'source_points': '10'}
        form = InvestmentForm(points, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['funding_source'], 'POINTS')
        ambiguous = InvestmentForm({**points, 'source_account': self.account.pk}, user=self.user)
        self.assertFalse(ambiguous.is_valid())
        self.assertIn('source_account', ambiguous.errors)

    def test_form_is_user_scoped_and_has_no_title(self):
        other = User.objects.create_user('form-other')
        bank = Bank.objects.create(user=other, name='Private')
        account = BankAccount.objects.create(user=other, bank=bank, name='Hidden', currency=BASE)
        form = InvestmentForm(user=self.user)
        self.assertNotIn('title', form.fields)
        self.assertNotIn(account, form.fields['source_account'].queryset)
        self.assertEqual(list(form.fields['product'].queryset), [self.product])

    def test_operation_form_exposes_scoped_asset_mode_for_progressive_ui(self):
        form = InvestmentForm(user=self.user)
        html = str(form['asset'])
        self.assertIn('data-valuation-mode="UNITS"', html)
        self.assertIn(f'data-currency="{self.asset.currency}"', html)

        response = self.client.get(reverse('investments:create'))
        self.assertContains(response, 'id="money-fields"')
        self.assertContains(response, 'id="unit-fields"')
        self.assertContains(response, 'id="operation-kind-status"')
        self.assertContains(response, 'Choose an asset and operation type')
        self.assertContains(response, 'hasPreservedProgramCash')

    def test_operation_form_keeps_server_fields_as_no_js_fallback(self):
        response = self.client.get(reverse('investments:create'))
        for field_id in (
            'id_amount', 'id_quantity', 'id_unit_price', 'id_cash_amount',
            'id_source_account', 'id_source_program', 'id_source_points',
            'id_destination_account',
        ):
            with self.subTest(field_id=field_id):
                self.assertContains(response, f'id="{field_id}"')

    def test_asset_form_exposes_unit_opening_position_fields(self):
        response = self.client.get(reverse('investments:create_asset'))

        self.assertContains(response, 'id="id_opening_quantity"')
        self.assertContains(response, 'id="id_opening_unit_price"')
        self.assertContains(response, 'id="monetary-opening-fields"')
        self.assertContains(response, 'id="unit-opening-fields"')
        self.assertContains(response, "valuationMode.addEventListener('change'")
        self.assertContains(response, "openingQuantity.value = '0'")
        self.assertContains(response, "openingBalance.value = '0'")

        response = self.client.post(reverse('investments:create_asset'), {
            'name': 'Bitcoin',
            'code': 'BTC',
            'asset_class': Asset.AssetClass.CRYPTO,
            'currency': BASE,
            'valuation_mode': Asset.ValuationMode.UNITS,
            'opening_balance': '0',
            'opening_quantity': '0.25',
            'opening_unit_price': '60000',
            'opening_product': self.product.pk,
            'opening_date': '2026-01-01',
        })

        self.assertRedirects(response, reverse('investments:settings'))
        bitcoin = Asset.objects.get(user=self.user, code='BTC')
        self.assertEqual(bitcoin.opening_quantity, Decimal('0.25000000'))

    def test_unit_positions_show_quantity_and_base_currency_value(self):
        Asset.objects.create(
            user=self.user,
            name='Bitcoin',
            code='BTC',
            asset_class=Asset.AssetClass.CRYPTO,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.UNITS,
            opening_quantity=Decimal('0.25000000'),
            opening_unit_price=Decimal('60000.00000000'),
            opening_product=self.product,
        )

        response = self.client.get(reverse('investments:list'))

        asset = response.context['portfolio_groups'][0]['products'][0]['assets'][0]
        self.assertEqual(asset['quantity'], Decimal('0.25000000'))
        self.assertEqual(asset['base_balance'], Decimal('15000.0000000000000000'))
        self.assertContains(response, '0,25 units')
        self.assertContains(response, 'BRL 15.000,00')

    def test_unit_position_display_preserves_smallest_supported_quantity(self):
        Asset.objects.create(
            user=self.user,
            name='Fractional asset',
            code='TINY',
            asset_class=Asset.AssetClass.CRYPTO,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.UNITS,
            opening_quantity=Decimal('0.00000001'),
            opening_unit_price=Decimal('60000.00000000'),
            opening_product=self.product,
        )

        response = self.client.get(reverse('investments:list'))

        self.assertContains(response, '0,00000001 units')

    def test_create_view_saves_and_synchronizes_atomically(self):
        response = self.client.post(reverse('investments:create'), {
            'product': self.product.pk,
            'asset': self.asset.pk,
            'kind': Investment.Kind.DEPOSIT,
            'quantity': '2.5',
            'unit_price': '40',
            'fees': '1.00',
            'cash_amount': '101.00',
            'source_account': self.account.pk,
            'source_program': '',
            'source_points': '',
            'destination_account': '',
            'date': timezone.localdate(),
            'reason': 'Allocation',
            'notes': '',
        })
        self.assertRedirects(response, reverse('investments:operations'))
        operation = Investment.objects.get()
        self.assertEqual(operation.bank_movement.amount, Decimal('101.00'))

    def test_monetary_create_view_uses_amount_without_units(self):
        savings = Asset.objects.create(
            user=self.user,
            name='Savings pot',
            code='POT',
            asset_class=Asset.AssetClass.LIQUIDITY,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.MONETARY,
        )
        response = self.client.post(reverse('investments:create'), {
            'product': self.product.pk,
            'asset': savings.pk,
            'kind': Investment.Kind.DEPOSIT,
            'amount': '1653.10',
            'quantity': '',
            'unit_price': '',
            'fees': '0.00',
            'cash_amount': '',
            'source_account': self.account.pk,
            'source_program': '',
            'source_points': '',
            'destination_account': '',
            'date': timezone.localdate(),
            'reason': 'Initial contribution',
            'notes': '',
        })
        self.assertRedirects(response, reverse('investments:operations'))
        operation = Investment.objects.get(asset=savings)
        self.assertIsNone(operation.quantity)
        self.assertEqual(operation.amount, Decimal('1653.10'))
        self.assertEqual(operation.bank_movement.amount, Decimal('1653.10'))
        response = self.client.get(reverse('investments:list'))
        self.assertContains(response, 'BRL 1.653,10')
        self.assertEqual(response.context['portfolio_groups'][0]['products'][0]['assets'][0]['balance'], Decimal('1653.10'))
        operations = self.client.get(reverse('investments:operations'))
        self.assertContains(operations, 'Initial contribution')
        self.assertNotContains(response, 'Initial contribution')
        self.assertNotContains(response, '1.00000000 units')

    def test_update_and_delete_views_replace_and_cleanup_ledger(self):
        baseline = self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        )
        baseline.full_clean()
        baseline.save()
        sync_investment_ledger(baseline)
        operation = self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        )
        operation.full_clean()
        operation.save()
        sync_investment_ledger(operation)
        movement_id = operation.bank_movement_id

        response = self.client.post(reverse('investments:update', args=[operation.pk]), {
            'product': self.product.pk,
            'asset': self.asset.pk,
            'kind': Investment.Kind.WITHDRAWAL,
            'quantity': '1.25',
            'unit_price': '42',
            'fees': '0',
            'cash_amount': '51.00',
            'source_account': '',
            'source_program': '',
            'source_points': '',
            'destination_account': self.account.pk,
            'date': timezone.localdate(),
            'reason': '',
            'notes': '',
        })
        self.assertRedirects(response, reverse('investments:operations'))
        movement = BankMovement.objects.get(pk=movement_id)
        self.assertEqual(movement.direction, BankMovement.Direction.CREDIT)
        self.assertEqual(movement.amount, Decimal('51.00'))

        response = self.client.post(reverse('investments:delete', args=[operation.pk]))
        self.assertRedirects(response, reverse('investments:operations'))
        self.assertFalse(BankMovement.objects.filter(pk=movement_id).exists())

    def test_grouping_filters_and_htmx_chart_contract(self):
        operation = self.operation(Investment.Kind.YIELD, reason='Coupon')
        operation.full_clean()
        operation.save()
        group = get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]
        self.assertEqual(group['quantity'], Decimal('2.50000000'))
        response = self.client.get(reverse('investments:operations'), {
            'bank': self.bank.pk, 'product': self.product.pk,
            'asset': self.asset.pk, 'q': 'Coupon',
        })
        self.assertContains(response, 'Coupon')
        htmx = self.client.get(
            reverse('investments:list'), {'flow_offset': '-1'}, HTTP_HX_REQUEST='true',
            HTTP_HX_TARGET='investments-charts',
        )
        self.assertEqual(htmx.status_code, 200)
        self.assertContains(htmx, 'id="investments-charts"')
        self.assertNotContains(htmx, '<html')

    def test_operation_filters_keep_large_identifiers_unlocalized(self):
        bank = Bank.objects.create(pk=12345, user=self.user, name='Large bank')
        product = InvestmentProduct.objects.create(pk=23456, user=self.user, bank=bank, name='Large product')
        asset = Asset.objects.create(pk=34567, user=self.user, name='Large asset', code='LARGE',
            asset_class=Asset.AssetClass.FIXED_INCOME, currency=BASE)
        operation = self.operation(product=product, asset=asset)
        operation.save()
        for language in ('en', 'pt-br'):
            with self.subTest(language=language):
                self.client.cookies['django_language'] = language
                response = self.client.get(reverse('investments:operations'), {
                    'bank': str(bank.pk), 'product': str(product.pk), 'asset': str(asset.pk),
                })
                self.assertContains(response, '<option value="12345" selected>Large bank</option>')
                self.assertContains(response, '<option value="23456" selected>Large bank / Large product</option>')
                self.assertContains(response, '<option value="34567" selected>LARGE</option>')

    def test_charts_have_mouse_and_keyboard_tooltips(self):
        operation = self.operation(
            Investment.Kind.YIELD,
            quantity=Decimal('3.00'),
            unit_price=Decimal('41.15'),
        )
        operation.full_clean()
        operation.save()

        response = self.client.get(reverse('investments:charts'))
        content = response.content.decode()

        self.assertContains(response, 'group-hover:opacity-100')
        self.assertContains(response, 'group-focus-visible:opacity-100')
        self.assertNotContains(response, 'group-focus:opacity-100')
        self.assertContains(response, 'tabindex="0"')
        self.assertContains(response, 'R$ 123,45')
        for marks, interactions in (
            ('investment-total-marks', 'investment-total-interactions'),
            ('investment-flow-marks', 'investment-flow-interactions'),
        ):
            with self.subTest(chart=marks):
                self.assertLess(
                    content.index(f'data-chart-layer="{marks}"'),
                    content.index(f'data-chart-layer="{interactions}"'),
                )

    def test_portfolio_links_to_separate_charts_and_operations(self):
        response = self.client.get(reverse('investments:list'))
        self.assertNotContains(response, 'id="investments-charts"')
        self.assertContains(response, reverse('investments:charts'))
        self.assertContains(response, reverse('investments:operations'))

    def test_movement_pagination_uses_a_position_preserving_htmx_island(self):
        for index in range(11):
            operation = self.operation(reason=f'Operation {index + 1}')
            operation.full_clean()
            operation.save()

        response = self.client.get(reverse('investments:operations'))
        self.assertContains(response, 'id="investment-movements"')
        self.assertContains(response, 'data-live-results="investment-operation-results"')
        self.assertContains(response, 'data-live-link="investment-history-filters"')
        self.assertContains(response, 'data-scroll-target="investment-movements"')
        self.assertContains(response, '?page=2#investment-movements')

        htmx = self.client.get(
            reverse('investments:operations'),
            {'page': '2'},
            HTTP_HX_REQUEST='true',
            HTTP_HX_TARGET='investment-movements',
        )
        self.assertEqual(htmx.status_code, 200)
        self.assertContains(htmx, 'id="investment-movements"')
        self.assertContains(htmx, 'Page 2 of 2')
        self.assertNotContains(htmx, 'id="investments-charts"')
        self.assertNotContains(htmx, '<html')

    def test_historical_conversion_uses_banking_exchange_rate(self):
        foreign = Asset.objects.create(
            user=self.user, name='Dollar', code='USD',
            asset_class=Asset.AssetClass.CURRENCY, currency='USD'
        )
        ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency=BASE,
            rate=Decimal('5.00'), effective_date=date(2024, 1, 1)
        )
        operation = self.operation(
            Investment.Kind.YIELD, asset=foreign,
            quantity=Decimal('2.00'), unit_price=Decimal('50.00'),
            date=date(2024, 6, 1),
        )
        operation.full_clean()
        operation.save()
        rows, missing = get_total_in_base_timeseries(
            self.user, BASE, months=36, offset=0
        )
        self.assertEqual(missing, [])
        self.assertTrue(any(row['total'] == Decimal('500.00') for row in rows))

    def test_reconstructed_snapshot_is_immutable_after_rate_change(self):
        foreign = Asset.objects.create(
            user=self.user, name='Historic dollar', code='HUSD',
            asset_class=Asset.AssetClass.CURRENCY, currency='USD',
        )
        rate = ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency=BASE,
            rate=Decimal('5.00'), effective_date=date(2024, 1, 1),
        )
        operation = self.operation(
            Investment.Kind.YIELD, asset=foreign, quantity=Decimal('2.00'),
            unit_price=Decimal('50.00'), date=date(2024, 6, 1),
        )
        operation.save()
        refresh_fx_snapshot(operation)
        operation.fx_snapshot_status = Investment.FxSnapshotStatus.RECONSTRUCTED
        operation.save(update_fields=['fx_snapshot_status'])
        rate.rate = Decimal('9.00')
        rate.save(update_fields=['rate'])

        rows, missing = get_total_in_base_timeseries(self.user, BASE, months=36)

        self.assertEqual(missing, [])
        self.assertTrue(any(row['total'] == Decimal('500.00') for row in rows))

    def test_settings_keeps_bank_navigation_without_an_investment_exchange_rate_route(self):
        response = self.client.get(reverse('investments:settings'))
        self.assertContains(response, reverse('banking:list'))
        self.assertContains(response, reverse('investments:list'))
        self.assertNotContains(response, 'investments/settings/exchange-rates')
