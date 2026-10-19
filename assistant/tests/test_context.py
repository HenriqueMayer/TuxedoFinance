# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
import json
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserPreference
from assistant.context import MAX_ROWS, collect_context, normalize_location
from assistant.tests.support import make_finances, make_owner
from banking.models import BankAccount, BankMovement
from transactions.models import Transaction, TransactionSplit


class AssistantFinancialContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_owner('context-owner')
        cls.other = make_owner('context-other')
        cls.bank, cls.account, cls.category, cls.item = make_finances(cls.user)
        cls.foreign_bank, cls.foreign_account, cls.foreign_category, cls.foreign_item = make_finances(cls.other, 'Foreign')

    def collect(self, location='/dashboard/'):
        with patch('assistant.context.timezone.now', return_value=datetime(2026, 10, 18, 12, tzinfo=datetime_timezone.utc)):
            return collect_context(self.user, normalize_location(self.user, location))

    def test_native_balances_have_cutoff_and_never_refresh_ledger_or_convert_fx(self):
        BankMovement.objects.create(user=self.user, account=self.account, direction='CREDIT', kind='ADJUSTMENT',
                                    amount=Decimal('50.00'), effective_date=date(2026, 10, 19))
        second = BankAccount.objects.create(user=self.user, bank=self.bank, name='EUR account', currency='EUR',
                                            opening_balance=Decimal('21.80'), opening_date=date(2026, 10, 20))
        with patch('transactions.services.sync_user_ledger', side_effect=AssertionError('No sync')):
            with CaptureQueriesContext(connection) as queries:
                snapshot = self.collect()
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in queries))
        self.assertEqual(snapshot['cutoff'], '2026-10-18')
        self.assertEqual(snapshot['currency'], 'USD')
        self.assertEqual(snapshot['metrics'], [{'label': self.account.name, 'value': '87.66', 'currency': 'BRL'},
                                               {'label': second.name, 'value': '0.00', 'currency': 'EUR'}])
        self.assertIn('no currency conversion', ' '.join(snapshot['warnings']))
        serialized = json.dumps(snapshot)
        self.assertNotIn('Foreign', serialized)
        self.assertNotIn('PRIVATE', serialized)
        self.assertNotIn('RAW DESCRIPTION', serialized)

    def test_app_timezone_changes_financial_cutoff_without_host_clock(self):
        instant = datetime(2026, 10, 19, 0, 30, tzinfo=datetime_timezone.utc)
        with patch('assistant.context.timezone.now', return_value=instant):
            with timezone.override('America/Sao_Paulo'):
                sp = collect_context(self.user, normalize_location(self.user, '/dashboard/'))
            with timezone.override('UTC'):
                utc = collect_context(self.user, normalize_location(self.user, '/dashboard/'))
        self.assertEqual(sp['cutoff'], '2026-10-18')
        self.assertEqual(utc['cutoff'], '2026-10-19')
        self.assertEqual(sp['captured_at'], utc['captured_at'])

    def test_missing_preferences_are_read_without_get_or_create(self):
        UserPreference.objects.filter(user=self.user).delete()
        with CaptureQueriesContext(connection) as queries:
            snapshot = self.collect()
        self.assertEqual(snapshot['currency'], 'BRL')
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in queries))

    def test_filtered_or_editor_pages_never_broaden_to_current_account_totals(self):
        locations = ['/dashboard/?month=2026-09', '/dashboard/reports/',
                     '/banking/invoices/?month=2026-10', f'/banking/accounts/{self.account.pk}/edit/',
                     '/transactions/?month=2026-10', f'/transactions/?category={self.category.pk}',
                     '/transactions/create/?account=' + str(self.account.pk), '/investments/', '/planning/']
        for location in locations:
            with self.subTest(location=location):
                snapshot = self.collect(location)
                self.assertEqual(snapshot['metrics'], [])
                self.assertEqual(len(snapshot['sources']), 1)
                self.assertTrue(snapshot['warnings'])

    def test_transactions_are_dated_sources_not_realized_split_or_recurrence_totals(self):
        self.item.is_fixed = True
        self.item.save(update_fields=['is_fixed'])
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount=Decimal('12.34'))
        future = Transaction.objects.create(user=self.user, title='Future installment', amount=Decimal('30.01'),
                                            transaction_type='EXPENSE', category=self.category, payment_channel='ACCOUNT',
                                            bank_account=self.account, date=date(2026, 11, 1), installments=3)
        snapshot = self.collect('/transactions/')
        values = {metric['value']: metric for metric in snapshot['metrics']}
        self.assertEqual(set(values), {'12.34', '30.01'})
        self.assertIn('2026-10-10', values['12.34']['label'])
        self.assertIn('Recurring template', values['12.34']['label'])
        self.assertIn('2026-11-01', values['30.01']['label'])
        self.assertIn('Installment source; future date', values['30.01']['label'])
        self.assertIn('not realized cash flows', ' '.join(snapshot['warnings']))
        single = self.collect(reverse('transactions:update', args=[future.pk]))
        self.assertEqual(len(single['metrics']), 1)
        self.assertEqual(single['metrics'][0]['value'], '30.01')

    def test_owned_bank_detail_and_source_lists_are_bounded(self):
        for number in range(MAX_ROWS + 1):
            BankAccount.objects.create(user=self.user, bank=self.bank, name=f'Extra {number}', currency='BRL')
            Transaction.objects.create(user=self.user, title=f'Extra source {number}', amount=Decimal('1.00'),
                                        transaction_type='EXPENSE', category=self.category, payment_channel='ACCOUNT',
                                        bank_account=self.account, date=date(2026, 10, 11))
        for location in [reverse('banking:detail', args=[self.bank.pk]), '/transactions/']:
            with self.subTest(location=location):
                snapshot = self.collect(location)
                self.assertEqual(len(snapshot['metrics']), MAX_ROWS)
                self.assertIn('Only the first 20', ' '.join(snapshot['warnings']))
                self.assertNotIn('Foreign', json.dumps(snapshot))

    def test_inconsistent_legacy_movements_do_not_leak_foreign_amounts(self):
        BankMovement.objects.create(user=self.other, account=self.account, direction='CREDIT', kind='ADJUSTMENT',
                                    amount=Decimal('7777.00'), effective_date=date(2026, 10, 15))
        snapshot = self.collect()
        self.assertEqual(snapshot['metrics'], [])
        self.assertIn('ownership is inconsistent', ' '.join(snapshot['warnings']))
        self.assertNotIn('7777', json.dumps(snapshot))
