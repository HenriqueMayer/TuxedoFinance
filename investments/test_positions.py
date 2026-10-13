"""Financial regression coverage for ordered costs and observed valuations."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, ExchangeRate
from banking.services import ConversionContext
from investments.forms import AssetForm, PriceObservationForm
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation
from investments.positions import get_portfolio_valuation, get_portfolio_series, validate_position_history
from investments.services import get_portfolio_groups, sync_investment_ledger


class PositionValuationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='position-owner')
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Account', currency='BRL', opening_balance=Decimal('1000'))
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Portfolio')
        self.asset = Asset.objects.create(user=self.user, name='Share', code='SHARE', asset_class='EQUITY', valuation_mode='UNITS', currency='BRL')
        self.client.force_login(self.user)

    def operation(self, kind, quantity, price, day, **kwargs):
        links = {'source_account': self.account, 'cash_amount': Decimal(quantity) * Decimal(price)} if kind == 'DEPOSIT' else (
            {'destination_account': self.account, 'cash_amount': Decimal(quantity) * Decimal(price)} if kind == 'WITHDRAWAL' else {})
        values = dict(user=self.user, product=self.product, asset=self.asset, kind=kind,
                      quantity=Decimal(quantity), unit_price=Decimal(price), date=date(2026, 9, day), **links)
        values.update(kwargs)
        operation = Investment.objects.create(**values)
        sync_investment_ledger(operation)
        return operation

    def position(self, day=30):
        return get_portfolio_valuation(self.user, date(2026, 9, day))['positions'][0]

    def test_full_sale_clears_cost_and_preserves_cash_gain(self):
        self.operation('DEPOSIT', '1', '100', 1)
        self.operation('WITHDRAWAL', '1', '150', 2)
        row = self.position()
        self.assertEqual(row['quantity'], Decimal('0'))
        self.assertEqual(row['remaining_cost'], Decimal('0'))
        self.assertEqual(row['realized_gain'], Decimal('50'))
        self.assertEqual(get_portfolio_groups(self.user, date(2026, 9, 30))[0]['products'][0]['assets'][0]['balance'], Decimal('0'))
        self.assertEqual(sum(BankMovement.objects.values_list('amount', flat=True)), Decimal('250'))

    def test_partial_sale_uses_weighted_cost_per_product_and_asset(self):
        self.operation('DEPOSIT', '1', '100', 1)
        self.operation('DEPOSIT', '1', '200', 2)
        self.operation('WITHDRAWAL', '1', '250', 3)
        row = self.position()
        self.assertEqual((row['quantity'], row['remaining_cost'], row['realized_gain']), (Decimal('1'), Decimal('150'), Decimal('100')))
        other = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Other product')
        self.operation('DEPOSIT', '1', '10', 4, product=other)
        rows = get_portfolio_valuation(self.user, date(2026, 9, 30))['positions']
        self.assertEqual(sorted(row['remaining_cost'] for row in rows), [Decimal('10'), Decimal('150')])

    def test_yield_entry_value_and_legacy_fees_are_preserved(self):
        self.operation('YIELD', '2', '30', 1, fees=Decimal('99'))
        self.operation('WITHDRAWAL', '1', '40', 2)
        row = self.position()
        self.assertEqual((row['remaining_cost'], row['realized_gain'], row['unapplied_fees']), (Decimal('30'), Decimal('10'), Decimal('99')))

    def test_explicit_asset_currency_fees_change_cost_not_cash(self):
        deposit = self.operation('DEPOSIT', '2', '100', 1, fees=Decimal('4'), fees_in_asset_currency=True, cash_amount=Decimal('207'))
        sale = self.operation('WITHDRAWAL', '1', '150', 2, fees=Decimal('3'), fees_in_asset_currency=True, cash_amount=Decimal('140'))
        row = self.position()
        self.assertEqual((row['remaining_cost'], row['realized_gain']), (Decimal('102'), Decimal('45')))
        self.assertEqual((deposit.bank_movement.amount, sale.bank_movement.amount), (Decimal('207'), Decimal('140')))

    def test_delete_and_edit_reject_invalid_later_withdrawal_atomically(self):
        deposit = self.operation('DEPOSIT', '2', '100', 1)
        self.operation('WITHDRAWAL', '2', '150', 2)
        before = list(BankMovement.objects.order_by('pk').values_list('pk', 'amount'))
        deleted = self.client.post(reverse('investments:delete', args=[deposit.pk]))
        self.assertEqual(deleted.status_code, 200)
        self.assertContains(deleted, 'exceeds the available position')
        self.assertTrue(Investment.objects.filter(pk=deposit.pk).exists())
        edited = self.client.post(reverse('investments:update', args=[deposit.pk]), {
            'product': self.product.pk, 'asset': self.asset.pk, 'kind': 'DEPOSIT', 'quantity': '1',
            'unit_price': '100', 'cash_amount': '100', 'source_account': self.account.pk,
            'funding_source': 'ACCOUNT', 'fees': '0', 'date': '2026-09-01'})
        self.assertEqual(edited.status_code, 200)
        deposit.refresh_from_db()
        self.assertEqual(deposit.quantity, Decimal('2'))
        self.assertEqual(before, list(BankMovement.objects.order_by('pk').values_list('pk', 'amount')))

    def test_same_day_registration_order_cannot_borrow_later_units(self):
        deposit = self.operation('DEPOSIT', '1', '100', 1)
        self.operation('WITHDRAWAL', '1', '150', 1)
        with self.assertRaises(ValidationError):
            validate_position_history(self.user, [(self.product.pk, self.asset.pk)], exclude_pk=deposit.pk)

    def test_out_of_order_edit_validates_future_and_old_position(self):
        deposit = self.operation('DEPOSIT', '2', '100', 1)
        self.operation('WITHDRAWAL', '2', '150', 2)
        deposit.date = date(2026, 9, 3)
        with self.assertRaises(ValidationError):
            deposit.full_clean()
        other = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Moved product')
        deposit.date = date(2026, 9, 1)
        deposit.product = other
        with self.assertRaises(ValidationError):
            deposit.full_clean()
        deposit.refresh_from_db()
        self.assertEqual(deposit.product, self.product)

    def test_fractional_complete_disposal_has_no_cost_dust(self):
        self.operation('YIELD', '.00000001', '33333333.33333333', 1)
        self.operation('YIELD', '.00000002', '55555555.55555555', 2)
        self.operation('WITHDRAWAL', '.00000001', '77777777.77777777', 3, cash_amount=Decimal('.78'))
        self.operation('WITHDRAWAL', '.00000002', '77777777.77777777', 4, cash_amount=Decimal('1.56'))
        row = self.position()
        self.assertEqual((row['quantity'], row['remaining_cost'], row['average_cost']), (Decimal('0'), Decimal('0'), Decimal('0')))

    def test_dated_opening_does_not_exist_before_baseline(self):
        self.asset.opening_product = self.product
        self.asset.opening_quantity = Decimal('2')
        self.asset.opening_unit_price = Decimal('100')
        self.asset.opening_date = date(2026, 9, 10)
        self.asset.save()
        self.assertEqual(get_portfolio_valuation(self.user, date(2026, 9, 9))['total'], Decimal('0'))
        self.assertEqual(get_portfolio_valuation(self.user, date(2026, 9, 10))['cost_total'], Decimal('200'))
        new = AssetForm({'name': 'Opening', 'code': 'OPEN', 'asset_class': 'EQUITY', 'currency': 'BRL',
                         'valuation_mode': 'UNITS', 'opening_quantity': '1', 'opening_unit_price': '10',
                         'opening_balance': '0', 'opening_product': self.product.pk}, user=self.user)
        self.assertFalse(new.is_valid())
        self.assertIn('opening_date', new.errors)

    def test_legacy_unknown_opening_remains_explicit_and_can_be_dated(self):
        self.asset.opening_product = self.product
        self.asset.opening_quantity = Decimal('1')
        self.asset.opening_unit_price = Decimal('100')
        self.asset.save()
        snapshot = get_portfolio_valuation(self.user, date(2026, 9, 30))
        self.assertEqual(snapshot['total'], Decimal('100'))
        self.assertTrue(snapshot['unknown_baselines'])
        self.assertFalse(snapshot['performance_complete'])

    def test_prices_value_holdings_without_posting_and_do_not_look_ahead(self):
        self.operation('DEPOSIT', '2', '100', 1)
        PriceObservation.objects.create(user=self.user, asset=self.asset, date=date(2026, 9, 10), unit_price=Decimal('125'), source='September statement')
        PriceObservation.objects.create(user=self.user, asset=self.asset, date=date(2026, 10, 10), unit_price=Decimal('500'), source='October statement')
        counts = (Investment.objects.count(), BankMovement.objects.count())
        before = get_portfolio_valuation(self.user, date(2026, 9, 9))
        after = get_portfolio_valuation(self.user, date(2026, 9, 30))
        self.assertEqual(before['total'], Decimal('200'))
        self.assertTrue(before['missing_prices'])
        self.assertEqual((after['total'], after['unrealized_total']), (Decimal('250'), Decimal('50')))
        series = get_portfolio_series(self.user, 'BRL', [(2026, 8), (2026, 9)])
        self.assertEqual([row['total'] for row in series], [Decimal('0'), Decimal('250')])
        self.assertEqual(counts, (Investment.objects.count(), BankMovement.objects.count()))

    def test_price_create_edit_delete_and_owner_isolation(self):
        response = self.client.post(reverse('investments:create_price'), {'asset': self.asset.pk, 'date': '2026-09-10', 'unit_price': '125', 'source': 'Local statement'})
        self.assertEqual(response.status_code, 302)
        observation = PriceObservation.objects.get()
        self.assertEqual(self.client.get(reverse('investments:prices')).status_code, 200)
        self.assertEqual(self.client.post(reverse('investments:update_price', args=[observation.pk]), {'asset': self.asset.pk, 'date': '2026-09-10', 'unit_price': '130', 'source': 'Corrected statement'}).status_code, 302)
        other = get_user_model().objects.create_user(username='other-owner')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('investments:update_price', args=[observation.pk])).status_code, 404)
        invalid = PriceObservationForm({'asset': self.asset.pk, 'date': '2026-09-11', 'unit_price': '200', 'source': 'Wrong owner'}, user=other)
        self.assertFalse(invalid.is_valid())
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('investments:delete_price', args=[observation.pk])).status_code, 302)
        self.assertFalse(PriceObservation.objects.exists())

    def test_duplicate_quote_and_asset_evidence_cannot_be_reinterpreted(self):
        PriceObservation.objects.create(user=self.user, asset=self.asset, date=date(2026, 9, 10), unit_price=Decimal('125'), source='Local statement')
        duplicate = PriceObservationForm({'asset': self.asset.pk, 'date': '2026-09-10', 'unit_price': '130', 'source': 'Duplicate'}, user=self.user)
        self.assertFalse(duplicate.is_valid())
        self.assertIn('date', duplicate.errors)
        self.asset.currency = 'USD'
        with self.assertRaises(ValidationError):
            self.asset.full_clean()
        self.asset.currency = 'BRL'
        self.asset.valuation_mode = 'MONETARY'
        with self.assertRaises(ValidationError):
            self.asset.full_clean()

    def test_current_value_survives_missing_historical_result_fx(self):
        self.asset.currency = 'EUR'
        self.asset.save()
        self.operation('DEPOSIT', '2', '100', 1, cash_amount=Decimal('500'))
        PriceObservation.objects.create(user=self.user, asset=self.asset, date=date(2026, 9, 30), unit_price=Decimal('150'), source='Local statement')
        ExchangeRate.objects.create(user=self.user, from_currency='EUR', to_currency='BRL', rate=Decimal('2'), effective_date=date(2026, 9, 30))
        snapshot = get_portfolio_valuation(self.user, date(2026, 9, 30))
        self.assertEqual(snapshot['total'], Decimal('600'))
        self.assertFalse(snapshot['missing_currencies'])
        historical = get_portfolio_valuation(self.user, date(2026, 9, 30), historical=True)
        self.assertEqual(historical['total'], Decimal('600'))
        self.assertEqual(historical['performance_missing_currencies'], ['EUR'])
        self.assertFalse(historical['missing_currencies'])
        self.assertTrue(historical['complete'])
        self.assertFalse(historical['performance_complete'])

    def test_conversion_context_is_scoped_to_its_owner(self):
        other = get_user_model().objects.create_user(username='conversion-owner')
        with self.assertRaises(ValueError):
            get_portfolio_valuation(self.user, conversion=ConversionContext(other))

    def test_admin_bulk_delete_checks_the_remaining_sequence_and_cleans_cash(self):
        from django.contrib.admin import AdminSite
        from django.test import RequestFactory
        from investments.admin import InvestmentAdmin
        deposit = self.operation('DEPOSIT', '1', '100', 1)
        sale = self.operation('WITHDRAWAL', '1', '150', 2)
        request = RequestFactory().post('/admin/investments/investment/')
        request.user = self.user
        admin = InvestmentAdmin(Investment, AdminSite())
        self.assertTrue(admin.get_deleted_objects([deposit], request)[3])
        with self.assertRaises(ValidationError):
            admin.delete_queryset(request, Investment.objects.filter(pk=deposit.pk))
        self.assertEqual(BankMovement.objects.count(), 2)
        admin.delete_queryset(request, Investment.objects.filter(pk__in=[deposit.pk, sale.pk]))
        self.assertFalse(Investment.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_goal_reservations_preserve_currency_and_purpose_even_when_archived(self):
        from planning.models import FinancialGoal, GoalAllocation
        pot = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Goal pot', purpose='MONTHLY_CASH')
        cash = Asset.objects.create(user=self.user, name='Goal cash', code='GOAL', asset_class='LIQUIDITY', valuation_mode='MONETARY', currency='BRL', opening_balance=Decimal('100'), opening_product=pot)
        goal = FinancialGoal.objects.create(user=self.user, name='Archived goal', target_amount=Decimal('200'), currency='BRL', is_archived=True)
        GoalAllocation.objects.create(user=self.user, goal=goal, product=pot, asset=cash, amount=Decimal('10'))
        pot.purpose = 'INVESTMENT'
        with self.assertRaises(ValidationError):
            pot.full_clean()
        cash.currency = 'USD'
        with self.assertRaises(ValidationError):
            cash.full_clean()
        cash.currency = 'BRL'
        cash.valuation_mode = 'UNITS'
        cash.opening_balance = Decimal('0')
        cash.opening_product = None
        with self.assertRaises(ValidationError) as result:
            cash.full_clean()
        self.assertIn('valuation_mode', result.exception.message_dict)
