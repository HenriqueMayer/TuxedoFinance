"""Assistant simulations use net category expenses including invoice credits."""
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from assistant.simulation_tools import simulate_month
from assistant.tests.support import make_finances, make_owner
from banking.models import CardInvoiceCredit, CreditCard


class InvoiceCreditSimulationTests(TestCase):
    def test_category_cut_uses_net_expenses_and_never_saves(self):
        user = make_owner('simulation-credit')
        _bank, account, category, item = make_finances(user)
        card = CreditCard.objects.create(user=user, account=account, name='Card', closing_day=24, due_day=1)
        item.amount = '100'
        item.payment_channel, item.bank_account, item.credit_card = 'CREDIT_CARD', None, card
        item.date = date(2026, 10, 5)
        item.save()
        CardInvoiceCredit.objects.create(user=user, card=card, category=category,
            title='Refund', amount='8.95', date=date(2026, 10, 10), reference_month=date(2026, 10, 1))
        arguments = {'planning_month': '2026-10', 'gross_salary': '6000.00', 'clt_dependents': 0,
            'clt_pension': '0.00', 'clt_transport': '0.00', 'clt_food': '0.00',
            'clt_health': '0.00', 'clt_other': '0.00', 'extra_expenses': [],
            'category_reductions': [{'category_id': category.pk, 'amount': '10.00'}]}
        with patch('transactions.services.sync_user_ledger') as sync:
            result = simulate_month(user, arguments)
        self.assertTrue(result['complete'], result)
        self.assertEqual(result['forecast']['total'], '91.05')
        self.assertEqual(result['forecast']['adjusted_total'], '81.05')
        self.assertEqual(result['category_reductions'][0]['before'], '91.05')
        self.assertEqual(result['budget']['registered_expenses'], '81.05')
        self.assertFalse(result['saved'])
        sync.assert_not_called()
