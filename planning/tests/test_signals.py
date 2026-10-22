# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Signals coverage for planning."""

from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse
from banking.models import BankAccount, BankMovement, CreditCard
from banking.services import account_balance
from planning.models import CategoryBudget, SignalDecision, SignalSettings
from planning.services import local_signals
from transactions.models import Transaction
from planning.tests.fixtures import PlanningFixture


class SignalTests(PlanningFixture):
    def test_historical_cash_signal_does_not_count_later_payments_twice(self):
        from banking.models import CardInvoice, InvoicePayment
        from banking.settlements import save_invoice_payment, delete_invoice_payment
        self.account.opening_balance = Decimal('100')
        self.account.save()
        other = BankAccount.objects.create(user=self.user, bank=self.bank, name='Other real cash', currency='BRL', opening_balance=100, opening_date=date(2020, 1, 1))
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Historical manual', closing_day=10, due_day=28, manual_settlement_from=self.today-timedelta(days=200))
        cutoff = self.today-timedelta(days=1)
        invoice = CardInvoice.objects.create(user=self.user, card=card, reference_month=self.month, due_date=self.today+timedelta(days=10), amount=80, manual_settlement=True)
        for account in (self.account, other):
            for due in (self.today+timedelta(days=10), cutoff-timedelta(days=2)):
                with self.subTest(account=account.pk, due=due):
                    invoice.due_date = due
                    invoice.save()
                    payment = save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=account, amount=40, date=self.today))
                    signals = [row for row in local_signals(self.user, as_of=cutoff)['signals'] if row['kind']=='futurecashshortage']
                    self.assertEqual(signals, [])
                    self.assertEqual(account_balance(self.account, cutoff), 100)
                    delete_invoice_payment(payment)

    def test_cash_signal_includes_manual_remainder_without_fabricating_debit(self):
        from banking.models import CardInvoice, InvoicePayment
        from banking.settlements import save_invoice_payment
        from transactions.services import sync_user_ledger
        self.account.opening_balance = Decimal('100')
        self.account.save()
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual', closing_day=31, due_day=31, manual_settlement_from=self.today)
        self.expense(amount=150, payment_channel='CREDIT_CARD', bank_account=None, credit_card=card)
        sync_user_ledger(self.user)
        SignalSettings.objects.create(user=self.user, forecast_days=90)
        invoice = CardInvoice.objects.get(card=card)
        signals = [row for row in local_signals(self.user)['signals'] if row['kind']=='futurecashshortage']
        self.assertEqual(len(signals), 1)
        self.assertIn('-50.00', signals[0]['explanation'])
        self.assertIn(reverse('banking:invoice_detail', args=[invoice.pk]), [source['url'] for source in signals[0]['sources']])
        self.assertEqual(account_balance(self.account), 100)
        self.assertFalse(BankMovement.objects.filter(account=self.account).exists())
        save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=self.account, amount=40, date=self.today))
        signals = [row for row in local_signals(self.user)['signals'] if row['kind']=='futurecashshortage']
        self.assertEqual(len(signals), 1)
        self.assertIn('-50.00', signals[0]['explanation'])
        self.assertEqual(account_balance(self.account), 60)

    def test_duplicates_explained_owned_stable_and_review_does_not_mutate_sources(self):
        self.expense(title='  Local subscription ', date=self.today - timedelta(days=1))
        latest = self.expense(title='local   subscription', date=self.today)
        self.expense(user=self.other, category=self.private_category, bank_account=self.private_account, title='local subscription', date=self.today)
        result = local_signals(self.user)
        duplicate = next(row for row in result['signals'] if row['kind'] == 'duplicates')
        self.assertEqual(len(duplicate['sources']), 2)
        self.assertEqual(duplicate['key'], next(row for row in local_signals(self.user)['signals'] if row['kind'] == 'duplicates')['key'])
        before = list(Transaction.objects.values('pk', 'amount', 'updated_at'))
        self.client.force_login(self.user)
        response = self.client.post(reverse('planning:signal_decision'), {'key': duplicate['key'], 'action': 'ACK'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(Transaction.objects.values('pk', 'amount', 'updated_at')), before)
        self.assertFalse(BankMovement.objects.exists())
        reviewed = next(row for row in local_signals(self.user)['signals'] if row['kind'] == 'duplicates')
        self.assertEqual(reviewed['decision'].action, 'ACK')
        latest.title = 'A different record'
        latest.save()
        self.assertFalse(any(row['kind'] == 'duplicates' for row in local_signals(self.user)['signals']))

    def test_subscription_threshold_and_fixed_template_history_limit(self):
        self.expense(title='Streaming', amount='100', date=self.today - timedelta(days=30))
        self.expense(title='streaming', amount='115')
        self.expense(title='Fixed template', amount='900', is_fixed=True)
        signals = local_signals(self.user)['signals']
        increases = [row for row in signals if row['kind'] == 'subscriptionincrease']
        self.assertEqual(len(increases), 1)
        self.assertIn('15.00%', increases[0]['explanation'])
        SignalSettings.objects.create(user=self.user, subscription_increase_percent='20')
        self.assertFalse(any(row['kind'] == 'subscriptionincrease' for row in local_signals(self.user)['signals']))

    def test_budget_and_cash_forecast_explain_only_known_money(self):
        CategoryBudget.objects.create(user=self.user, category=self.category, month=self.month, amount='50', currency='BRL')
        self.expense(amount='100')
        BankMovement.objects.create(user=self.user, account=self.account, direction='DEBIT', kind='EXPENSE', amount='1200', effective_date=self.today + timedelta(days=2))
        signals = local_signals(self.user)['signals']
        self.assertTrue(any(row['kind'] == 'budgetoverspend' for row in signals))
        shortage = next(row for row in signals if row['kind'] == 'futurecashshortage')
        self.assertIn('-200.00', shortage['explanation'])
        self.assertIn(str(self.today + timedelta(days=2)), shortage['explanation'])
        self.assertIn('Unrecorded income', shortage['explanation'])

    def test_read_only_get_defaults_disabled_signals_and_review_ownership(self):
        self.expense(title='Duplicate')
        self.expense(title='Duplicate')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('planning:signals')).status_code, 200)
        self.assertFalse(SignalSettings.objects.filter(user=self.user).exists())
        self.assertFalse(SignalDecision.objects.exists())
        SignalSettings.objects.create(user=self.user, duplicates_enabled=False, subscriptionincrease_enabled=False, budgetoverspend_enabled=False, futurecashshortage_enabled=False)
        self.assertEqual(local_signals(self.user)['signals'], [])
        response = self.client.post(reverse('planning:signal_decision'), {'key': 'duplicates:private-key', 'action': 'DISMISS'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SignalDecision.objects.exists())
