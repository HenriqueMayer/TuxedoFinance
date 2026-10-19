# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit operator-only provider probe; never synchronize or import the ledger."""
from datetime import timedelta
import getpass
from pathlib import Path
import sys
import warnings

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ingestion.open_finance.client import PilotError, PluggyClient
from ingestion.open_finance.report import build_report, check_item, closed_bills, identifier, reusable
from ingestion.open_finance.storage import PilotStore
from ingestion.open_finance.synthetic import CARD, ITEM, SyntheticClient


class Command(BaseCommand):
    help = 'Read-only Inter bill pilot. --demo is offline; --live requires personal setup and hidden credential prompts.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--demo', action='store_true', help='Use labelled synthetic data without networking.')
        mode.add_argument('--live', action='store_true', help='Read the explicitly authorized personal proxy.')
        parser.add_argument('--confirm-inter', action='store_true', help='Attest that the Dashboard item is your regulated Inter PF connection.')
        parser.add_argument('--item-id', help='Known MeuPluggy proxy item UUID; never a bank credential.')
        parser.add_argument('--card-id', help='Explicit credit-card account UUID within that item.')
        parser.add_argument('--bill-id', help='Explicit published, closed bill UUID within that card.')
        parser.add_argument('--include-transactions', action='store_true', help='Also read a bounded card-transaction window; retain only this bill\'s linked rows.')
        parser.add_argument('--lookback-days', type=int, default=90, help='Transaction window, 1–366 days (default 90). Does not prove complete bill contents.')
        parser.add_argument('--output-dir', type=Path, default=None, help='Private local artifact directory; defaults to ignored .local/open-finance-pilot.')

    def hidden(self, prompt):
        if not sys.stdin.isatty():
            raise PilotError('interactive_terminal_required')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                value = getpass.getpass(prompt)
        except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
            raise PilotError('input_cancelled') from None
        if not value or len(value) > 512:
            raise PilotError('invalid_input')
        return value.strip()

    def handle(self, *args, **options):
        try:
            self.run(options)
        except PilotError as error:
            raise CommandError(f'Pilot stopped ({error.code}). No financial records were changed. See docs/open-finance-pilot.md.') from None

    def run(self, options):
        mode = 'synthetic' if options['demo'] else 'live'
        if not 1 <= options['lookback_days'] <= 366:
            raise PilotError('invalid_lookback')
        if mode == 'live' and not options['confirm_inter']:
            raise PilotError('inter_attestation_required')
        item_id = ITEM if options['demo'] else identifier(options['item_id'] or self.hidden('Inter MeuPluggy proxy item ID (hidden): '))
        card_id = identifier(options['card_id']) if options['card_id'] else None
        bill_id = identifier(options['bill_id']) if options['bill_id'] else None
        requested_card_id, requested_bill_id = card_id, bill_id
        root = options['output_dir'] or settings.BASE_DIR / '.local' / 'open-finance-pilot'
        store = PilotStore(root)
        # The artifact is private to the OS operator, not a web-visible record.
        # A file lock serializes attempts without holding any SQLite transaction.
        key = f'{mode}:{item_id}'
        now = timezone.now()
        today = timezone.localdate(now)
        with store.lock(key):
            previous = store.load(key)
            if reusable(previous, mode=mode, item_id=item_id, card_id=card_id, bill_id=bill_id,
                        include_transactions=options['include_transactions'],
                        lookback_days=options['lookback_days'], now=now):
                self.stdout.write('Using a private observation retrieved less than 24 hours ago; no provider request was made.')
                self.summary(previous, store.path(key))
                return
            if options['demo']:
                client = SyntheticClient(now, today)
                card_id = card_id or CARD
            else:
                self.stdout.write('Read-only personal pilot. Credentials are hidden, used once and never saved. No bank refresh or payment is requested.')
                client_id = self.hidden('Pluggy Client ID (hidden): ')
                secret = self.hidden('Pluggy Client Secret (hidden): ')
                client = PluggyClient(client_id, secret)
                del client_id, secret
            with client:
                client.authenticate()
                item = client.item(item_id)
                check_item(item, item_id, timezone.now())
                cards = client.accounts(item_id)
                if card_id is None:
                    if not cards:
                        raise PilotError('card_unavailable_or_not_authorized')
                    if len(cards) > 1:
                        raise PilotError('multiple_cards_require_card_id')
                    card_id = identifier(cards[0]['id'])
                account = next((row for row in cards if identifier(row.get('id')) == card_id), None)
                if account is None:
                    raise PilotError('foreign_account')
                bills = closed_bills(client.bills(card_id), today)
                bill = next((row for row in bills if identifier(row['id']) == bill_id), None) if bill_id else next(iter(bills), None)
                if bill is None:
                    raise PilotError('closed_bill_unavailable')
                transactions = None
                window = None
                if options['include_transactions']:
                    first = today - timedelta(days=options['lookback_days'])
                    transactions = client.transactions(card_id, first.isoformat(), today.isoformat())
                    window = {'from': first.isoformat(), 'to': today.isoformat(), 'lookback_days': options['lookback_days']}
                retrieved = timezone.now()
                check_item(item, item_id, retrieved)
                report = build_report(item=item, account=account, bill=bill, transactions=transactions,
                                      now=retrieved, today=today, mode=mode, window=window,
                                      requested_card_id=requested_card_id, requested_bill_id=requested_bill_id)
            self.summary(report, store.save(key, report))

    def summary(self, report, path):
        self.stdout.write(f"Mode: {report['mode']}. One closed bill observed; {len(report['linked_transactions'])} linked transaction(s).")
        self.stdout.write(f"Warnings: {len(report['warnings'])}. Bank resource collection time is unverified; retrieval time is recorded separately.")
        self.stdout.write(f'Private JSON: {path}')
        self.stdout.write('No database records, categories, balances or payments were changed.')
