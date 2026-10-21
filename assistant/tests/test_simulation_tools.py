# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read-only monthly simulations on disposable synthetic financial records."""
from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import TestCase
from django.urls import resolve
from urllib.parse import urlsplit

from accounts.models import UserPreference
from assistant.simulation_tools import MAX_RESULT_BYTES, monthly_simulation_schema, simulate_month
from assistant.tests.support import make_finances, make_owner
from banking.models import CardInvoice, CreditCard, ExchangeRate, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from categories.models import Category
from planning.models import CategoryBudget
from sandbox.forms import SalarySandboxForm
from sandbox.models import ScenarioDraft
from sandbox.services import calculate_monthly_plan
from sandbox.views import _calculate_budget, _expense_forecast
from transactions.models import Transaction, TransactionSplit


class MonthlySimulationToolsTests(TestCase):
    def setUp(self):
        self.user, self.other = make_owner('simulation-owner'), make_owner('simulation-other')
        self.bank, self.account, self.category, self.item = make_finances(self.user)
        self.foreign_bank, self.foreign_account, self.foreign_category, self.foreign_item = make_finances(self.other, 'Foreign')

    def arguments(self, **changes):
        return {'planning_month': '2026-10', 'gross_salary': '6000.00', 'clt_dependents': 0,
                'clt_pension': '0.00', 'clt_transport': '0.00', 'clt_food': '0.00',
                'clt_health': '0.00', 'clt_other': '600.00', 'extra_expenses': [], 'category_reductions': [], **changes}

    def simulate(self, **changes):
        def only_reads(execute, sql, params, many, context):
            self.assertTrue(sql.lstrip().upper().startswith('SELECT '), sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(only_reads), patch('transactions.services.sync_user_ledger') as sync:
            result = simulate_month(self.user, self.arguments(**changes))
        sync.assert_not_called()
        self.assertLess(len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode()), MAX_RESULT_BYTES)
        self.assertFalse(result['saved'])
        return result

    def test_salary_other_payroll_deduction_and_registered_forecast_have_verified_amounts(self):
        result = self.simulate()
        self.assertTrue(result['complete'])
        self.assertEqual(result['currency'], 'BRL')  # User's presentation preference is USD.
        self.assertEqual(result['payroll'], {'gross': '6000.00', 'inss': '641.51', 'irrf': '385.10',
            'deductions': '600.00', 'net': '4373.39', 'irrf_base': '5358.49', 'irrf_method': 'legal'})
        self.assertEqual(result['forecast'], {'total': '12.34', 'count': 1, 'missing_currencies': []})
        self.assertEqual(result['budget'], {'net_income': '4373.39', 'registered_expenses': '12.34',
            'additional_expenses': '0.00', 'remaining': '4361.05'})
        self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_other_payroll_is_not_an_extra_category_and_does_not_reduce_irrf_base(self):
        payroll = self.simulate()
        extra = self.simulate(clt_other='0.00', extra_expenses=[{'title': 'Unrecorded expense', 'unit': 'currency', 'value': '600.00'}])
        self.assertEqual(extra['payroll']['net'], '4973.39')
        self.assertEqual(extra['payroll']['deductions'], '0.00')
        self.assertEqual(extra['payroll']['irrf'], payroll['payroll']['irrf'])
        self.assertEqual(extra['payroll']['irrf_base'], payroll['payroll']['irrf_base'])
        self.assertEqual(extra['budget']['additional_expenses'], '600.00')
        self.assertEqual(payroll['budget']['additional_expenses'], '0.00')
        self.assertEqual(extra['budget']['remaining'], payroll['budget']['remaining'])

    def test_extra_percentage_uses_gross_salary_and_negative_remaining_is_preserved(self):
        result = self.simulate(extra_expenses=[{'title': 'Reserve', 'unit': 'percent', 'value': '10.00'}])
        self.assertEqual(result['extra_expenses'][0]['monthly_amount'], '600.00')
        self.assertEqual(result['budget']['remaining'], '3761.05')
        result = self.simulate(extra_expenses=[{'title': 'Expense', 'unit': 'currency', 'value': '9000.00'}])
        self.assertEqual(result['budget']['remaining'], '-4638.95')

    def test_no_preference_or_financial_rows_are_created_during_simulation(self):
        UserPreference.objects.filter(user=self.user).delete()
        self.simulate()
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())
        self.assertEqual(ScenarioDraft.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 2)
        self.assertEqual(CardInvoice.objects.count(), 0)

    def test_tool_aggregate_does_not_return_private_titles_notes_or_instrument_identity(self):
        result = self.simulate()
        serialized = json.dumps(result)
        for value in ('Owned purchase', 'Owned account', 'Owned bank', 'Foreign', 'DO NOT COPY PRIVATE NOTES',
                      'DO NOT COPY RAW DESCRIPTION'):
            self.assertNotIn(value, serialized)
        self.assertEqual(result['forecast']['total'], '12.34')

    def test_missing_fx_is_explicit_and_foreign_user_rates_do_not_complete_it(self):
        self.account.currency = 'USD'
        self.account.save(update_fields=['currency'])
        ExchangeRate.objects.create(user=self.other, from_currency='USD', to_currency='BRL', rate='5.00',
                                     effective_date=date(2026, 1, 1))
        result = self.simulate()
        self.assertFalse(result['complete'])
        self.assertEqual(result['error'], 'missing_exchange_rate')
        self.assertIsNone(result['forecast']['total'])
        self.assertEqual(result['forecast']['missing_currencies'], ['USD'])
        self.assertIsNone(result['budget'])
        self.assertIsNone(result['payroll'])

    def test_owned_fx_uses_read_only_capture_date_and_does_not_mix_native_amounts(self):
        self.account.currency = 'USD'
        self.account.save(update_fields=['currency'])
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='5.00',
                                     effective_date=date(2026, 1, 1))
        result = self.simulate()
        self.assertEqual(result['forecast']['total'], '61.70')
        self.assertEqual(result['budget']['remaining'], '4311.69')
        self.assertEqual(result['currency'], 'BRL')

    def test_installments_follow_statement_month_and_invoice_is_not_added_twice(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Private card', closing_day=24, due_day=1)
        Transaction.objects.create(user=self.user, title='Private installments', amount='100.00', category=self.category,
            transaction_type='EXPENSE', payment_channel='CREDIT_CARD', credit_card=card, installments=3, date=date(2026, 8, 25))
        CardInvoice.objects.create(user=self.user, card=card, reference_month=date(2026, 10, 1),
                                   due_date=date(2026, 11, 1), amount='999.00')
        result = self.simulate()
        self.assertEqual(result['forecast']['total'], '45.67')
        self.assertEqual(result['forecast']['count'], 2)
        november = self.simulate(planning_month='2026-11')
        self.assertEqual(november['forecast']['total'], '33.33')
        self.assertEqual(CardInvoice.objects.get().amount, Decimal('999.00'))

    def test_recurrences_and_category_splits_remain_one_economic_expense(self):
        other_category = Category.objects.create(user=self.user, name='Split category')
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount='6.00')
        TransactionSplit.objects.create(transaction=self.item, category=other_category, amount='6.34')
        Transaction.objects.create(user=self.user, title='Private recurrence', amount='80.00', category=self.category,
            transaction_type='EXPENSE', payment_channel='ACCOUNT', bank_account=self.account,
            is_fixed=True, fixed_until=date(2026, 11, 1), date=date(2026, 9, 5))
        result = self.simulate()
        self.assertEqual(result['forecast']['total'], '92.34')
        self.assertEqual(result['forecast']['count'], 2)
        self.assertEqual(self.simulate(planning_month='2026-11')['forecast']['total'], '80.00')
        self.assertEqual(self.simulate(planning_month='2026-12')['forecast']['total'], '0.00')

    def test_canonical_workspace_calculation_is_shared_and_unchanged(self):
        self.assertIs(_calculate_budget, calculate_monthly_plan)
        args = self.arguments()
        form = SalarySandboxForm({name: value for name, value in args.items() if name != 'extra_expenses'})
        _snapshot, forecast = _expense_forecast(self.user, date(2026, 10, 1))
        canonical = _calculate_budget(form, forecast)
        self.assertEqual(self.simulate()['budget']['remaining'], format(canonical['budget'].remaining, '.2f'))

    def test_category_other_cut_changes_only_hypothetical_expenses_not_payroll_or_limits(self):
        self.category.name = 'Outros'
        self.category.save(update_fields=['name'])
        self.item.amount = Decimal('1000.00')
        self.item.save(update_fields=['amount'])
        limit = CategoryBudget.objects.create(user=self.user, category=self.category,
            month=date(2026, 10, 1), currency='BRL', amount='1500.00')
        item_before = Transaction.objects.filter(pk=self.item.pk).values().get()
        limit_before = CategoryBudget.objects.filter(pk=limit.pk).values().get()
        original = self.simulate(clt_other='0.00')
        result = self.simulate(clt_other='0.00', category_reductions=[{'category_id': self.category.pk, 'amount': '600.00'}])
        self.assertEqual(result['payroll'], original['payroll'])
        self.assertEqual(result['payroll']['net'], '4973.39')
        self.assertEqual(result['payroll']['deductions'], '0.00')
        self.assertEqual(result['forecast']['total'], '1000.00')
        self.assertEqual(result['forecast']['adjusted_total'], '400.00')
        self.assertEqual(result['forecast']['reduction_total'], '600.00')
        self.assertEqual(result['budget']['remaining_before_reductions'], original['budget']['remaining'])
        self.assertEqual(result['budget']['registered_expenses'], '400.00')
        self.assertEqual(result['budget']['remaining'], '4573.39')
        self.assertEqual(result['category_reductions'], [{'category_id': self.category.pk, 'category': 'Outros',
            'includes_descendants': True, 'before': '1000.00', 'reduction': '600.00', 'after': '400.00'}])
        self.assertEqual(Transaction.objects.filter(pk=self.item.pk).values().get(), item_before)
        self.assertEqual(CategoryBudget.objects.filter(pk=limit.pk).values().get(), limit_before)
        self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_parent_category_cut_includes_descendants_split_allocations_and_recurrences_once(self):
        child = Category.objects.create(user=self.user, name='Child', parent_category=self.category)
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount='6.00')
        TransactionSplit.objects.create(transaction=self.item, category=child, amount='6.34')
        Transaction.objects.create(user=self.user, title='Private recurring category expense', amount='80.00', category=child,
            transaction_type='EXPENSE', payment_channel='ACCOUNT', bank_account=self.account,
            is_fixed=True, fixed_until=date(2026, 11, 1), date=date(2026, 9, 5))
        result = self.simulate(category_reductions=[{'category_id': self.category.pk, 'amount': '90.00'}])
        self.assertEqual(result['forecast']['total'], '92.34')
        self.assertEqual(result['forecast']['adjusted_total'], '2.34')
        self.assertEqual(result['category_reductions'][0]['before'], '92.34')
        self.assertEqual(result['category_reductions'][0]['after'], '2.34')
        november = self.simulate(planning_month='2026-11', category_reductions=[{'category_id': child.pk, 'amount': '80.00'}])
        self.assertEqual(november['forecast']['adjusted_total'], '0.00')
        self.assertEqual(november['budget']['remaining'], november['payroll']['net'])

    def test_overlap_duplicate_foreign_income_and_excessive_category_cuts_are_rejected(self):
        child = Category.objects.create(user=self.user, name='Child', parent_category=self.category)
        income = Category.objects.create(user=self.user, name='Income', transaction_type='INCOME')
        cut = {'category_id': self.category.pk, 'amount': '1.00'}
        cases = [([cut, cut], 'overlapping_category_reductions'),
                 ([cut, {'category_id': child.pk, 'amount': '1.00'}], 'overlapping_category_reductions'),
                 ([{'category_id': child.pk, 'amount': '1.00'}, cut], 'overlapping_category_reductions'),
                 ([{'category_id': self.foreign_category.pk, 'amount': '1.00'}], 'invalid_category_reference'),
                 ([{'category_id': 9223372036854775807, 'amount': '1.00'}], 'invalid_category_reference'),
                 ([{'category_id': income.pk, 'amount': '1.00'}], 'invalid_category_reference'),
                 ([{'category_id': self.category.pk, 'amount': '12.35'}], 'category_reduction_exceeds_forecast')]
        for cuts, error in cases:
            with self.subTest(cuts=cuts):
                result = self.simulate(category_reductions=cuts)
                self.assertFalse(result['complete'])
                self.assertEqual(result['error'], error)
                self.assertIsNone(result['budget'])
                self.assertNotIn('adjusted_total', result['forecast'])
                self.assertNotIn('Foreign', json.dumps(result))

    def test_disjoint_category_cuts_and_additional_expenses_reconcile_to_the_original(self):
        second = Category.objects.create(user=self.user, name='Disjoint')
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount='6.00')
        TransactionSplit.objects.create(transaction=self.item, category=second, amount='6.34')
        result = self.simulate(extra_expenses=[{'title': 'Extra', 'unit': 'currency', 'value': '2.00'}],
            category_reductions=[{'category_id': self.category.pk, 'amount': '3.00'}, {'category_id': second.pk, 'amount': '4.00'}])
        self.assertEqual(result['forecast']['adjusted_total'], '5.34')
        self.assertEqual(result['forecast']['reduction_total'], '7.00')
        self.assertEqual(result['budget']['additional_expenses'], '2.00')
        self.assertEqual(result['budget']['remaining'], '4366.05')
        self.assertEqual(result['budget']['remaining_before_reductions'], '4359.05')

    def test_installment_category_replay_uses_statement_month_and_remaining_cent_capacities(self):
        second = Category.objects.create(user=self.user, name='Installment split')
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Private card', closing_day=24, due_day=1)
        item = Transaction.objects.create(user=self.user, title='Tiny split installments', amount='0.05', category=self.category,
            transaction_type='EXPENSE', payment_channel='CREDIT_CARD', credit_card=card, installments=3, date=date(2026, 8, 25))
        TransactionSplit.objects.create(transaction=item, category=self.category, amount='0.02')
        TransactionSplit.objects.create(transaction=item, category=second, amount='0.03')
        october = self.simulate(category_reductions=[{'category_id': self.category.pk, 'amount': '0.01'}])
        self.assertEqual(october['category_reductions'][0]['before'], '12.35')
        self.assertEqual(october['forecast']['total'], '12.35')
        self.assertEqual(october['forecast']['adjusted_total'], '12.34')
        unavailable = self.simulate(category_reductions=[{'category_id': second.pk, 'amount': '0.01'}])
        self.assertEqual(unavailable['error'], 'category_reduction_exceeds_forecast')
        november = self.simulate(planning_month='2026-11', category_reductions=[{'category_id': second.pk, 'amount': '0.01'}])
        self.assertEqual(november['category_reductions'][0]['before'], '0.01')
        self.assertEqual(november['forecast']['adjusted_total'], '0.00')

    def test_fx_split_cents_close_to_converted_event_and_missing_fx_blocks_cuts(self):
        self.account.currency = 'USD'
        self.account.save(update_fields=['currency'])
        self.item.amount = Decimal('0.02')
        self.item.save(update_fields=['amount'])
        second = Category.objects.create(user=self.user, name='FX split')
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount='0.01')
        TransactionSplit.objects.create(transaction=self.item, category=second, amount='0.01')
        cuts = [{'category_id': self.category.pk, 'amount': '0.02'}, {'category_id': second.pk, 'amount': '0.01'}]
        missing = self.simulate(category_reductions=cuts)
        self.assertEqual(missing['error'], 'missing_exchange_rate')
        self.assertNotIn('adjusted_total', missing['forecast'])
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='1.50',
                                     effective_date=date(2026, 1, 1))
        result = self.simulate(category_reductions=cuts)
        self.assertEqual([row['before'] for row in result['category_reductions']], ['0.02', '0.01'])
        self.assertEqual(result['forecast']['total'], '0.03')
        self.assertEqual(result['forecast']['adjusted_total'], '0.00')
        self.assertEqual(result['budget']['remaining'], result['payroll']['net'])

    def test_iof_uses_its_linked_category_once_and_points_remain_uncategorized(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Private rewards')
        iof_category = Category.objects.create(user=self.user, name='IOF')
        redemption = RewardRedemption.objects.create(user=self.user, program=program, points='10.00',
            target_account=self.account, target_amount='1.00', iof_amount='5.00', iof_account=self.account, date=date(2026, 10, 10))
        Transaction.objects.create(user=self.user, title='IOF on reward redemption', amount='5.00', category=iof_category,
            reward_redemption=redemption, transaction_type='EXPENSE', payment_channel='ACCOUNT',
            bank_account=self.account, date=date(2026, 10, 10))
        LoyaltyEntry.objects.create(user=self.user, program=program, kind='PURCHASE', direction='CREDIT',
            amount='100.00', cash_amount='20.00', funding_account=self.account, date=date(2026, 10, 10))
        result = self.simulate(category_reductions=[{'category_id': iof_category.pk, 'amount': '3.00'}])
        self.assertTrue(result['complete'])
        self.assertEqual(result['forecast']['count'], 3)
        self.assertEqual(result['forecast']['total'], '37.34')
        self.assertEqual(result['forecast']['adjusted_total'], '34.34')
        self.assertEqual(result['forecast']['uncategorized_points_expenses'], '20.00')
        self.assertEqual(result['category_reductions'][0]['before'], '5.00')
        self.assertEqual(result['budget']['remaining'], '4339.05')
        self.assertEqual(Transaction.objects.filter(reward_redemption=redemption).count(), 1)

    def test_unlinked_legacy_iof_or_changed_fx_fails_closed_instead_of_guessing_categories(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Legacy rewards')
        redemption = RewardRedemption.objects.create(user=self.user, program=program, points='10.00',
            target_account=self.account, target_amount='1.00', iof_amount='5.00', iof_account=self.account, date=date(2026, 10, 10))
        result = self.simulate(category_reductions=[{'category_id': self.category.pk, 'amount': '1.00'}])
        self.assertEqual(result['error'], 'category_mapping_unavailable')
        self.assertEqual(result['forecast']['total'], '17.34')
        self.assertIsNone(result['budget'])
        self.assertFalse(Transaction.objects.filter(reward_redemption=redemption).exists())
        redemption.delete()
        with patch('assistant.simulation_tools.convert', return_value=Decimal('2.00')):
            self.assertEqual(self.simulate(category_reductions=[{'category_id': self.category.pk, 'amount': '1.00'}])['error'],
                'category_mapping_unavailable')

    def test_older_local_arguments_can_omit_category_reductions(self):
        arguments = self.arguments()
        del arguments['category_reductions']
        with patch.object(self, 'arguments', return_value=arguments):
            result = self.simulate()
        self.assertTrue(result['complete'])
        self.assertEqual(result['category_reductions'], [])
        self.assertEqual(result['budget']['remaining'], '4361.05')

    def test_schema_dates_tax_provenance_and_local_references_are_explicit(self):
        schema = monthly_simulation_schema()
        self.assertEqual(schema['name'], 'simulate_month')
        self.assertEqual(set(schema['parameters']['required']), set(self.arguments()))
        self.assertFalse(schema['parameters']['additionalProperties'])
        result = self.simulate(planning_month='2027-01')
        self.assertEqual(result['tax_rules']['year'], 2026)
        self.assertEqual(len(result['tax_rules']['source_urls']), 2)
        self.assertEqual(result['month_basis'], 'reference_month')
        self.assertIn('does not assert the tax table for another year', result['warnings'][0])
        self.assertTrue(result['captured_at'])
        date.fromisoformat(result['cutoff'])
        for reference in result['references']:
            self.assertFalse(urlsplit(reference['url']).netloc)
            resolve(urlsplit(reference['url']).path)

    def test_invalid_input_is_bounded_and_never_reads_financial_sources(self):
        cases = [{'gross_salary': '0.00'}, {'gross_salary': 'NaN'}, {'gross_salary': '1e1000000'},
                 {'gross_salary': 6000}, {'clt_other': '600.001'}, {'clt_other': '-1.00'},
                 {'clt_dependents': True}, {'clt_dependents': 100}, {'planning_month': '2026-13'},
                 {'planning_month': '1900-01'}, {'user_id': self.other.pk},
                 {'extra_expenses': [{'title': 'Bad percentage', 'unit': 'percent', 'value': '101.00'}]},
                 {'extra_expenses': [{'title': 'Bad', 'unit': 'currency', 'value': '1.00'}] * 21},
                 {'category_reductions': {}},
                 {'category_reductions': [{'category_id': True, 'amount': '1.00'}]},
                 {'category_reductions': [{'category_id': 2**64, 'amount': '1.00'}]},
                 {'category_reductions': [{'category_id': self.category.pk, 'amount': '0.00'}]},
                 {'category_reductions': [{'category_id': self.category.pk, 'amount': '-1.00'}]},
                 {'category_reductions': [{'category_id': self.category.pk, 'amount': '1e100'}]},
                 {'category_reductions': [{'category_id': self.category.pk, 'amount': 1}]},
                 {'category_reductions': [{'category_id': self.category.pk, 'amount': '1.00', 'user_id': self.user.pk}]},
                 {'category_reductions': [{'category_id': self.category.pk, 'amount': '1.00'}] * 21}]
        with patch('assistant.simulation_tools.commitment_snapshot') as snapshot:
            for changes in cases:
                with self.subTest(changes=changes):
                    result = self.simulate(**changes)
                    self.assertEqual(result['error'], 'invalid_parameters')
            snapshot.assert_not_called()

    def test_disabled_and_anonymous_users_cannot_read_forecast(self):
        with patch('assistant.simulation_tools.commitment_snapshot') as snapshot:
            result = simulate_month(AnonymousUser(), self.arguments())
            self.assertEqual(result['error'], 'unauthorized')
            self.user.__class__.objects.filter(pk=self.user.pk).update(is_active=False)
            self.assertEqual(self.simulate()['error'], 'unauthorized')
            snapshot.assert_not_called()

    def test_snapshot_capacity_failure_and_long_output_fail_closed_without_saving(self):
        with patch('sandbox.planning.MAX_COMMITMENTS', 0):
            self.assertEqual(self.simulate()['error'], 'forecast_unavailable')
        result = self.simulate(extra_expenses=[{'title': '😀' * 80, 'unit': 'currency', 'value': '1.00'}] * 20)
        self.assertEqual(result['error'], 'limit_exceeded')
        self.assertEqual(ScenarioDraft.objects.count(), 0)
