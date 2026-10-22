"""Shared illustrated instruments preserve native financial form contracts.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.translation import override

from banking.forms import (BankTransferForm, CreditCardForm, DebitCardForm,
    InvoicePaymentForm, LoyaltyEntryForm, LoyaltyProgramForm, RewardRedemptionForm)
from banking.models import Bank, BankAccount, CardInvoice, CreditCard, LoyaltyProgram
from pages.templatetags.form_ui import form_control


class LoyaltyInstrumentPresentationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('loyalty-presentation')
        self.other = get_user_model().objects.create_user('loyalty-private')
        self.bank = Bank.objects.create(user=self.user, name='Cedar bank', color='#315D50')
        self.account = BankAccount.objects.create(pk=1201, user=self.user, bank=self.bank,
            name='Daily account', currency='BRL', opening_balance='5000', opening_date=date(2020, 1, 1))
        self.card = CreditCard.objects.create(pk=1301, user=self.user, account=self.account,
            name='Travel credit', color='#5B3E7C', gradient_end='#C6A173', gradient_angle=45,
            closing_day=20, due_day=28)
        self.card_two = CreditCard.objects.create(user=self.user, account=self.account,
            name='Daily credit', closing_day=20, due_day=28)
        private_bank = Bank.objects.create(user=self.other, name='Private bank')
        self.private_account = BankAccount.objects.create(user=self.other, bank=private_bank,
            name='Private account', currency='BRL')
        self.private_card = CreditCard.objects.create(user=self.other, account=self.private_account,
            name='Private card', closing_day=20, due_day=28)
        self.program = LoyaltyProgram.objects.create(user=self.user, bank=self.bank, name='Travel points')
        self.invoice = CardInvoice.objects.create(user=self.user, card=self.card,
            reference_month=date.today().replace(day=1), due_date=date.today() + timedelta(days=30),
            amount=100, manual_settlement=True)

    def test_program_multiple_has_saved_card_artwork_complete_labels_and_unlocalized_ids(self):
        self.program.cards.set([self.card])
        form = LoyaltyProgramForm(instance=self.program, user=self.user)
        with override('pt-br'), self.assertNumQueries(1):
            rendered = str(form_control(form['cards']))
        for expected in ['multiple', 'data-payment-choices="true"', 'data-payment-kind="card"',
                'data-card-color="#5B3E7C"', 'data-card-gradient-end="#C6A173"',
                'data-card-gradient-angle="45"', 'value="1301" selected',
                'Travel credit - Cedar bank &gt; Daily account (BRL)']:
            self.assertIn(expected, rendered)
        self.assertNotIn('Private card', rendered)
        self.assertNotIn('1.301', rendered)

    def test_every_bank_instrument_selector_uses_the_shared_board_without_extra_lookups(self):
        cases = [(CreditCardForm(user=self.user), ['account']),
            (DebitCardForm(user=self.user), ['account']),
            (BankTransferForm(user=self.user), ['source_account', 'destination_account']),
            (InvoicePaymentForm(user=self.user, invoice=self.invoice), ['account']),
            (LoyaltyEntryForm(user=self.user), ['funding_account', 'funding_credit_card', 'invoice']),
            (RewardRedemptionForm(user=self.user), ['target_account', 'iof_account', 'iof_credit_card'])]
        for form, fields in cases:
            for name in fields:
                with self.subTest(form=type(form).__name__, field=name), self.assertNumQueries(1):
                    rendered = str(form_control(form[name]))
                self.assertIn('data-payment-choices="true"', rendered)
                self.assertIn('data-bank-color="#315D50"', rendered)
                self.assertNotIn('Private', rendered)
                self.assertIn('Cedar bank', rendered)
                if name == 'invoice':
                    self.assertIn(self.invoice.reference_month.strftime('%Y-%m'), rendered)

    def test_program_native_multi_post_preserves_owned_cards_and_rejects_foreign_cards(self):
        values = {'name': 'Native rewards', 'bank': self.bank.pk, 'unit_name': 'Miles',
            'cards': [str(self.card.pk), str(self.card_two.pk)]}
        form = LoyaltyProgramForm(values, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        program = form.save()
        self.assertSetEqual(set(program.cards.values_list('pk', flat=True)), {self.card.pk, self.card_two.pk})
        values.update(name='Forged rewards', cards=[str(self.private_card.pk)])
        forged = LoyaltyProgramForm(values, user=self.user)
        self.assertFalse(forged.is_valid())
        self.assertIn('cards', forged.errors)
        self.assertNotIn('Private card', str(form_control(forged['cards'])))

    def test_invalid_purchase_keeps_selected_card_errors_and_decimal_precision(self):
        values = {'program': self.program.pk, 'direction': 'CREDIT', 'kind': 'PURCHASE',
            'amount': '1234.56', 'funding_credit_card': self.card.pk, 'cash_amount': '-1',
            'date': date.today().isoformat()}
        form = LoyaltyEntryForm(values, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('cash_amount', form.errors)
        self.assertEqual(form['funding_credit_card'].value(), self.card.pk)
        self.assertEqual(form.cleaned_data['amount'], Decimal('1234.56'))
        self.assertNotIn('data-money-input', str(form['amount']))
        self.assertIn('selected', str(form_control(form['funding_credit_card'])))
        values.update(funding_credit_card=self.private_card.pk, cash_amount='25.10')
        forged = LoyaltyEntryForm(values, user=self.user)
        self.assertFalse(forged.is_valid())
        self.assertIn('funding_credit_card', forged.errors)

    def test_redemption_native_fields_keep_owned_choices_and_conflicting_source_errors(self):
        values = {'program': self.program.pk, 'points': '100.25', 'target_account': self.account.pk,
            'target_amount': '12.34', 'iof_amount': '1.25', 'iof_account': self.account.pk,
            'iof_credit_card': self.card.pk, 'date': date.today().isoformat()}
        form = RewardRedemptionForm(values, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)
        self.assertEqual(form['iof_account'].value(), self.account.pk)
        self.assertEqual(form['iof_credit_card'].value(), self.card.pk)
        self.assertNotIn('data-money-input', str(form['points']))
        values.update(iof_account='', iof_credit_card=self.private_card.pk)
        forged = RewardRedemptionForm(values, user=self.user)
        self.assertFalse(forged.is_valid())
        self.assertIn('iof_credit_card', forged.errors)
