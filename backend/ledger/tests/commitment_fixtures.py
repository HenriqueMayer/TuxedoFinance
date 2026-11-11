"""Shared fixture of the R4 model, service and read tests (recurring commitments).

One owner with an account, a debit card, two credit cards and recurring
sources, and a second owner. The clock is fixed: ``TODAY`` is 2026-10-20 in
the default financial time zone (America/Sao_Paulo). All values are synthetic.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import UserPreference
from banking.models import Bank, BankAccount, CreditCard, DebitCard
from config import clock
from ledger.categories import Category
from ledger.models import Transaction

D = Decimal
NOW = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
TODAY = clock.local_date(NOW)
OPENING = date(2026, 1, 1)


def clean_save(instance):
    instance.full_clean()
    instance.save()
    return instance


class CommitmentFixture(TestCase):
    """Owner ``user`` with recurring sources ``rent`` (account), ``salary`` (income) and ``gym`` (card)."""

    @classmethod
    def setUpClass(cls):
        clock_patch = patch("django.utils.timezone.now", return_value=NOW)
        clock_patch.start()
        cls.addClassCleanup(clock_patch.stop)
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.user = users.create_user("commitment-owner", password="test")
        cls.other = users.create_user("commitment-other", password="test")
        UserPreference.objects.create(user=cls.user, base_currency="BRL", date_format="DMY")
        cls.expense = Category.objects.create(
            user=cls.user, name="Housing", transaction_type="EXPENSE"
        )
        cls.leisure = Category.objects.create(
            user=cls.user, name="Leisure", transaction_type="EXPENSE"
        )
        cls.income = Category.objects.create(
            user=cls.user, name="Salary", transaction_type="INCOME"
        )
        cls.bank = Bank.objects.create(user=cls.user, name="Commitment bank")
        cls.account = clean_save(
            BankAccount(
                user=cls.user,
                bank=cls.bank,
                name="Checking",
                currency="BRL",
                opening_balance=D("1000.00"),
                opening_date=OPENING,
            )
        )
        cls.debit = clean_save(DebitCard(user=cls.user, account=cls.account, name="Debit"))
        # Closing day 10, due day 17: each statement is due in its own month.
        cls.card = clean_save(
            CreditCard(user=cls.user, account=cls.account, name="Card", closing_day=10, due_day=17)
        )
        cls.rent = cls.source("Rent", "100.00", "ACCOUNT", date(2026, 1, 10))
        cls.salary = cls.source(
            "Pay", "1000.00", "ACCOUNT", date(2026, 1, 5), kind="INCOME", category=cls.income
        )
        # Day 20 is after the closing day 10: offset 0 is the February statement.
        cls.gym = cls.source("Gym", "50.00", "CREDIT_CARD", date(2026, 1, 20))
        other_bank = Bank.objects.create(user=cls.other, name="Other bank")
        other_account = clean_save(
            BankAccount(user=cls.other, bank=other_bank, name="Other", currency="BRL")
        )
        other_category = Category.objects.create(
            user=cls.other, name="Other", transaction_type="EXPENSE"
        )
        cls.foreign = clean_save(
            Transaction(
                user=cls.other,
                title="Other rent",
                amount=D("70.00"),
                transaction_type="EXPENSE",
                category=other_category,
                payment_channel="ACCOUNT",
                bank_account=other_account,
                date=date(2026, 1, 10),
                is_fixed=True,
            )
        )

    @classmethod
    def source(
        cls, title, amount, channel, day, *, kind="EXPENSE", category=None, is_fixed=True, **values
    ):
        instruments = {
            "ACCOUNT": {"bank_account": cls.account},
            "DEBIT_CARD": {"debit_card": cls.debit},
            "CREDIT_CARD": {"credit_card": cls.card},
        }
        return clean_save(
            Transaction(
                user=cls.user,
                title=title,
                amount=D(amount),
                transaction_type=kind,
                category=category or cls.expense,
                payment_channel=channel,
                date=day,
                is_fixed=is_fixed,
                **{**instruments[channel], **values},
            )
        )

    def fresh(self, item):
        return Transaction.objects.select_related(
            "bank_account", "debit_card__account", "credit_card__account"
        ).get(pk=item.pk)
