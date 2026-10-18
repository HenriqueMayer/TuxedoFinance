from datetime import date, timedelta
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CreditCard, InvoicePayment
from banking.services import account_balance
from banking.settlements import save_invoice_payment, delete_invoice_payment, manual_invoice_obligations
from categories.models import Category
from transactions.models import Transaction
from transactions.services import sync_user_ledger


class ConfirmedPaymentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('confirmed', password='Test-2026-password!')
        self.bank = Bank.objects.create(user=self.user, name='Local')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash', currency='BRL', opening_balance=1000)
        self.card = CreditCard.objects.create(user=self.user, account=self.account, name='Card', closing_day=31, due_day=30, manual_settlement_from=timezone.localdate())
        self.category = Category.objects.create(user=self.user, name='Food', transaction_type='EXPENSE')
        self.purchase = Transaction.objects.create(user=self.user, title='Purchase', amount=100, transaction_type='EXPENSE', category=self.category, payment_channel='CREDIT_CARD', credit_card=self.card, date=timezone.localdate().replace(day=1))
        sync_user_ledger(self.user)
        self.invoice = CardInvoice.objects.get(user=self.user)

    def payment(self, amount, **kwargs):
        return InvoicePayment(user=self.user, invoice=self.invoice, account=self.account, amount=Decimal(amount), date=timezone.localdate(), **kwargs)

    def test_partial_payment_is_cash_and_remainder_only_forecast(self):
        self.assertTrue(self.invoice.manual_settlement)
        self.assertEqual(account_balance(self.account), 1000)
        payment = save_invoice_payment(self.payment('40'))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, CardInvoice.Status.PARTIAL)
        self.assertEqual(account_balance(self.account), 960)
        self.assertEqual(manual_invoice_obligations(self.user, timezone.localdate())[0].remaining_amount_at_cutoff, 60)
        sync_user_ledger(self.user)
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 1)
        payment.amount = Decimal('100')
        save_invoice_payment(payment)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, CardInvoice.Status.PAID)
        self.assertIsNotNone(self.invoice.paid_at)
        self.assertEqual(account_balance(self.account), 900)
        delete_invoice_payment(payment)
        self.assertEqual(account_balance(self.account), 1000)

    def test_guard_overpayment_future_foreign_currency_and_ownership(self):
        with self.assertRaises(ValidationError):
            save_invoice_payment(self.payment('101'))
        payment = self.payment('20'); payment.date += timedelta(days=1)
        with self.assertRaises(ValidationError):
            save_invoice_payment(payment)
        other = get_user_model().objects.create_user('other')
        payment = self.payment('20'); payment.user = other
        with self.assertRaises(CardInvoice.DoesNotExist):
            save_invoice_payment(payment)
        self.assertFalse(InvoicePayment.objects.exists())

    def test_payment_survives_source_deletion_and_horizon_changes(self):
        save_invoice_payment(self.payment('40'))
        self.purchase.delete()
        sync_user_ledger(self.user)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount, 0)
        self.assertEqual(self.invoice.overpaid_amount, 40)
        self.assertEqual(account_balance(self.account), 960)

    def test_automatic_history_is_not_reclassified(self):
        self.card.manual_settlement_from = timezone.localdate() + timedelta(days=400)
        self.card.save()
        # Once an invoice has opted into confirmed mode it retains that fact.
        sync_user_ledger(self.user)
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.manual_settlement)
        past_card = CreditCard.objects.create(user=self.user, account=self.account, name='Legacy', closing_day=31, due_day=30)
        Transaction.objects.create(user=self.user, title='Legacy purchase', amount=70, transaction_type='EXPENSE', category=self.category, payment_channel='CREDIT_CARD', credit_card=past_card, date=date(2026, 1, 1))
        sync_user_ledger(self.user)
        legacy = CardInvoice.objects.get(card=past_card)
        self.assertFalse(legacy.manual_settlement)
        self.assertEqual(legacy.status, CardInvoice.Status.PAID)
        past_card.manual_settlement_from = timezone.localdate(); past_card.save()
        sync_user_ledger(self.user)
        legacy.refresh_from_db()
        self.assertFalse(legacy.manual_settlement)

    def test_native_post_invalid_errors_and_user_isolation(self):
        self.client.force_login(self.user)
        url = reverse('banking:invoice_detail', args=[self.invoice.pk])
        confirmation_key = str(uuid.uuid4())
        response = self.client.post(url, {'confirmation_key': confirmation_key, 'account': self.account.pk, 'amount': '101', 'date': timezone.localdate().isoformat(), 'notes': ''})
        self.assertContains(response, 'Payments cannot exceed')
        self.assertFalse(InvoicePayment.objects.exists())
        data = {'confirmation_key': confirmation_key, 'account': self.account.pk, 'amount': '25', 'date': timezone.localdate().isoformat(), 'notes': ''}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account_balance(self.account), 975)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(account_balance(self.account), 975)
        self.client.force_login(get_user_model().objects.create_user('stranger'))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_goal_reservations_keep_their_source_currency(self):
        from banking.forms import BankAccountForm
        from planning.models import FinancialGoal, GoalAllocation
        goal = FinancialGoal.objects.create(user=self.user, name='Safety', currency='BRL', target_amount=100)
        GoalAllocation.objects.create(user=self.user, goal=goal, bank_account=self.account, amount=50)
        # The source remains protected even after the reservation is released
        # by archiving: restoring a goal must not reinterpret its denomination.
        goal.is_archived = True
        goal.save()
        self.account.currency = 'USD'
        with self.assertRaisesMessage(ValidationError, 'Currency cannot change'):
            self.account.full_clean()
        form = BankAccountForm(data={'bank':self.bank.pk, 'name':'Cash', 'currency':'USD', 'opening_balance':'1000'}, instance=self.account, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('currency', form.errors)
