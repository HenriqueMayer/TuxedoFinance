"""Validation coverage for transactions."""

from django.core.exceptions import ValidationError
from transactions.models import Transaction
from transactions.tests.fixtures import TransactionFixture


class TransactionValidationTests(TransactionFixture):
    def assert_invalid(self, **overrides):
        item = self.make_transaction()
        for field, value in overrides.items():
            setattr(item, field, value)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_account_and_pix_require_only_account(self):
        for channel in (Transaction.PaymentChannel.ACCOUNT, Transaction.PaymentChannel.PIX):
            item = self.make_transaction(payment_channel=channel)
            item.full_clean()
        self.assert_invalid(payment_channel=Transaction.PaymentChannel.PIX, bank_account=None)

    def test_pix_requires_an_enabled_account(self):
        self.account.pix_enabled = False
        self.account.save(update_fields=['pix_enabled'])

        self.assert_invalid(payment_channel=Transaction.PaymentChannel.PIX)

    def test_debit_card_requires_only_debit_card(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            bank_account=None,
            debit_card=self.debit,
        )
        item.full_clean()
        self.assert_invalid(
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            debit_card=self.debit,
        )

    def test_credit_card_requires_only_credit_card(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
        )
        item.full_clean()
        self.assertTrue(item.is_credit_card)

    def test_every_relation_must_have_same_owner(self):
        self.assert_invalid(bank_account=self.other_account)
        self.assert_invalid(category=self.other_category)
        self.assert_invalid(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.other_credit,
        )

    def test_income_cannot_use_cards(self):
        self.assert_invalid(
            transaction_type=Transaction.TransactionType.INCOME,
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
        )

    def test_installments_and_override_are_credit_only(self):
        self.assert_invalid(installments=2)
        self.assert_invalid(billing_override=Transaction.BillChoice.NEXT)

    def test_fixed_and_installments_are_incompatible(self):
        self.assert_invalid(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
            installments=2,
            is_fixed=True,
        )

    def test_payment_properties(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            bank_account=None,
            debit_card=self.debit,
        )
        self.assertEqual(item.payment_account, self.account)
        self.assertEqual(item.payment_name, 'Daily Debit')
        self.assertEqual(item.payment_label, 'North Bank > Daily / Daily Debit')
