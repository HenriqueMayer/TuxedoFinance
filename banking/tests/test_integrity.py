# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Cash conservation and known opening dates at financial write boundaries."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from banking.forms import BankTransferForm
from banking.models import (
    Bank, BankAccount, BankMovement, BankTransfer, CardInvoice, CreditCard,
    InvoicePayment, LoyaltyEntry, LoyaltyProgram, RewardRedemption,
)
from banking.services import (
    account_balances, create_reward_redemption, create_transfer,
    movements_before_opening, update_reward_redemption,
)
from banking.settlements import save_invoice_payment


class CashIntegrityTests(TestCase):
    def setUp(self):
        self.day = date(2026, 1, 15)
        self.user = get_user_model().objects.create_user('cash-integrity')
        self.bank = Bank.objects.create(user=self.user, name='Local bank')
        self.account = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Source', currency='BRL',
            opening_balance=Decimal('1000'), opening_date=self.day,
        )
        self.destination = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Destination', currency='BRL',
            opening_date=self.day,
        )
        self.card = CreditCard.objects.create(
            user=self.user, account=self.account, name='Card', closing_day=10, due_day=20,
        )
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Points')
        LoyaltyEntry.objects.create(
            user=self.user, program=self.program, direction='CREDIT', kind='ADJUSTMENT',
            amount=Decimal('100'), date=self.day,
        )

    def transfer(self, **overrides):
        values = dict(
            user=self.user, source_account=self.account, destination_account=self.destination,
            source_amount=Decimal('100'), destination_amount=Decimal('100'), date=self.day,
        )
        return create_transfer(**(values | overrides))

    def redemption(self, **overrides):
        values = dict(
            user=self.user, program=self.program, points=Decimal('10'),
            target_account=self.destination, target_amount=Decimal('5'), date=self.day,
        )
        return create_reward_redemption(**(values | overrides))

    def test_same_currency_transfer_rejects_gain_or_loss_without_partial_posting(self):
        for received in ('50', '150'):
            with self.subTest(received=received), self.assertRaises(ValidationError) as caught:
                self.transfer(destination_amount=Decimal(received))
            self.assertIn('destination_amount', caught.exception.message_dict)
        self.assertFalse(BankTransfer.objects.exists())
        self.assertFalse(BankMovement.objects.exists())
        self.transfer()
        self.assertEqual(sum((row['balance'] for row in account_balances(self.user, self.day)), Decimal('0')), Decimal('1000'))

    def test_native_transfer_form_retains_error_and_bound_amount(self):
        data = {
            'source_account': self.account.pk, 'destination_account': self.destination.pk,
            'source_amount': '100', 'destination_amount': '150', 'date': self.day.isoformat(),
        }
        form = BankTransferForm(data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('destination_amount', form.errors)
        self.assertEqual(form['destination_amount'].value(), '150')
        self.client.force_login(self.user)
        response = self.client.post(reverse('banking:transfer_create'), data)
        self.assertContains(response, 'Transfers in the same currency require equal')
        self.assertFalse(BankTransfer.objects.exists())
        self.assertFalse(BankMovement.objects.exists())

    def test_cross_currency_transfer_retains_actual_received_amount_and_evidence(self):
        self.destination.currency = 'USD'
        self.destination.save(update_fields=['currency'])
        transfer = self.transfer(destination_amount=Decimal('20'))
        self.assertEqual((transfer.fx_source_currency, transfer.fx_target_currency), ('BRL', 'USD'))
        self.assertEqual(transfer.fx_rate, Decimal('.2'))
        self.assertEqual(transfer.fx_snapshot_status, 'CAPTURED')
        self.assertEqual(transfer.fx_effective_date, self.day)
        self.assertEqual(list(transfer.movements.order_by('direction').values_list('amount', flat=True)), [Decimal('20'), Decimal('100')])

    def test_transfer_checks_both_openings_and_leaves_unknown_baselines_unchanged(self):
        before = self.day - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.transfer(date=before)
        self.account.opening_date = None
        self.account.save(update_fields=['opening_date'])
        with self.assertRaises(ValidationError):
            self.transfer(date=before)
        self.destination.opening_date = None
        self.destination.save(update_fields=['opening_date'])
        self.transfer(date=before)
        self.account.refresh_from_db()
        self.destination.refresh_from_db()
        self.assertIsNone(self.account.opening_date)
        self.assertIsNone(self.destination.opening_date)

    def test_transfer_ownership_is_still_enforced(self):
        other = get_user_model().objects.create_user('private-transfer')
        with self.assertRaises(ValidationError):
            self.transfer(user=other)
        self.assertFalse(BankMovement.objects.exists())

    def test_points_purchase_checks_account_and_card_dates_on_create_and_edit(self):
        self.client.force_login(self.user)
        data = dict(program=self.program.pk, direction='CREDIT', kind='PURCHASE', amount='10',
                    cash_amount='3', date=(self.day - timedelta(days=1)).isoformat())
        for funding in ('funding_account', 'funding_credit_card'):
            instrument = self.account if funding == 'funding_account' else self.card
            with self.subTest(funding=funding):
                response = self.client.post(reverse('banking:entry_create'), data | {funding: instrument.pk})
                self.assertContains(response, 'The operation cannot precede')
        self.assertEqual(LoyaltyEntry.objects.count(), 1)
        self.assertFalse(BankMovement.objects.exists())
        response = self.client.post(reverse('banking:entry_create'), data | {
            'funding_account': self.account.pk, 'date': self.day.isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        entry = LoyaltyEntry.objects.get(kind='PURCHASE')
        movement = entry.funding_movement
        response = self.client.post(reverse('banking:entry_update', args=[entry.pk]), data | {'funding_account': self.account.pk})
        self.assertContains(response, 'The operation cannot precede')
        entry.refresh_from_db()
        movement.refresh_from_db()
        self.assertEqual(entry.date, self.day)
        self.assertEqual(movement.effective_date, self.day)

    def test_redemption_checks_target_and_both_iof_channels_atomically(self):
        before = self.day - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.redemption(date=before)
        self.destination.opening_date = None
        self.destination.save(update_fields=['opening_date'])
        for instrument in ({'iof_account': self.account}, {'iof_credit_card': self.card}):
            with self.subTest(instrument=instrument), self.assertRaises(ValidationError):
                self.redemption(date=before, iof_amount=Decimal('1'), **instrument)
        self.assertFalse(RewardRedemption.objects.exists())
        self.assertEqual(LoyaltyEntry.objects.count(), 1)
        self.assertFalse(BankMovement.objects.exists())
        redemption = self.redemption(iof_amount=Decimal('1'), iof_account=self.account)
        before_movements = list(BankMovement.objects.order_by('pk').values())
        with self.assertRaises(ValidationError):
            update_reward_redemption(
                redemption=redemption, user=self.user, program=self.program, points=Decimal('10'),
                target_account=self.destination, target_amount=Decimal('5'), date=before,
                iof_amount=Decimal('1'), iof_account=self.account,
            )
        redemption.refresh_from_db()
        self.assertEqual(redemption.date, self.day)
        self.assertEqual(before_movements, list(BankMovement.objects.order_by('pk').values()))

    def test_payment_rejects_before_opening_without_changing_prior_confirmation(self):
        invoice = CardInvoice.objects.create(
            user=self.user, card=self.card, reference_month=self.day.replace(day=1),
            due_date=self.day, amount=Decimal('100'), manual_settlement=True,
        )
        payment = InvoicePayment(user=self.user, invoice=invoice, account=self.account,
                                 amount=Decimal('10'), date=self.day - timedelta(days=1))
        with self.assertRaises(ValidationError):
            save_invoice_payment(payment)
        self.assertFalse(InvoicePayment.objects.exists())
        self.assertFalse(BankMovement.objects.exists())
        payment.date = self.day
        save_invoice_payment(payment)
        payment.date -= timedelta(days=1)
        with self.assertRaises(ValidationError):
            save_invoice_payment(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.date, self.day)
        self.assertEqual(payment.movement.effective_date, self.day)

    def test_existing_conflicts_are_owned_read_only_evidence(self):
        legacy = BankMovement.objects.create(
            user=self.user, account=self.account, direction='DEBIT', kind='ADJUSTMENT',
            amount=Decimal('10'), effective_date=self.day - timedelta(days=1),
        )
        BankMovement.objects.create(user=self.user, account=self.account, direction='CREDIT',
                                    kind='ADJUSTMENT', amount=Decimal('5'), effective_date=self.day)
        other = get_user_model().objects.create_user('private-legacy')
        other_bank = Bank.objects.create(user=other, name='Private')
        other_account = BankAccount.objects.create(user=other, bank=other_bank, name='Private',
                                                   currency='BRL', opening_date=self.day)
        BankMovement.objects.create(user=other, account=other_account, direction='DEBIT',
                                    kind='ADJUSTMENT', amount=Decimal('9'), effective_date=self.day - timedelta(days=1))
        before = list(BankMovement.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(list(movements_before_opening(self.user)), [legacy])
        self.assertTrue(all(row['sql'].lstrip().upper().startswith('SELECT') for row in queries))
        self.assertEqual(before, list(BankMovement.objects.order_by('pk').values()))
