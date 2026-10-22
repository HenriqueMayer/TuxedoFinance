# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owned consultation uses canonical read calculations and never initializes data."""
from datetime import date
from decimal import Decimal
import json
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import UserPreference
from assistant.action_service import ActionError
from assistant.consultation import AREAS, MAX_RESPONSE_BYTES, read_financial_data
from assistant.tests.support import make_finances, make_owner
from banking.models import BankAccount, BankMovement, CardInvoice, CreditCard, DebitCard, ExchangeRate, InvoicePayment, LoyaltyProgram
from banking.services import ConversionContext
from investments.models import Asset, InvestmentProduct, PositionPlanningSetting
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation
from planning.monthly import monthly_outlook
from sandbox.models import ScenarioDraft
from transactions.models import Transaction


TODAY = date(2026, 10, 20)


class ConsultationTests(TestCase):
    def setUp(self):
        self.user, self.other = make_owner('consult-owner'), make_owner('consult-other')
        self.bank, self.account, self.category, self.item = make_finances(self.user)
        self.private_bank, self.private_account, self.private_category, self.private_item = make_finances(self.other, 'PRIVATE')
        self.credit = CreditCard.objects.create(user=self.user, account=self.account, name='Owned credit', closing_day=20, due_day=1)
        self.private_credit = CreditCard.objects.create(user=self.other, account=self.private_account,
            name='PRIVATE credit', closing_day=20, due_day=1)
        self.invoice = CardInvoice.objects.create(user=self.user, card=self.credit,
            reference_month=date(2026, 10, 1), due_date=date(2026, 11, 1), amount='25.00')
        self.private_invoice = CardInvoice.objects.create(user=self.other, card=self.private_credit,
            reference_month=date(2026, 10, 1), due_date=date(2026, 11, 1), amount='999.00')
        self.fx = ExchangeRate.objects.create(user=self.user, from_currency='BRL', to_currency='USD',
            rate='0.20000000', effective_date=date(2026, 10, 1))
        self.program = LoyaltyProgram.objects.create(user=self.user, bank=self.bank, name='Owned program')
        self.goal = FinancialGoal.objects.create(user=self.user, name='Owned goal', target_amount='100.00', currency='BRL')
        self.private_goal = FinancialGoal.objects.create(user=self.other, name='PRIVATE goal', target_amount='999.00', currency='BRL')
        self.budget = CategoryBudget.objects.create(user=self.user, category=self.category,
            month=date(2026, 10, 1), currency='BRL', amount='100.00')
        self.product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Owned position')
        self.asset = Asset.objects.create(user=self.user, name='Owned asset', code='OWN', currency='BRL',
            asset_class='LIQUIDITY', valuation_mode='MONETARY', opening_balance='50.00', opening_product=self.product,
            opening_date=date(2026, 10, 1))
        self.draft = ScenarioDraft.objects.create(user=self.user, name='Owned salary draft', kind='budget', payload={
            'schema_version': 1, 'calculation_version': 2, 'tax_rule_year': 2026, 'complete': True,
            'input_format': {'date_order': 'DMY', 'month': 'YYYY-MM', 'decimal': '.'},
            'inputs': {'planning_month': ['2026-10'], 'gross_salary': ['5000.00']},
            'snapshot': {'user_id': self.user.pk, 'start_month': '2026-10', 'currency': 'BRL',
                'captured_at': '2026-10-10T12:00:00Z', 'month_basis': 'reference_month', 'rows': [{
                    'key': f'transaction:{self.item.pk}:once', 'label': 'Captured owned purchase',
                    'amount': '12.34', 'native_amount': '12.34', 'currency': 'BRL', 'included': True,
                    'payment_date': '2026-10-10', 'reference_month': '2026-10', 'override': ''}]}})
        self.private_draft = ScenarioDraft.objects.create(user=self.other, name='PRIVATE draft', kind='yield', payload={})
        self.clock = patch('assistant.consultation.timezone.localdate', return_value=TODAY)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def args(self, area='accounts', **changes):
        result = {'area': area, 'month': '2026-10', 'query': '', 'record_id': None, 'page': 0}
        result.update(changes)
        return result

    def read(self, area='accounts', **changes):
        return read_financial_data(self.user, self.args(area, **changes))

    def assert_error(self, code, callback, *args, **kwargs):
        with self.assertRaises(ActionError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_every_area_returns_serializable_owned_evidence_without_any_sql_write(self):
        UserPreference.objects.filter(user=self.user).delete()
        with patch.object(UserPreference, 'for_user', side_effect=AssertionError('No preference initialization')), \
                patch('transactions.services.sync_user_ledger', side_effect=AssertionError('No synchronization')):
            for area in AREAS:
                with self.subTest(area=area), CaptureQueriesContext(connection) as captured:
                    result = self.read(area)
                    encoded = json.dumps(result, ensure_ascii=True).encode()
                self.assertLessEqual(len(encoded), MAX_RESPONSE_BYTES)
                self.assertEqual(result['area'], area)
                self.assertEqual(result['base_currency'], 'BRL')
                self.assertEqual(result['cutoff'], '2026-10-20')
                self.assertFalse(result['saved'])
                self.assertNotIn('PRIVATE', encoded.decode())
                self.assertFalse(any(re.match(r'\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|REPLACE)\b', row['sql'], re.I)
                                     for row in captured.captured_queries), captured.captured_queries)
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())

    def test_record_ids_never_resolve_another_user_across_all_record_areas(self):
        private_product = InvestmentProduct.objects.create(user=self.other, bank=self.private_bank, name='PRIVATE position')
        private_asset = Asset.objects.create(user=self.other, name='PRIVATE asset', code='PRIVATE', currency='BRL',
            asset_class='LIQUIDITY', valuation_mode='MONETARY', opening_product=private_product)
        private_budget = CategoryBudget.objects.create(user=self.other, category=self.private_category,
            month=date(2026, 10, 1), currency='BRL', amount='1.00')
        private_rate = ExchangeRate.objects.create(user=self.other, from_currency='BRL', to_currency='USD',
            rate='0.10000000', effective_date=date(2026, 10, 1))
        private_program = LoyaltyProgram.objects.create(user=self.other, name='PRIVATE loyalty')
        cases = {'accounts': self.private_account.pk, 'cards': self.private_credit.pk,
            'invoices': self.private_invoice.pk, 'transactions': self.private_item.pk,
            'categories': self.private_category.pk, 'planning': private_budget.pk, 'goals': self.private_goal.pk,
            'investments': private_asset.pk, 'reports': self.private_category.pk,
            'exchange_rates': private_rate.pk, 'loyalty': private_program.pk, 'saved_scenarios': self.private_draft.pk}
        for area, pk in cases.items():
            with self.subTest(area=area):
                self.assert_error('invalid_reference', self.read, area, record_id=pk)

    def test_card_id_selects_an_owned_credit_even_without_any_debit_record(self):
        result = self.read('cards', record_id=self.credit.pk)
        self.assertEqual([(row['kind'], row['id']) for row in result['items']], [('credit', self.credit.pk)])

    def test_card_id_selects_an_owned_debit_even_without_a_matching_credit_id(self):
        debit = DebitCard.objects.create(user=self.user, account=self.account, name='Owned debit', pk=5000)
        result = self.read('cards', record_id=debit.pk)
        self.assertEqual([(row['kind'], row['id']) for row in result['items']], [('debit', debit.pk)])

    def test_card_pagination_is_one_bounded_stable_sequence_across_both_kinds(self):
        for index in range(24):
            CreditCard.objects.create(user=self.user, account=self.account, name=f'Credit {index}', closing_day=10, due_day=20)
        for index in range(3):
            DebitCard.objects.create(user=self.user, account=self.account, name=f'Debit {index}')
        first, second = self.read('cards'), self.read('cards', page=1)
        self.assertEqual(len(first['items']), 20)
        self.assertTrue(first['has_more'])
        self.assertEqual(len(second['items']), 8)
        self.assertFalse(second['has_more'])
        identifiers = [(row['kind'], row['id']) for row in first['items'] + second['items']]
        self.assertEqual(len(set(identifiers)), 28)

    def test_query_and_page_narrow_owned_records_without_duplicate_rows(self):
        for index in range(25):
            BankAccount.objects.create(user=self.user, bank=self.bank, name=f'Filtered account {index:02}', currency='BRL')
        first, second = self.read('accounts', query='Filtered'), self.read('accounts', query='Filtered', page=1)
        self.assertEqual(len(first['items']), 20)
        self.assertEqual(len(second['items']), 5)
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertFalse({row['id'] for row in first['items']} & {row['id'] for row in second['items']})

    def test_unicode_references_cannot_break_the_whole_response_size_bound(self):
        for index in range(25):
            BankAccount.objects.create(user=self.user, bank=self.bank, name='界' * 160 + str(index), currency='BRL')
        result = self.read('accounts', query='界')
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=True).encode()), MAX_RESPONSE_BYTES)
        self.assertTrue(result['truncated'])
        self.assertTrue(result['has_more'])
        self.assertTrue(any('size limit' in text for text in result['warnings']))

    def test_account_balance_uses_cutoff_and_retains_native_currency_and_zero(self):
        BankMovement.objects.create(user=self.user, account=self.account, direction='CREDIT', kind='INCOME',
            amount='100.00', effective_date=date(2026, 10, 25))
        current = self.read('accounts', record_id=self.account.pk)['items'][0]
        self.assertEqual(Decimal(current['balance']), Decimal('87.66'))
        self.assertEqual(current['currency'], 'BRL')
        past = self.read('accounts', month='2026-09', record_id=self.account.pk)
        self.assertEqual(past['cutoff'], '2026-09-30')
        self.assertEqual(Decimal(past['items'][0]['balance']), Decimal('0.00'))
        self.assertEqual(self.read('accounts', month='2026-11')['cutoff'], '2026-10-20')

    def test_transactions_keep_source_and_month_allocations_distinct_without_copying_notes_by_default(self):
        self.item.payment_channel = 'CREDIT_CARD'
        self.item.bank_account = None
        self.item.credit_card = self.credit
        self.item.amount = Decimal('120.00')
        self.item.installments = 3
        self.item.save()
        result = self.read('transactions', month='2026-11')
        row = result['items'][0]
        self.assertEqual(row['source_amount'], '120.00')
        self.assertEqual(row['month_amount'], '40.00')
        self.assertEqual(row['currency'], 'BRL')
        self.assertNotIn('notes', row)
        self.assertTrue(any('scheduled economic' in text for text in result['warnings']))
        selected = self.read('transactions', record_id=self.item.pk)
        self.assertEqual(selected['items'][0]['notes'], 'DO NOT COPY PRIVATE NOTES')

    def test_reports_expose_canonical_category_total_and_realized_vs_remaining_flow(self):
        Transaction.objects.create(user=self.user, category=self.category, title='Future owned expense', amount='20.00',
            transaction_type='EXPENSE', payment_channel='ACCOUNT', bank_account=self.account, date=date(2026, 10, 25))
        report = self.read('reports')
        self.assertEqual(report['period_kind'], 'current')
        self.assertEqual(report['period_cutoff'], '2026-10-20')
        self.assertEqual(Decimal(report['items'][0]['total']), Decimal('2.468'))
        self.assertEqual(Decimal(report['performance']['through_cutoff']['expenses']), Decimal('2.468'))
        self.assertEqual(Decimal(report['performance']['remaining']['expenses']), Decimal('4.00'))
        self.assertEqual(Decimal(report['performance']['full_month']['expenses']), Decimal('6.468'))
        future = self.read('reports', month='2026-11')
        self.assertEqual(future['period_kind'], 'future')
        self.assertIsNone(future['period_cutoff'])

    def test_missing_fx_is_exposed_as_partial_instead_of_a_complete_zero_report(self):
        self.fx.delete()
        report = self.read('reports')
        self.assertIn('BRL', report['missing_currencies'])
        planning = self.read('planning')
        self.assertFalse(planning['outlook']['complete'])
        self.assertIn('BRL', planning['outlook']['missing_currencies'])
        investments = self.read('investments')
        self.assertFalse(investments['valuation']['complete'])
        self.assertEqual(Decimal(investments['items'][0]['valuation']), Decimal('50.00'))
        self.assertIsNone(investments['items'][0]['base_value'])

    def test_selected_invoice_can_be_read_outside_the_default_month_and_labels_today_remainder(self):
        CardInvoice.objects.filter(pk=self.invoice.pk).update(reference_month=date(2026, 9, 1), manual_settlement=True)
        InvoicePayment.objects.create(user=self.user, invoice=self.invoice, account=self.account, amount='5.00', date=date(2026, 10, 1))
        result = self.read('invoices', record_id=self.invoice.pk)
        self.assertEqual(result['items'][0]['reference_month'], '2026-09-01')
        self.assertEqual(result['items'][0]['remaining_today'], '20.00')

    def test_selected_archived_goal_remains_owned_readable_and_list_omits_it(self):
        self.goal.is_archived = True
        self.goal.save(update_fields=['is_archived'])
        self.assertEqual(self.read('goals')['items'], [])
        selected = self.read('goals', record_id=self.goal.pk)['items'][0]
        self.assertTrue(selected['archived'])
        self.assertEqual(selected['progress'], '0.00')

    def test_saved_scenario_list_omits_payload_but_explicit_read_returns_only_canonical_inputs(self):
        payload = self.draft.payload
        payload['api_key'] = 'SECRET-CREDENTIAL'
        payload['inputs']['password'] = ['SECRET-CREDENTIAL']
        payload['input_format']['token'] = 'SECRET-CREDENTIAL'
        payload['snapshot']['rows'][0]['access_token'] = 'SECRET-CREDENTIAL'
        self.draft.save(update_fields=['payload'])
        self.assertNotIn('payload', self.read('saved_scenarios')['items'][0])
        selected = self.read('saved_scenarios', record_id=self.draft.pk)['items'][0]['payload']
        self.assertEqual(selected['inputs']['gross_salary'], ['5000.00'])
        self.assertEqual(selected['input_format']['date_order'], 'DMY')
        self.assertTrue(selected['snapshot']['captured'])
        self.assertEqual(selected['snapshot']['captured_at'], '2026-10-10T12:00:00Z')
        self.assertEqual(selected['snapshot']['rows'][0]['native_amount'], '12.34')
        self.assertNotIn('SECRET-CREDENTIAL', str(selected))

    def test_saved_snapshot_cannot_claim_another_owner_or_unchecked_nested_payload(self):
        self.draft.payload['snapshot']['user_id'] = self.other.pk
        self.draft.save(update_fields=['payload'])
        self.assert_error('inconsistent_ownership', self.read, 'saved_scenarios', record_id=self.draft.pk)
        # Merely listing names never opens a saved financial snapshot.
        self.assertEqual(len(self.read('saved_scenarios')['items']), 1)

    def test_large_saved_snapshot_retains_bounded_explicitly_partial_detail(self):
        original = self.draft.payload['snapshot']['rows'][0]
        self.draft.payload['snapshot']['rows'] = [{**original, 'label': '界' * 2000} for _ in range(100)]
        self.draft.save(update_fields=['payload'])
        result = self.read('saved_scenarios', record_id=self.draft.pk)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=True).encode()), MAX_RESPONSE_BYTES)
        self.assertTrue(result['truncated'])
        selected = result['items'][0]['payload']
        self.assertEqual(selected['inputs']['gross_salary'], ['5000.00'])
        self.assertTrue(selected['snapshot']['has_more'])

    def test_malformed_direct_ownership_stops_before_any_foreign_data_is_returned(self):
        BankAccount.objects.create(user=self.user, bank=self.private_bank, name='Invalid foreign bank link', currency='BRL')
        for area in ('accounts', 'reports', 'planning'):
            self.assert_error('inconsistent_ownership', self.read, area)

    def test_foreign_movements_on_an_owned_account_and_foreign_allocations_on_an_owned_goal_are_rejected(self):
        movement = BankMovement.objects.create(user=self.other, account=self.account, amount='999.00',
            effective_date=TODAY, direction='CREDIT', kind='INCOME')
        self.assert_error('inconsistent_ownership', self.read, 'accounts')
        movement.delete()
        GoalAllocation.objects.create(user=self.other, goal=self.goal, bank_account=self.private_account, amount='99.00')
        self.assert_error('inconsistent_ownership', self.read, 'goals')

    def test_malformed_planning_setting_cannot_influence_aggregate_ownership(self):
        product = InvestmentProduct.objects.create(user=self.other, bank=self.private_bank, name='PRIVATE pot', purpose='MONTHLY_CASH')
        PositionPlanningSetting.objects.create(user=self.user, product=product, asset=self.asset)
        self.assert_error('inconsistent_ownership', self.read, 'planning')

    def test_anonymous_inactive_and_malformed_requests_are_rejected(self):
        from django.contrib.auth.models import AnonymousUser
        self.assert_error('unauthorized', read_financial_data, AnonymousUser(), self.args())
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        self.assert_error('unauthorized', self.read)
        for changes in ({'area': 'sql'}, {'month': '2026-13'}, {'month': '20/10/2026'},
                        {'month': '1900-01'}, {'record_id': True}, {'query': 'x' * 121},
                        {'page': True}, {'page': -1}, {'page': 10001}):
            self.assert_error('invalid_parameters', self.read, **changes)

    def test_explicit_conversion_context_is_reused_without_initializing_preferences(self):
        UserPreference.objects.filter(user=self.user).delete()
        conversion = ConversionContext(self.user, base_currency='USD')
        with patch.object(UserPreference, 'for_user', side_effect=AssertionError('No preference creation')), \
                CaptureQueriesContext(connection) as captured:
            result = monthly_outlook(self.user, date(2026, 10, 1), conversion=conversion)
        self.assertEqual(result['base_currency'], 'USD')
        self.assertFalse(any(re.match(r'\s*(INSERT|UPDATE|DELETE)\b', row['sql'], re.I) for row in captured.captured_queries))
        self.assert_error('invalid_reference', self.read, 'accounts', record_id=999999)
        with self.assertRaises(ValueError):
            monthly_outlook(self.other, date(2026, 10, 1), conversion=conversion)
