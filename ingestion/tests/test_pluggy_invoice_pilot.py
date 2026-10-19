# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Offline command/report regressions, with no installation or bank access."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone as utc
from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from ingestion.open_finance.client import PilotError
from ingestion.open_finance.report import build_report, check_item, closed_bills, reusable
from ingestion.open_finance.storage import PilotStore
from ingestion.open_finance.synthetic import BILL, CARD, ITEM, SyntheticClient


NOW = datetime(2026, 10, 19, 15, tzinfo=utc.utc)
COMMAND = 'ingestion.management.commands.pluggy_invoice_pilot'


class ReportTests(SimpleTestCase):
    def setUp(self):
        self.source = SyntheticClient(NOW, NOW.date())
        self.item = self.source.item(ITEM)
        self.account = self.source.accounts(ITEM)[0]
        self.bill = self.source.bills(CARD)[0]

    def report(self, **changes):
        arguments = dict(item=self.item, account=self.account, bill=self.bill,
                         transactions=None, now=NOW, today=NOW.date(), mode='synthetic')
        arguments.update(changes)
        return build_report(**arguments)

    def test_native_values_missing_not_zero_and_no_inferred_payment(self):
        self.bill['totalAmount'] = '0.00'
        self.bill['payments'] = [{'amount': '45.00', 'currencyCode': 'BRL', 'paymentDate': '2026-10-17'}]
        result = self.report()
        self.assertEqual(result['bill']['total'], '0.00')
        self.assertIsNone(result['bill']['minimum_payment'])
        self.assertNotIn('paid', result['bill'])
        self.assertFalse(result['financial_writes'])
        self.bill.pop('totalAmount')
        result = self.report()
        self.assertIsNone(result['bill']['total'])
        self.assertIn('bill_total_or_currency_missing', result['warnings'])

    def test_closing_date_required_and_future_not_selected(self):
        variants = [dict(self.bill, billClosingDate=None), dict(self.bill, billClosingDate='2026-11-01'),
                    dict(self.bill, billClosingDate='invalid')]
        self.assertEqual(closed_bills(variants, NOW.date()), [])
        self.assertEqual(closed_bills([self.bill, *variants], NOW.date()), [self.bill])

    def test_expired_authorization_rejected_even_updated_empty_item(self):
        self.item['consentExpiresAt'] = (NOW - timedelta(seconds=1)).isoformat()
        with self.assertRaisesMessage(PilotError, 'authorization_expired'):
            check_item(self.item, ITEM, NOW)

    def test_direct_bank_or_sandbox_connector_not_accepted_as_personal_proxy(self):
        for connector in ({'id': 823, 'name': 'Inter'}, {'id': 200, 'name': 'Sandbox'}):
            self.item['connector'] = connector
            with self.assertRaisesMessage(PilotError, 'not_personal_proxy'):
                check_item(self.item, ITEM, NOW)

    def test_partial_stale_and_unknown_bank_collection_not_hidden(self):
        self.item.update(executionStatus='PARTIAL_SUCCESS', lastUpdatedAt='2026-09-01T00:00:00Z')
        result = self.report()
        self.assertIn('provider_partial_or_unknown_execution', result['warnings'])
        self.assertIn('proxy_update_missing_stale_or_future', result['warnings'])
        self.assertIsNone(result['bank_resource_collected_at'])
        self.assertEqual(result['source']['verified_by'], 'operator_attestation')

    def test_only_exact_bill_links_retained_without_guessing(self):
        one = self.source.transactions(CARD, '2026-07-01', '2026-10-19')[0]
        unlinked = deepcopy(one)
        unlinked['creditCardMetadata'] = {}
        another = deepcopy(one)
        another['creditCardMetadata']['billId'] = ITEM
        result = self.report(transactions=[one, unlinked, another], window={'from': '2026-07-01', 'to': '2026-10-19'})
        self.assertEqual(len(result['linked_transactions']), 1)
        self.assertEqual(result['unassigned_transactions_in_window'], 1)
        self.assertNotIn('total_purchase_amount', result['linked_transactions'][0])
        self.assertIn('bounded_transaction_window_not_complete_history', result['warnings'])

    def test_foreign_account_rows_and_invalid_money_fail(self):
        transaction = self.source.transactions(CARD, '2026-07-01', '2026-10-19')[0]
        transaction['accountId'] = ITEM
        with self.assertRaisesMessage(PilotError, 'foreign_account'):
            self.report(transactions=[transaction])
        for value in ('NaN', 'Infinity', True, '1e100', '1e-100000000'):
            self.bill['totalAmount'] = value
            with self.assertRaises(PilotError):
                self.report()

    def test_cache_is_scoped_dated_and_never_reuses_demo_as_live(self):
        report = self.report()
        arguments = dict(mode='synthetic', item_id=ITEM, now=NOW)
        self.assertTrue(reusable(report, **arguments))
        self.assertFalse(reusable(report, **dict(arguments, mode='live')))
        self.assertFalse(reusable(report, **dict(arguments, item_id=CARD)))
        self.assertFalse(reusable(report, **dict(arguments, card_id=ITEM)))
        self.assertFalse(reusable(report, **dict(arguments, now=NOW + timedelta(hours=24))))
        self.assertFalse(reusable(report, **dict(arguments, now=NOW - timedelta(seconds=1))))
        self.assertFalse(reusable(report, **dict(arguments, include_transactions=True)))
        for changes in ({'bill': None}, {'transaction_window': 'invalid'}, {'warnings': None}, {'linked_transactions': None}):
            self.assertFalse(reusable(dict(report, **changes), **arguments))

    def test_cache_requires_source_identity_and_a_confirmed_closed_bill(self):
        report = self.report()
        variants = [
            {'provider': None}, {'source': None}, {'account_id': None},
            {'account_id': 'not-an-id'}, {'bill': {}}, {'financial_cutoff': None},
            {'source': dict(report['source'], bank='Unverified bank')},
            {'bill': dict(report['bill'], id='not-an-id')},
            {'bill': dict(report['bill'], closing_date=None)},
            {'bill': dict(report['bill'], closing_date='2026-10-21')},
            {'bill': dict(report['bill'], due_date='2026-01-01')},
            {'transaction_window': {'lookback_days': 90}},
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                self.assertFalse(reusable(dict(report, **changes), mode='synthetic', item_id=ITEM,
                                          include_transactions=bool(changes.get('transaction_window')), now=NOW))

    def test_cache_preserves_explicit_and_automatic_selection_intent(self):
        for requested_card in (None, CARD):
            for requested_bill in (None, BILL):
                report = self.report(requested_card_id=requested_card, requested_bill_id=requested_bill)
                for card in (None, CARD):
                    for bill in (None, BILL):
                        with self.subTest(requested=(requested_card, requested_bill), current=(card, bill)):
                            self.assertEqual(
                                reusable(report, mode='synthetic', item_id=ITEM, card_id=card, bill_id=bill, now=NOW),
                                (card, bill) == (requested_card, requested_bill),
                            )
        report = self.report()
        report.pop('request_selection')
        self.assertFalse(reusable(report, mode='synthetic', item_id=ITEM, now=NOW))


class PilotCommandTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'private'
        self.output = StringIO()

    def command(self, **options):
        options.setdefault('stdout', self.output)
        options.setdefault('output_dir', self.root)
        with patch(f'{COMMAND}.timezone.now', return_value=NOW):
            call_command('pluggy_invoice_pilot', **options)

    def test_demo_has_no_network_no_prompts_and_separate_private_artifact(self):
        with patch(f'{COMMAND}.PluggyClient', side_effect=AssertionError('network forbidden')):
            self.command(demo=True, include_transactions=True)
        report = PilotStore(self.root).load(f'synthetic:{ITEM}')
        self.assertEqual(report['mode'], 'synthetic')
        self.assertEqual(len(report['linked_transactions']), 1)
        self.assertIn('synthetic', self.output.getvalue())
        self.assertIsNone(PilotStore(self.root).load(f'live:{ITEM}'))

    def test_live_requires_source_attestation_before_prompt_or_network(self):
        with patch(f'{COMMAND}.PluggyClient') as client, patch(f'{COMMAND}.getpass.getpass') as prompt:
            with self.assertRaisesMessage(CommandError, 'inter_attestation_required'):
                self.command(live=True, item_id=ITEM)
        client.assert_not_called()
        prompt.assert_not_called()

    def test_interactive_credentials_only_no_stdin_pipe_fallback(self):
        with patch(f'{COMMAND}.sys.stdin.isatty', return_value=False):
            with self.assertRaisesMessage(CommandError, 'interactive_terminal_required'):
                self.command(live=True, confirm_inter=True, item_id=ITEM)

    def test_live_fake_provider_then_daily_cache_without_credentials_or_rewrite(self):
        source = SyntheticClient(NOW, NOW.date())
        with patch(f'{COMMAND}.sys.stdin.isatty', return_value=True), \
                patch(f'{COMMAND}.getpass.getpass', side_effect=['not-a-real-id', 'not-a-real-secret']), \
                patch(f'{COMMAND}.PluggyClient', return_value=source) as client:
            self.command(live=True, confirm_inter=True, item_id=ITEM, card_id=CARD)
        client.assert_called_once_with('not-a-real-id', 'not-a-real-secret')
        store = PilotStore(self.root)
        previous = store.path(f'live:{ITEM}').stat().st_mtime_ns
        with patch(f'{COMMAND}.PluggyClient', side_effect=AssertionError('cache must not connect')):
            self.command(live=True, confirm_inter=True, item_id=ITEM, card_id=CARD)
        self.assertEqual(previous, store.path(f'live:{ITEM}').stat().st_mtime_ns)
        self.assertNotIn('not-a-real-secret', self.output.getvalue())
        self.assertNotIn('not-a-real-secret', store.path(f'live:{ITEM}').read_text())

    def test_failed_collection_preserves_previous_report(self):
        self.command(demo=True)
        store = PilotStore(self.root)
        old = store.load(f'synthetic:{ITEM}')
        old['retrieved_at'] = (NOW - timedelta(hours=25)).isoformat()
        store.save(f'synthetic:{ITEM}', old)
        before = store.path(f'synthetic:{ITEM}').read_bytes()
        with patch(f'{COMMAND}.SyntheticClient.bills', side_effect=PilotError('forbidden')):
            with self.assertRaisesMessage(CommandError, 'forbidden'):
                self.command(demo=True)
        self.assertEqual(before, store.path(f'synthetic:{ITEM}').read_bytes())

    def test_multiple_cards_require_explicit_identity_and_never_pick_first(self):
        source = SyntheticClient(NOW, NOW.date())
        cards = [source.accounts(ITEM)[0], dict(source.accounts(ITEM)[0], id=BILL)]
        with patch(f'{COMMAND}.sys.stdin.isatty', return_value=True), \
                patch(f'{COMMAND}.getpass.getpass', side_effect=['mock-id', 'mock-secret']), \
                patch(f'{COMMAND}.PluggyClient', return_value=source), \
                patch.object(source, 'accounts', return_value=cards), patch.object(source, 'bills') as bills:
            with self.assertRaisesMessage(CommandError, 'multiple_cards_require_card_id'):
                self.command(live=True, confirm_inter=True, item_id=ITEM)
        bills.assert_not_called()

    def test_raw_provider_error_and_identifiers_are_not_dumped(self):
        with patch(f'{COMMAND}.SyntheticClient.item', side_effect=PilotError('provider_unavailable')):
            with self.assertRaisesMessage(CommandError, 'provider_unavailable'):
                self.command(demo=True)
        self.assertNotIn(ITEM, self.output.getvalue())


class PilotDatabasePreservationTests(TestCase):
    def test_offline_pilot_makes_zero_queries_and_keeps_seeded_domain_rows(self):
        from banking.models import Bank, BankAccount, CreditCard
        user = get_user_model().objects.create_user(username='synthetic-pilot-owner')
        bank = Bank.objects.create(user=user, name='Inter synthetic')
        account = BankAccount.objects.create(user=user, bank=bank, name='Existing account', currency='BRL', opening_balance='100.00')
        CreditCard.objects.create(user=user, account=account, name='Existing card', closing_day=10, due_day=20)
        models = [model for model in apps.get_models() if model._meta.app_label in {
            'banking', 'transactions', 'investments', 'planning', 'ingestion', 'categories', 'sandbox'}]
        before = {model._meta.label: list(model.objects.order_by('pk').values()) for model in models}
        with tempfile.TemporaryDirectory() as directory, self.assertNumQueries(0):
            call_command('pluggy_invoice_pilot', demo=True, include_transactions=True,
                         output_dir=Path(directory) / 'private', stdout=StringIO())
        after = {model._meta.label: list(model.objects.order_by('pk').values()) for model in models}
        self.assertEqual(before, after)
