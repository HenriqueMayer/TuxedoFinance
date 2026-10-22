# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bound recurring work without discarding legitimate financial history."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from banking.models import BankMovement, CardInvoice, LoyaltyEntry, LoyaltyProgram
from transactions.forms import TransactionForm
from transactions.models import Transaction
from transactions.services import sync_user_ledger
from transactions.tests.fixtures import TransactionFixture


class RecurrenceProjectionTests(TransactionFixture):
    def test_extreme_open_ended_recurrence_is_rejected_for_every_instrument(self):
        for channel, instrument in (
            ('ACCOUNT', {'bank_account': self.account.pk}),
            ('PIX', {'bank_account': self.account.pk}),
            ('DEBIT_CARD', {'debit_card': self.debit.pk}),
            ('CREDIT_CARD', {'credit_card': self.credit.pk}),
        ):
            with self.subTest(channel=channel):
                form = TransactionForm(data={
                    'title': 'Extreme recurrence', 'amount': '10',
                    'transaction_type': 'EXPENSE', 'category': self.category.pk,
                    'payment_channel': channel, 'date': '0001-01-01',
                    'is_fixed': 'on', 'installments': '1', **instrument,
                }, user=self.user)
                self.assertFalse(form.is_valid())
                self.assertIn('date', form.errors)
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_model_validation_rejects_extreme_open_ended_recurrence(self):
        item = self.make_transaction(date=date.min, is_fixed=True)
        with self.assertRaises(ValidationError) as error:
            item.full_clean()
        self.assertIn('date', error.exception.message_dict)

    def test_native_post_rejects_extreme_recurrence_without_creating_records(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('transactions:create'), {
            'title': 'Do not materialize', 'amount': '10',
            'transaction_type': 'EXPENSE', 'category': self.category.pk,
            'payment_channel': 'ACCOUNT', 'bank_account': self.account.pk,
            'date': '0001-01-01', 'is_fixed': 'on', 'installments': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('date', response.context['form'].errors)
        self.assertEqual(response.context['form']['title'].value(), 'Do not materialize')
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_portuguese_post_explains_the_limit_without_saving(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('transactions:create'), {
            'title': 'Histórico preservado', 'amount': '10',
            'transaction_type': 'EXPENSE', 'category': self.category.pk,
            'payment_channel': 'ACCOUNT', 'bank_account': self.account.pk,
            'date': '0001-01-01', 'is_fixed': 'on', 'installments': '1',
        }, HTTP_ACCEPT_LANGUAGE='pt-BR')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ocorrências mensais. Revise as datas de início e término.')
        self.assertIn('date', response.context['form'].errors)
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_ancient_short_ended_recurrence_keeps_all_three_occurrences(self):
        item = self.make_transaction(date=date.min, is_fixed=True,
            fixed_until=date(1, 3, 1), amount=Decimal('10'))
        item.full_clean()
        sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        movements = BankMovement.objects.filter(user=self.user).order_by('effective_date')
        self.assertEqual(list(movements.values_list('effective_date', 'amount')), [
            (date(1, 1, 1), Decimal('10')),
            (date(1, 2, 1), Decimal('10')),
            (date(1, 3, 1), Decimal('10')),
        ])
        original = list(movements.values())
        sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        self.assertEqual(original, list(movements.values()))

    def test_ancient_card_recurrence_preserves_shifted_final_bill(self):
        item = self.make_transaction(date=date(1, 1, 31), is_fixed=True,
            fixed_until=date(1, 3, 1), amount=Decimal('10'),
            payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit)
        item.full_clean()
        sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        self.assertEqual(list(CardInvoice.objects.filter(card=self.credit)
            .order_by('reference_month').values_list('reference_month', 'amount')), [
                (date(1, 2, 1), Decimal('10')),
                (date(1, 3, 1), Decimal('10')),
                (date(1, 4, 1), Decimal('10')),
            ])

    def test_ancient_one_off_card_and_loyalty_purchase_keep_exact_amounts(self):
        self.make_transaction(date=date.min, amount=Decimal('12.34'),
            payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit)
        program = LoyaltyProgram.objects.create(user=self.user, name='Historic points')
        LoyaltyEntry.objects.create(user=self.user, program=program,
            direction='CREDIT', kind='PURCHASE', amount=Decimal('1000'),
            cash_amount=Decimal('25'), funding_credit_card=self.credit, date=date(1, 2, 1))
        sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        self.assertEqual(list(CardInvoice.objects.filter(card=self.credit)
            .order_by('reference_month').values_list('reference_month', 'amount')), [
                (date(1, 1, 1), Decimal('12.34')),
                (date(1, 2, 1), Decimal('25')),
            ])
