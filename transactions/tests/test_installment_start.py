# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Opening imports keep remaining installments without inventing old cash."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from banking.models import BankMovement, CardInvoice
from dashboard.wealth import card_debt
from transactions.forms import TransactionForm
from transactions.models import Transaction
from transactions.projection import occurrence_months
from transactions.services import sync_user_ledger
from transactions.tests.fixtures import TransactionFixture


class InstallmentStartTests(TransactionFixture):
    def purchase(self, **overrides):
        values = dict(payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit,
                      amount=Decimal('1200.00'), installments=12, installment_start=9,
                      date=date(2026, 2, 18))
        values.update(overrides)
        return self.make_transaction(**values)

    def test_only_remaining_installments_are_projected_with_original_numbering(self):
        item = self.purchase()
        self.assertEqual(list(occurrence_months(item, date(2027, 2, 1))),
                         [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)])
        self.assertEqual(item.amount_for_month(2026, 9), 0)
        self.assertEqual(item.amount_for_month(2026, 10), Decimal('100.00'))
        self.assertEqual(item.months_from_start(2026, 10) + 1, 9)
        self.assertEqual(item.amount_through_month(2027, 1), Decimal('400.00'))
        self.assertEqual(item.amount_through_month(2026, 9), 0)

    def test_sync_does_not_recreate_previously_paid_invoices_or_movements(self):
        self.purchase()
        sync_user_ledger(self.user, date(2026, 10, 20))
        self.assertFalse(CardInvoice.objects.filter(reference_month__lt=date(2026, 10, 1)).exists())
        self.assertFalse(BankMovement.objects.filter(effective_date__lt=date(2026, 10, 1)).exists())
        self.assertEqual(card_debt(self.user, date(2026, 9, 30)), [])
        self.assertEqual(sum((row['amount'] for row in card_debt(self.user, date(2026, 10, 20))), Decimal(0)), Decimal('400.00'))
        before = list(CardInvoice.objects.values())
        sync_user_ledger(self.user, date(2026, 10, 20))
        self.assertEqual(before, list(CardInvoice.objects.values()))

    def test_final_installment_remains_an_installment_plan(self):
        item = self.purchase(amount=Decimal('195.80'), installments=2, installment_start=2, date=date(2026, 9, 11))
        self.assertTrue(item.is_installment_plan)
        self.assertEqual(item.amount_for_month(2026, 9), 0)
        self.assertEqual(item.amount_for_month(2026, 10), Decimal('97.90'))
        self.assertEqual(item.amount_for_month(2026, 11), 0)

    def test_omitted_first_rounding_remainder_is_not_charged_again(self):
        item = self.purchase(amount=Decimal('100.00'), installments=3, installment_start=2, date=date(2026, 9, 11))
        self.assertEqual(item.amount_through_month(2026, 12), Decimal('66.66'))
        self.assertEqual(item.amount_for_month(2026, 10), Decimal('33.33'))
        item.installment_start = 1
        self.assertEqual(item.amount_through_month(2026, 12), Decimal('100.00'))

    def test_range_and_recurrence_are_validated(self):
        item = self.purchase()
        item.installment_start = 13
        with self.assertRaises(ValidationError):
            item.full_clean()
        item.installment_start = 2
        item.is_fixed = True
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_legacy_post_preserves_reviewed_start_and_invalid_input_remains_recoverable(self):
        item = self.purchase()
        payload = dict(title=item.title, amount=str(item.amount), transaction_type='EXPENSE',
                       category=self.category.pk, payment_channel='CREDIT_CARD', credit_card=self.credit.pk,
                       installments='12', date='18/02/2026')
        form = TransactionForm(data=payload, instance=item, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['installment_start'], 9)
        payload['installment_start'] = '13'
        form = TransactionForm(data=payload, instance=item, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('installment_start', form.errors)

    def test_monthly_consultation_and_export_skip_old_installments(self):
        self.purchase()
        self.client.force_login(self.user)
        old = self.client.get(reverse('transactions:list'), {'month': '2026-09'})
        self.assertNotContains(old, 'Tracking installments 9')
        current = self.client.get(reverse('transactions:list'), {'month': '2026-10'})
        self.assertContains(current, 'Tracking installments 9')
        response = self.client.get(reverse('transactions:export'))
        self.assertIn('installment_start', response.content.decode())
