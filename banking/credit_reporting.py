# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read-only expense occurrences for invoice credits, never bank transactions.

Credits reduce expense reports in their explicit statement month. Their posting
date still controls realized cutoffs, independently of that reference month.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.urls import reverse

from banking.models import CardInvoiceCredit


ZERO = Decimal('0.00')


@dataclass(frozen=True)
class InvoiceCreditOccurrence:
    credit: CardInvoiceCredit

    transaction_type = 'EXPENSE'
    payment_channel = 'CREDIT_CARD'
    is_fixed = False
    is_installment_plan = False
    is_credit_card = True
    installments = 1
    bank_account = None
    bank_account_id = None
    debit_card = None
    debit_card_id = None
    reward_redemption_id = None

    @property
    def pk(self):
        return self.credit.pk

    @property
    def user_id(self):
        return self.credit.user_id

    @property
    def title(self):
        return self.credit.title

    display_title = title

    @property
    def date(self):
        return self.credit.date

    @property
    def category(self):
        return self.credit.category

    @property
    def credit_card(self):
        return self.credit.card

    @property
    def credit_card_id(self):
        return self.credit.card_id

    @property
    def payment_account(self):
        return self.credit.card.account

    @property
    def native_currency(self):
        return self.payment_account.currency

    @property
    def source_key(self):
        # A credit PK can equal a Transaction PK; identities must stay separate.
        return f'invoice-credit:{self.pk}'

    @property
    def source_url(self):
        return reverse('banking:invoice_credit_edit', args=[self.pk])

    def amount_for_month(self, year, month):
        return -self.credit.amount if (year, month) == (
            self.credit.reference_month.year, self.credit.reference_month.month,
        ) else ZERO

    def category_allocations_for_month(self, year, month):
        amount = self.amount_for_month(year, month)
        return [(self.category, amount)] if amount else []


def invoice_credit_occurrences(user):
    return [InvoiceCreditOccurrence(credit) for credit in
            CardInvoiceCredit.objects.filter(user=user).select_related(
                'category', 'card__account__bank',
            )]
