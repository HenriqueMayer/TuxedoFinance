from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from banking.models import (
    Bank, BankAccount, BankMovement, ExchangeRate, LoyaltyEntry, LoyaltyProgram,
)
from investments.forms import InvestmentForm
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import (
    YIELD_INPUT_AMOUNT,
    YIELD_INPUT_ENDING_BALANCE,
    calculate_monetary_yield,
    cleanup_investment_ledger,
    get_portfolio_groups,
    get_total_in_base_timeseries,
    refresh_fx_snapshot,
    sync_investment_ledger,
)


User = get_user_model()
BASE = 'BRL'


class InvestmentFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('investor', password='test')
        cls.bank = Bank.objects.create(user=cls.user, name='Portfolio Bank')
        cls.account = BankAccount.objects.create(
            user=cls.user, bank=cls.bank, name='Cash', currency=BASE
        )
        cls.program = LoyaltyProgram.objects.create(
            user=cls.user, bank=cls.bank, name='Rewards'
        )
        LoyaltyEntry.objects.create(
            user=cls.user,
            program=cls.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.ADJUSTMENT,
            amount=Decimal('10000.00'),
            date=timezone.localdate(),
        )
        cls.product = InvestmentProduct.objects.create(
            user=cls.user, bank=cls.bank, name='Brokerage'
        )
        cls.asset = Asset.objects.create(
            user=cls.user,
            name='Treasury fund',
            code='FUND',
            asset_class=Asset.AssetClass.FIXED_INCOME,
            currency=BASE,
        )

    def operation(self, kind=Investment.Kind.YIELD, **overrides):
        data = {
            'user': self.user,
            'product': self.product,
            'asset': self.asset,
            'kind': kind,
            'quantity': Decimal('2.50000000'),
            'unit_price': Decimal('40.00000000'),
            'fees': Decimal('0.00'),
            'date': timezone.localdate(),
        }
        data.update(overrides)
        return Investment(**data)


class InvestmentModelTests(InvestmentFixtureMixin, TestCase):
    def test_quantity_price_and_signed_values(self):
        deposit = self.operation(Investment.Kind.YIELD)
        withdrawal = self.operation(
            Investment.Kind.WITHDRAWAL,
            destination_account=self.account,
            cash_amount=Decimal('95.00'),
        )
        self.assertEqual(deposit.gross_value, Decimal('100.0000000000000000'))
        self.assertEqual(deposit.signed_quantity, Decimal('2.50000000'))
        self.assertEqual(withdrawal.signed_quantity, Decimal('-2.50000000'))
        self.assertEqual(withdrawal.signed_value, Decimal('-100.0000000000000000'))

    def test_validation_matrix_accepts_valid_operations(self):
        cases = (
            self.operation(
                Investment.Kind.DEPOSIT,
                source_account=self.account,
                cash_amount=Decimal('101.00'),
            ),
            self.operation(
                Investment.Kind.DEPOSIT,
                source_program=self.program,
                source_points=Decimal('1200.00'),
                cash_amount=Decimal('100.00'),
            ),
            self.operation(
                Investment.Kind.WITHDRAWAL,
                destination_account=self.account,
                cash_amount=Decimal('98.00'),
            ),
            self.operation(Investment.Kind.YIELD),
        )
        for operation in cases:
            with self.subTest(kind=operation.kind, source=operation.source_account_id):
                operation.full_clean()

    def test_validation_matrix_rejects_missing_and_irrelevant_fields(self):
        cases = (
            self.operation(Investment.Kind.DEPOSIT),
            self.operation(
                Investment.Kind.DEPOSIT,
                source_account=self.account,
                source_program=self.program,
                source_points=Decimal('1.00'),
                cash_amount=Decimal('1.00'),
            ),
            self.operation(Investment.Kind.WITHDRAWAL, cash_amount=Decimal('1.00')),
            self.operation(Investment.Kind.YIELD, cash_amount=Decimal('1.00')),
        )
        for operation in cases:
            with self.subTest(kind=operation.kind):
                with self.assertRaises(ValidationError):
                    operation.full_clean()

    def test_ownership_and_product_bank_are_validated(self):
        other = User.objects.create_user('other')
        other_bank = Bank.objects.create(user=other, name='Other Bank')
        other_account = BankAccount.objects.create(
            user=other, bank=other_bank, name='Other Cash', currency=BASE
        )
        product = InvestmentProduct(user=self.user, bank=other_bank, name='Invalid')
        with self.assertRaises(ValidationError):
            product.full_clean()
        operation = self.operation(
            Investment.Kind.DEPOSIT,
            source_account=other_account,
            cash_amount=Decimal('100.00'),
        )
        with self.assertRaises(ValidationError):
            operation.full_clean()

    def test_monetary_asset_accepts_opening_balance_without_units(self):
        savings = Asset.objects.create(
            user=self.user,
            name='Savings pot',
            code='POT',
            asset_class=Asset.AssetClass.LIQUIDITY,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.MONETARY,
            opening_balance=Decimal('1653.10'),
            opening_product=self.product,
        )
        operation = self.operation(
            Investment.Kind.DEPOSIT,
            asset=savings,
            quantity=None,
            unit_price=None,
            amount=Decimal('100.00'),
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        )
        operation.full_clean()
        self.assertEqual(operation.gross_value, Decimal('100.00'))

    def test_unit_asset_accepts_opening_quantity_and_unit_price(self):
        bitcoin = Asset.objects.create(
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

        self.assertEqual(bitcoin.opening_quantity, Decimal('0.25000000'))
        self.assertEqual(bitcoin.opening_unit_price, Decimal('60000.00000000'))

    def test_unit_asset_requires_opening_quantity_and_price_together(self):
        bitcoin = Asset(
            user=self.user,
            name='Bitcoin',
            code='BTC',
            asset_class=Asset.AssetClass.CRYPTO,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.UNITS,
            opening_quantity=Decimal('0.25000000'),
            opening_unit_price=Decimal('0.00'),
            opening_product=self.product,
        )

        with self.assertRaises(ValidationError):
            bitcoin.full_clean()


class InvestmentLedgerTests(InvestmentFixtureMixin, TestCase):
    def save_and_sync(self, operation):
        operation.full_clean()
        operation.save()
        sync_investment_ledger(operation)
        operation.refresh_from_db()
        return operation

    def test_account_deposit_creates_investment_debit(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('103.50'),
        ))
        movement = operation.bank_movement
        self.assertEqual(movement.direction, BankMovement.Direction.DEBIT)
        self.assertEqual(movement.kind, BankMovement.Kind.INVESTMENT)
        self.assertEqual(movement.amount, Decimal('103.50'))
        self.assertEqual(movement.source_key, f'investment:{operation.pk}')

    def test_points_deposit_creates_redemption_debit(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_program=self.program,
            source_points=Decimal('2500.00'),
            cash_amount=Decimal('100.00'),
        ))
        entry = operation.loyalty_entry
        self.assertEqual(entry.direction, LoyaltyEntry.Direction.DEBIT)
        self.assertEqual(entry.kind, LoyaltyEntry.Kind.REDEMPTION)
        self.assertEqual(entry.amount, Decimal('2500.00'))
        self.assertIn(f'[investment:{operation.pk}]', entry.notes)
        self.assertIsNone(operation.bank_movement)

    def test_withdrawal_credit_and_yield_has_no_cash_ledger(self):
        self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        ))
        withdrawal = self.save_and_sync(self.operation(
            Investment.Kind.WITHDRAWAL,
            destination_account=self.account,
            cash_amount=Decimal('97.00'),
        ))
        self.assertEqual(withdrawal.bank_movement.direction, BankMovement.Direction.CREDIT)
        yield_operation = self.save_and_sync(self.operation(Investment.Kind.YIELD))
        self.assertIsNone(yield_operation.bank_movement)
        self.assertIsNone(yield_operation.loyalty_entry)

    def test_withdrawal_view_rejects_more_than_available_quantity(self):
        self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        ))
        self.client.force_login(self.user)
        response = self.client.post(reverse('investments:create'), {
            'product': self.product.pk,
            'asset': self.asset.pk,
            'kind': Investment.Kind.WITHDRAWAL,
            'quantity': '3.00000000',
            'unit_price': '40.00000000',
            'fees': '0.00',
            'cash_amount': '120.00',
            'source_account': '',
            'source_program': '',
            'source_points': '',
            'destination_account': self.account.pk,
            'date': timezone.localdate(),
            'reason': '',
            'notes': '',
        })

        self.assertContains(response, 'exceeds the available position', status_code=200)

    def test_sync_update_is_idempotent_and_replaces_only_linked_ledger(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_account=self.account,
            cash_amount=Decimal('100.00'),
        ))
        movement_id = operation.bank_movement_id
        operation.cash_amount = Decimal('125.00')
        operation.save()
        sync_investment_ledger(operation)
        sync_investment_ledger(operation)
        operation.refresh_from_db()
        self.assertEqual(operation.bank_movement_id, movement_id)
        self.assertEqual(BankMovement.objects.get(pk=movement_id).amount, Decimal('125.00'))
        self.assertEqual(
            BankMovement.objects.filter(source_key=f'investment:{operation.pk}').count(), 1
        )

    def test_cleanup_removes_linked_rows_before_operation_delete(self):
        operation = self.save_and_sync(self.operation(
            Investment.Kind.DEPOSIT,
            source_program=self.program,
            source_points=Decimal('500.00'),
        ))
        entry_id = operation.loyalty_entry_id
        cleanup_investment_ledger(operation)
        operation.delete()
        self.assertFalse(LoyaltyEntry.objects.filter(pk=entry_id).exists())

    def test_monetary_opening_balance_is_available_for_withdrawal(self):
        savings = Asset.objects.create(
            user=self.user,
            name='Savings pot',
            code='POT',
            asset_class=Asset.AssetClass.LIQUIDITY,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.MONETARY,
            opening_balance=Decimal('1653.10'),
            opening_product=self.product,
        )
        withdrawal = self.save_and_sync(self.operation(
            Investment.Kind.WITHDRAWAL,
            asset=savings,
            quantity=None,
            unit_price=None,
            amount=Decimal('500.00'),
            destination_account=self.account,
            cash_amount=Decimal('500.00'),
        ))
        group = get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]
        self.assertEqual(withdrawal.bank_movement.amount, Decimal('500.00'))
        self.assertEqual(group['balance'], Decimal('1153.10'))

    def test_unit_opening_position_is_available_for_withdrawal(self):
        bitcoin = Asset.objects.create(
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
        withdrawal = self.save_and_sync(self.operation(
            Investment.Kind.WITHDRAWAL,
            asset=bitcoin,
            quantity=Decimal('0.10000000'),
            unit_price=Decimal('62000.00000000'),
            destination_account=self.account,
            cash_amount=Decimal('6200.00'),
        ))

        self.assertIsNotNone(withdrawal.bank_movement)
        group = get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]
        self.assertEqual(group['quantity'], Decimal('0.15000000'))
        self.assertEqual(group['balance'], Decimal('8800.0000000000000000'))


class MonetaryYieldTests(InvestmentFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.savings = Asset.objects.create(
            user=self.user,
            name='Savings pot',
            code='POT',
            asset_class=Asset.AssetClass.LIQUIDITY,
            currency=BASE,
            valuation_mode=Asset.ValuationMode.MONETARY,
            opening_balance=Decimal('1000.00'),
            opening_product=self.product,
        )

    def yield_data(self, **overrides):
        data = {
            'product': self.product.pk,
            'asset': self.savings.pk,
            'kind': Investment.Kind.YIELD,
            'yield_input_mode': YIELD_INPUT_ENDING_BALANCE,
            'ending_balance': '1200.00',
            'amount': '',
            'quantity': '',
            'unit_price': '',
            'fees': '0.00',
            'cash_amount': '',
            'source_account': '',
            'source_program': '',
            'source_points': '',
            'destination_account': '',
            'date': timezone.localdate(),
            'reason': '',
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_ending_balance_calculates_the_yield(self):
        calculation = calculate_monetary_yield(
            user=self.user,
            product=self.product,
            asset=self.savings,
            operation_date=timezone.localdate(),
            input_mode=YIELD_INPUT_ENDING_BALANCE,
            value=Decimal('1200.00'),
        )

        self.assertEqual(calculation.previous_balance, Decimal('1000.00'))
        self.assertEqual(calculation.yield_amount, Decimal('200.00'))
        self.assertEqual(calculation.ending_balance, Decimal('1200.00'))

    def test_direct_yield_calculates_the_ending_balance(self):
        calculation = calculate_monetary_yield(
            user=self.user,
            product=self.product,
            asset=self.savings,
            operation_date=timezone.localdate(),
            input_mode=YIELD_INPUT_AMOUNT,
            value=Decimal('200.00'),
        )

        self.assertEqual(calculation.ending_balance, Decimal('1200.00'))

    def test_form_rejects_an_unchanged_or_lower_ending_balance(self):
        unchanged = InvestmentForm(
            self.yield_data(ending_balance='1000.00'), user=self.user
        )
        lower = InvestmentForm(
            self.yield_data(ending_balance='999.99'), user=self.user
        )

        self.assertFalse(unchanged.is_valid())
        self.assertIn('ending_balance', unchanged.errors)
        self.assertFalse(lower.is_valid())
        self.assertIn('ending_balance', lower.errors)

    def test_operation_form_marks_nested_yield_error_groups(self):
        ending_balance_response = self.client.post(
            reverse('investments:create'),
            self.yield_data(
                yield_input_mode=YIELD_INPUT_AMOUNT,
                ending_balance='0',
                amount='200.00',
            ),
        )

        self.assertEqual(ending_balance_response.status_code, 200)
        self.assertIn('ending_balance', ending_balance_response.context['form'].errors)
        ending_balance_html = ending_balance_response.content.decode()
        self.assertRegex(
            ending_balance_html,
            r'id="monetary-yield-fields"\s+data-has-errors="true"',
        )
        self.assertRegex(
            ending_balance_html,
            r'id="ending-balance-field"\s+data-has-errors="true"',
        )

        amount_response = self.client.post(
            reverse('investments:create'),
            self.yield_data(amount='not-a-number'),
        )

        self.assertEqual(amount_response.status_code, 200)
        self.assertIn('amount', amount_response.context['form'].errors)
        self.assertRegex(
            amount_response.content.decode(),
            r'id="regular-amount-field"\s+data-has-errors="true"',
        )
        self.assertEqual(Investment.objects.count(), 0)

    def test_same_day_calculation_uses_registration_order_when_editing(self):
        first = Investment.objects.create(
            user=self.user, product=self.product, asset=self.savings,
            kind=Investment.Kind.YIELD, amount=Decimal('25.00'), date=timezone.localdate(),
        )
        Investment.objects.create(
            user=self.user, product=self.product, asset=self.savings,
            kind=Investment.Kind.YIELD, amount=Decimal('75.00'), date=timezone.localdate(),
        )

        calculation = calculate_monetary_yield(
            user=self.user,
            product=self.product,
            asset=self.savings,
            operation_date=timezone.localdate(),
            input_mode=YIELD_INPUT_ENDING_BALANCE,
            value=Decimal('1100.00'),
            operation=first,
        )

        self.assertEqual(calculation.previous_balance, Decimal('1000.00'))
        self.assertEqual(calculation.yield_amount, Decimal('100.00'))

    def test_preview_is_non_persistent_and_create_stores_only_the_yield(self):
        preview = self.client.post(
            reverse('investments:yield_preview'), self.yield_data()
        )

        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'Calculated yield')
        self.assertContains(preview, 'BRL 200,00')
        self.assertEqual(Investment.objects.count(), 0)

        response = self.client.post(reverse('investments:create'), self.yield_data())

        self.assertRedirects(response, reverse('investments:list'))
        operation = Investment.objects.get(asset=self.savings)
        self.assertEqual(operation.amount, Decimal('200.00'))
        self.assertIsNone(operation.bank_movement)

    def test_editing_a_monetary_yield_reconstructs_its_ending_balance(self):
        operation = Investment.objects.create(
            user=self.user, product=self.product, asset=self.savings,
            kind=Investment.Kind.YIELD, amount=Decimal('200.00'), date=timezone.localdate(),
        )

        form = InvestmentForm(user=self.user, instance=operation)

        self.assertEqual(form.initial['yield_input_mode'], YIELD_INPUT_ENDING_BALANCE)
        self.assertEqual(form.initial['ending_balance'], Decimal('1200.00'))


class InvestmentFormAndViewTests(InvestmentFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)

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
        self.assertContains(response, '0,25000000 units')
        self.assertContains(response, 'BRL 15.000,00')

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
        self.assertRedirects(response, reverse('investments:list'))
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
        self.assertRedirects(response, reverse('investments:list'))
        operation = Investment.objects.get(asset=savings)
        self.assertIsNone(operation.quantity)
        self.assertEqual(operation.amount, Decimal('1653.10'))
        self.assertEqual(operation.bank_movement.amount, Decimal('1653.10'))
        response = self.client.get(reverse('investments:list'))
        self.assertContains(response, 'Balance: BRL 1.653,10')
        self.assertContains(
            response,
            'class="mt-1 text-xs text-forest/70 dark:text-night-muted"',
        )
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
        self.assertRedirects(response, reverse('investments:list'))
        movement = BankMovement.objects.get(pk=movement_id)
        self.assertEqual(movement.direction, BankMovement.Direction.CREDIT)
        self.assertEqual(movement.amount, Decimal('51.00'))

        response = self.client.post(reverse('investments:delete', args=[operation.pk]))
        self.assertRedirects(response, reverse('investments:list'))
        self.assertFalse(BankMovement.objects.filter(pk=movement_id).exists())

    def test_grouping_filters_and_htmx_chart_contract(self):
        operation = self.operation(Investment.Kind.YIELD, reason='Coupon')
        operation.full_clean()
        operation.save()
        group = get_portfolio_groups(self.user)[0]['products'][0]['assets'][0]
        self.assertEqual(group['quantity'], Decimal('2.50000000'))
        response = self.client.get(reverse('investments:list'), {
            'bank': self.bank.pk, 'product': self.product.pk,
            'asset': self.asset.pk, 'q': 'Coupon',
        })
        self.assertContains(response, 'Coupon')
        htmx = self.client.get(
            reverse('investments:list'), {'flow_offset': '-1'}, HTTP_HX_REQUEST='true'
        )
        self.assertEqual(htmx.status_code, 200)
        self.assertContains(htmx, 'id="investments-charts"')
        self.assertNotContains(htmx, '<html')

    def test_charts_have_mouse_and_keyboard_tooltips(self):
        operation = self.operation(
            Investment.Kind.YIELD,
            quantity=Decimal('3.00'),
            unit_price=Decimal('41.15'),
        )
        operation.full_clean()
        operation.save()

        response = self.client.get(reverse('investments:list'))
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

    def test_charts_appear_before_operation_filters_and_movements(self):
        operation = self.operation()
        operation.full_clean()
        operation.save()

        response = self.client.get(reverse('investments:list'))
        content = response.content.decode()

        self.assertLess(
            content.index('id="investments-charts"'),
            content.index('id="investment-search"'),
        )
        self.assertLess(
            content.index('id="investment-search"'),
            content.index(reverse('investments:update', args=[operation.pk])),
        )

    def test_movement_pagination_uses_a_position_preserving_htmx_island(self):
        for index in range(11):
            operation = self.operation(reason=f'Operation {index + 1}')
            operation.full_clean()
            operation.save()

        response = self.client.get(reverse('investments:list'))
        self.assertContains(response, 'id="investment-movements"')
        self.assertContains(response, 'hx-target="#investment-movements"')
        self.assertContains(response, 'data-scroll-target="investment-movements"')
        self.assertContains(response, '?page=2#investment-movements')

        htmx = self.client.get(
            reverse('investments:list'),
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

    def test_settings_links_to_banking_without_broken_rate_route(self):
        response = self.client.get(reverse('investments:settings'))
        self.assertContains(response, reverse('banking:list'))
        self.assertContains(response, reverse('banking:exchange_rates'))
        self.assertNotContains(response, 'investments/settings/exchange-rates')
