"""Read projections stay idempotent while source changes remain observable."""
from datetime import date
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from banking.models import BankMovement, CardInvoice, InvoicePayment
from banking.settlements import save_invoice_payment
from transactions.models import Transaction
from transactions.services import sync_user_ledger
from transactions.tests import TransactionFixture


def writes(queries):
    return [query['sql'] for query in queries if query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]


class ProjectionEfficiencyTests(TransactionFixture):
    cutoff = date(2026, 10, 12)

    def test_warm_sync_preserves_sources_timestamps_and_issues_no_writes(self):
        self.make_transaction(is_fixed=True)
        self.make_transaction(payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit, installments=6)
        sync_user_ledger(self.user, self.cutoff)
        sources = list(Transaction.objects.filter(user=self.user).order_by('pk').values())
        movements = list(BankMovement.objects.filter(user=self.user).order_by('pk').values())
        invoices = list(CardInvoice.objects.filter(user=self.user).order_by('pk').values())
        with CaptureQueriesContext(connection) as queries:
            sync_user_ledger(self.user, self.cutoff)
        self.assertEqual(writes(queries), [])
        self.assertEqual(sources, list(Transaction.objects.filter(user=self.user).order_by('pk').values()))
        self.assertEqual(movements, list(BankMovement.objects.filter(user=self.user).order_by('pk').values()))
        self.assertEqual(invoices, list(CardInvoice.objects.filter(user=self.user).order_by('pk').values()))

    def test_warm_query_count_does_not_grow_with_recurring_occurrences(self):
        self.make_transaction(is_fixed=True)
        sync_user_ledger(self.user, self.cutoff)
        with CaptureQueriesContext(connection) as small:
            sync_user_ledger(self.user, self.cutoff)
        for index in range(29):
            self.make_transaction(title=f'Recurring {index}', is_fixed=True)
        sync_user_ledger(self.user, self.cutoff)
        with CaptureQueriesContext(connection) as large:
            sync_user_ledger(self.user, self.cutoff)
        self.assertEqual(len(small), len(large))
        self.assertEqual(writes(large), [])

    def test_direct_source_and_card_calendar_changes_are_reconciled(self):
        immediate = self.make_transaction(amount=Decimal('10'))
        card_purchase = self.make_transaction(payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit)
        sync_user_ledger(self.user, self.cutoff)
        Transaction.objects.filter(pk=immediate.pk).update(amount=Decimal('13'))
        self.credit.due_day = 20
        self.credit.save(update_fields=['due_day'])
        with CaptureQueriesContext(connection) as changed:
            sync_user_ledger(self.user, self.cutoff)
        self.assertEqual(len(writes(changed)), 3)
        self.assertEqual(BankMovement.objects.get(source_key=f'transaction:{immediate.pk}:2026-01').amount, Decimal('13'))
        invoice = CardInvoice.objects.get(card=self.credit)
        self.assertEqual(invoice.due_date, self.credit.due_date_for(card_purchase.billed_month))
        self.assertEqual(BankMovement.objects.get(source_key=f'invoice:{invoice.pk}').effective_date, invoice.due_date)

    def test_manual_mode_removes_only_automatic_cash_and_preserves_payment_evidence(self):
        purchase = self.make_transaction(payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit)
        sync_user_ledger(self.user, self.cutoff)
        invoice = CardInvoice.objects.get(card=self.credit)
        self.credit.manual_settlement_from = invoice.due_date
        self.credit.save(update_fields=['manual_settlement_from'])
        sync_user_ledger(self.user, self.cutoff)
        invoice.refresh_from_db()
        self.assertTrue(invoice.manual_settlement)
        self.assertFalse(BankMovement.objects.filter(source_key=f'invoice:{invoice.pk}').exists())
        payment = save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=self.account, amount=Decimal('25'), date=date(2026, 2, 1)))
        payment_values = InvoicePayment.objects.filter(pk=payment.pk).values().get()
        purchase.delete()
        sync_user_ledger(self.user, self.cutoff, projection_months=0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount, Decimal('0'))
        self.assertEqual(InvoicePayment.objects.filter(pk=payment.pk).values().get(), payment_values)
        self.assertEqual(BankMovement.objects.get(source_key=f'invoice-payment:{payment.pk}').amount, Decimal('25'))

    def test_shorter_horizon_preserves_paid_invoice_actual_source_total(self):
        self.credit.manual_settlement_from = date(2026, 1, 1)
        self.credit.save(update_fields=['manual_settlement_from'])
        self.make_transaction(payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit, date=date(2026, 11, 1))
        sync_user_ledger(self.user, date(2026, 12, 31))
        invoice = CardInvoice.objects.get(card=self.credit)
        # The model forbids future confirmed payment dates; use an existing
        # historical date to exercise retention independently of cutoff policy.
        save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=self.account, amount=Decimal('25'), date=date(2026, 1, 1)))
        sync_user_ledger(self.user, date(2026, 1, 1), projection_months=0)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount, Decimal('120'))
        self.assertEqual(invoice.payments.count(), 1)
