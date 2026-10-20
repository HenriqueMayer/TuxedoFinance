"""Invoice rules use Django's financial day across host midnight boundaries.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from banking.models import (
    Bank, BankAccount, BankMovement, CardInvoice, CreditCard, InvoicePayment,
)
from banking.services import account_balance
from banking.settlements import (
    invoice_projection, manual_invoice_obligations, save_invoice_payment,
)
from categories.models import Category
from transactions.models import Transaction
from transactions.services import sync_user_ledger


INSTANT = datetime(2026, 10, 19, 0, 30, tzinfo=datetime_timezone.utc)


class HostCalendarDate(date):
    """Keep date construction/type checks while decoupling the host's today."""

    @classmethod
    def today(cls):
        return cls(2026, 10, 18)


OCTOBER_18 = HostCalendarDate(2026, 10, 18)
OCTOBER_19 = HostCalendarDate(2026, 10, 19)


@override_settings(TIME_ZONE='UTC', USE_TZ=True)
class FinancialCalendarTests(TestCase):
    def setUp(self):
        clock = patch('django.utils.timezone.now', return_value=INSTANT)
        clock.start()
        self.addCleanup(clock.stop)
        host_date = patch('banking.models.date', HostCalendarDate)
        host_date.start()
        self.addCleanup(host_date.stop)
        self.enterContext(timezone.override('UTC'))

        self.user = get_user_model().objects.create_user('financial-calendar-owner')
        bank = Bank.objects.create(user=self.user, name='Calendar bank')
        self.account = BankAccount.objects.create(
            user=self.user, bank=bank, name='Cash', currency='BRL',
            opening_balance=Decimal('1000.00'),
            opening_date=HostCalendarDate(2026, 1, 1),
        )
        self.card = CreditCard.objects.create(
            user=self.user, account=self.account, name='Confirmed calendar card',
            closing_day=10, due_day=18,
            manual_settlement_from=HostCalendarDate(2026, 1, 1),
        )
        category = Category.objects.create(
            user=self.user, name='Calendar expense', transaction_type='EXPENSE',
        )
        self.purchase = Transaction(
            user=self.user, title='Calendar purchase', amount=Decimal('100.00'),
            transaction_type='EXPENSE', category=category,
            payment_channel='CREDIT_CARD', credit_card=self.card,
            date=HostCalendarDate(2026, 10, 1),
        )
        self.purchase.full_clean()
        self.purchase.save()
        sync_user_ledger(self.user)
        self.invoice = CardInvoice.objects.get(card=self.card)
        self.assertEqual(self.invoice.due_date, OCTOBER_18)
        self.assertTrue(self.invoice.manual_settlement)

    def payment(self, amount, paid_on):
        return InvoicePayment(
            user=self.user, invoice=self.invoice, account=self.account,
            amount=Decimal(amount), date=paid_on,
        )

    def record_payment(self, amount, paid_on):
        # Property/GET regressions need the same valid recorded evidence under
        # both implementations. Align only fixture creation, then restore the
        # disagreeing host clock before exercising the financial cutoff.
        with patch.object(HostCalendarDate, 'today', return_value=OCTOBER_19):
            return save_invoice_payment(self.payment(amount, paid_on))

    def invoice_variants(self):
        yield CardInvoice.objects.get(pk=self.invoice.pk)
        yield CardInvoice.objects.prefetch_related('payments').get(pk=self.invoice.pk)

    def test_overdue_uses_django_today_and_keeps_the_due_day_inclusive(self):
        self.assertEqual(timezone.localdate(), OCTOBER_19)
        self.assertEqual(HostCalendarDate.today(), OCTOBER_18)
        self.assertTrue(self.invoice.is_overdue)
        with timezone.override('America/Sao_Paulo'):
            self.assertEqual(timezone.localdate(), OCTOBER_18)
            self.assertFalse(self.invoice.is_overdue)
        self.invoice.status = CardInvoice.Status.PAID
        self.assertFalse(self.invoice.is_overdue)

    def test_full_clean_and_confirmed_save_accept_django_today_when_host_day_lags(self):
        payment = self.payment('40.00', OCTOBER_19)
        payment.full_clean()
        payment = save_invoice_payment(payment)
        payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(payment.date, OCTOBER_19)
        self.assertEqual(payment.movement.effective_date, OCTOBER_19)
        self.assertEqual(payment.movement.amount, Decimal('40.00'))
        self.assertEqual(self.invoice.status, CardInvoice.Status.PARTIAL)
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 1)
        self.assertFalse(BankMovement.objects.filter(invoice=self.invoice).exists())
        self.assertEqual(account_balance(self.account), Decimal('960.00'))
        for zone in ['UTC', 'America/Sao_Paulo']:
            with self.subTest(zone=zone), timezone.override(zone):
                self.assertEqual(account_balance(self.account, as_of=OCTOBER_18), Decimal('1000.00'))
                self.assertEqual(account_balance(self.account, as_of=OCTOBER_19), Decimal('960.00'))

    def test_future_confirmation_uses_the_active_django_timezone(self):
        with timezone.override('America/Sao_Paulo'), patch.object(
            HostCalendarDate, 'today', return_value=OCTOBER_19,
        ):
            self.assertEqual(timezone.localdate(), OCTOBER_18)
            payment = self.payment('40.00', OCTOBER_19)
            with self.assertRaises(ValidationError) as invalid:
                payment.full_clean()
            self.assertIn('date', invalid.exception.message_dict)
            self.assertIn('future', str(invalid.exception.message_dict['date']))
            with self.assertRaises(ValidationError):
                save_invoice_payment(payment)
        self.assertFalse(InvoicePayment.objects.filter(user=self.user).exists())
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_confirmed_and_remaining_amounts_share_the_cutoff_with_prefetched_payments(self):
        self.record_payment('30.00', OCTOBER_18)
        self.record_payment('50.00', OCTOBER_19)
        for prefetched, invoice in enumerate(self.invoice_variants()):
            with self.subTest(prefetched=bool(prefetched)):
                self.assertEqual(invoice.confirmed_amount, Decimal('80.00'))
                self.assertEqual(invoice.remaining_amount, Decimal('20.00'))
                with timezone.override('America/Sao_Paulo'):
                    self.assertEqual(invoice.confirmed_amount, Decimal('30.00'))
                    self.assertEqual(invoice.remaining_amount, Decimal('70.00'))
        for zone in ['UTC', 'America/Sao_Paulo']:
            with self.subTest(zone=zone), timezone.override(zone):
                obligations = manual_invoice_obligations(self.user, OCTOBER_18)
                self.assertEqual(obligations[0].remaining_amount_at_cutoff, Decimal('70.00'))
                obligations = manual_invoice_obligations(self.user, OCTOBER_19)
                self.assertEqual(obligations[0].remaining_amount_at_cutoff, Decimal('20.00'))
                self.assertEqual(invoice_projection(self.invoice, OCTOBER_18)['status'], CardInvoice.Status.PARTIAL)
                self.assertEqual(invoice_projection(self.invoice, OCTOBER_19)['status'], CardInvoice.Status.PARTIAL)

    def test_overpaid_credit_uses_the_cutoff_without_rewriting_recorded_evidence(self):
        self.record_payment('30.00', OCTOBER_18)
        self.record_payment('50.00', OCTOBER_19)
        payments = list(InvoicePayment.objects.values('pk', 'date', 'amount', 'movement_id'))
        movements = list(BankMovement.objects.values('pk', 'effective_date', 'amount', 'source_key'))
        self.purchase.amount = Decimal('60.00')
        self.purchase.full_clean()
        self.purchase.save()
        sync_user_ledger(self.user)
        for prefetched, invoice in enumerate(self.invoice_variants()):
            with self.subTest(prefetched=bool(prefetched)):
                self.assertEqual(invoice.amount, Decimal('60.00'))
                self.assertEqual(invoice.overpaid_amount, Decimal('20.00'))
                self.assertEqual(invoice.remaining_amount, Decimal('0.00'))
                with timezone.override('America/Sao_Paulo'):
                    self.assertEqual(invoice.overpaid_amount, Decimal('0.00'))
                    self.assertEqual(invoice.remaining_amount, Decimal('30.00'))
        self.assertEqual(list(InvoicePayment.objects.values('pk', 'date', 'amount', 'movement_id')), payments)
        self.assertEqual(list(BankMovement.objects.values('pk', 'effective_date', 'amount', 'source_key')), movements)

    def test_invoice_get_renders_current_prefetched_amounts_and_preserves_payment_dates(self):
        self.record_payment('40.00', OCTOBER_19)
        payments = list(InvoicePayment.objects.values('pk', 'date', 'amount', 'movement_id'))
        movements = list(BankMovement.objects.values('pk', 'effective_date', 'amount', 'source_key'))
        self.client.force_login(self.user)
        response = self.client.get(reverse('banking:invoice_detail', args=[self.invoice.pk]))
        self.assertEqual(response.status_code, 200)
        invoice = response.context['invoice']
        self.assertIn('payments', invoice._prefetched_objects_cache)
        self.assertEqual(invoice.confirmed_amount, Decimal('40.00'))
        self.assertEqual(invoice.remaining_amount, Decimal('60.00'))
        self.assertTrue(invoice.is_overdue)
        self.assertContains(response, 'BRL 40,00')
        self.assertContains(response, '60,00 BRL')
        self.assertContains(response, '19/10/2026')
        self.assertEqual(list(InvoicePayment.objects.values('pk', 'date', 'amount', 'movement_id')), payments)
        self.assertEqual(list(BankMovement.objects.values('pk', 'effective_date', 'amount', 'source_key')), movements)

    def test_paid_invoice_and_default_home_reports_keep_the_same_financial_day(self):
        # Clear the active override: the real default remains UTC even while
        # the host decoy still reports the previous Sao Paulo calendar date.
        with timezone.override(None):
            self.assertEqual(timezone.get_current_timezone_name(), 'UTC')
            self.assertEqual(timezone.localdate(), OCTOBER_19)
            payment = self.record_payment('100.00', OCTOBER_19)
            self.assertEqual(HostCalendarDate.today(), OCTOBER_18)
            payments = list(InvoicePayment.objects.values('pk', 'date', 'amount', 'movement_id'))
            movements = list(BankMovement.objects.values('pk', 'effective_date', 'amount', 'source_key'))
            self.client.force_login(self.user)

            response = self.client.get(reverse('banking:invoice_detail', args=[self.invoice.pk]))
            self.assertEqual(response.status_code, 200)
            invoice = response.context['invoice']
            self.assertEqual(invoice.status, CardInvoice.Status.PAID)
            self.assertEqual(invoice.confirmed_amount, Decimal('100.00'))
            self.assertEqual(invoice.remaining_amount, Decimal('0.00'))
            self.assertEqual(invoice.overpaid_amount, Decimal('0.00'))
            self.assertFalse(invoice.is_overdue)
            self.assertContains(response, 'BRL 100,00')
            self.assertContains(response, '0,00 BRL')

            home = self.client.get(reverse('dashboard:index'))
            self.assertEqual(home.status_code, 200)
            self.assertEqual(home.context['current_balance'], Decimal('900.00'))
            reports = self.client.get(reverse('analytics:index'))
            self.assertEqual(reports.status_code, 200)
            self.assertEqual(reports.context['evolution']['balance_today'], Decimal('900.00'))

            payment.refresh_from_db()
            payment.full_clean()
            self.assertEqual(payment.date, OCTOBER_19)
            self.assertEqual(account_balance(self.account, as_of=OCTOBER_18), Decimal('1000.00'))
            self.assertEqual(account_balance(self.account, as_of=OCTOBER_19), Decimal('900.00'))
            self.assertEqual(list(InvoicePayment.objects.values('pk', 'date', 'amount', 'movement_id')), payments)
            self.assertEqual(list(BankMovement.objects.values('pk', 'effective_date', 'amount', 'source_key')), movements)
