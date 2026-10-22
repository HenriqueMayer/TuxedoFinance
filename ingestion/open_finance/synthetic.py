# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Entirely synthetic, dependency-free provider for an explicitly labelled demo."""
from datetime import timedelta


ITEM = '11111111-1111-4111-8111-111111111111'
CARD = '22222222-2222-4222-8222-222222222222'
BILL = '33333333-3333-4333-8333-333333333333'


class SyntheticClient:
    def __init__(self, now, today):
        self.now, self.today = now, today

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def authenticate(self):
        return None

    def item(self, item_id):
        return {'id': ITEM, 'connector': {'id': 200, 'name': 'MeuPluggy'},
                'consentExpiresAt': (self.now + timedelta(days=100)).isoformat(),
                'status': 'UPDATED', 'executionStatus': 'SUCCESS',
                'lastUpdatedAt': self.now.isoformat()}

    def accounts(self, item_id):
        return [{'id': CARD, 'itemId': ITEM, 'type': 'CREDIT', 'subtype': 'CREDIT_CARD', 'currencyCode': 'BRL'}]

    def bills(self, account_id):
        return [{'id': BILL, 'billClosingDate': (self.today - timedelta(days=5)).isoformat(),
                 'dueDate': (self.today + timedelta(days=2)).isoformat(),
                 'totalAmount': '120.00', 'totalAmountCurrencyCode': 'BRL',
                 'minimumPaymentAmount': None, 'financeCharges': [], 'payments': []}]

    def transactions(self, account_id, date_from, date_to):
        return [{'id': '44444444-4444-4444-8444-444444444444', 'accountId': CARD,
                 'date': (self.today - timedelta(days=10)).isoformat(), 'description': 'Synthetic purchase',
                 'amount': '120.00', 'currencyCode': 'BRL', 'status': 'POSTED',
                 'creditCardMetadata': {'billId': BILL, 'installmentNumber': 1, 'totalInstallments': 1}}]
