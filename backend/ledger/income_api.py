"""Operations of the recurring incomes. The rules are in ``ledger.incomes``."""

import datetime as dt
from decimal import Decimal

from django.db import transaction
from ninja import Router, Schema

from banking.models import BankAccount
from config import clock
from config.ownership import owned, owned_choice
from ledger import incomes
from ledger.categories import Category
from ledger.models import RecurringIncome

router = Router()


class PartIn(Schema):
    #: The entry of an existing part. Without it the part is new.
    id: int | None = None
    day: int
    amount: Decimal


class IncomeIn(Schema):
    name: str
    category_id: int
    account_id: int
    #: The first month, for a new income. The current month when omitted.
    start: dt.date | None = None
    #: The last month, or null for an income without an end.
    until: dt.date | None = None
    #: The owner confirms each receipt; an unconfirmed one does not change the balance.
    confirm: bool = False
    #: What the owner typed to calculate the parts of a CLT salary.
    gross: Decimal | None = None
    advance_percent: Decimal | None = None
    parts: list[PartIn]


class PartOut(Schema):
    #: The repeating entry of the part. Its months are in its monthly schedule.
    id: int
    day: int
    #: The amount of the next receipt.
    amount: Decimal
    next_date: dt.date | None


class Named(Schema):
    id: int
    name: str


class IncomeAccount(Named):
    bank_name: str

    @staticmethod
    def resolve_bank_name(account):
        return account.bank.name


class IncomeOut(Schema):
    id: int
    name: str
    category: Named
    account: IncomeAccount
    currency: str
    until: dt.date | None
    confirm: bool
    gross: Decimal | None
    advance_percent: Decimal | None
    #: The parts of one month added.
    total: Decimal
    parts: list[PartOut]


class CurrencyAmount(Schema):
    currency: str
    amount: Decimal


class IncomesOut(Schema):
    items: list[IncomeOut]
    #: What the incomes add in one month, by currency of their account.
    totals: list[CurrencyAmount]


def _values(user, payload: IncomeIn):
    values = payload.model_dump()
    values["account"] = owned_choice(
        BankAccount, user, payload.account_id, "account_id", select_related=("bank",)
    )
    values["category"] = owned_choice(Category, user, payload.category_id, "category_id")
    return values


def _income(user, income_id):
    return owned(RecurringIncome, user, income_id)


def _out(income):
    income = RecurringIncome.objects.prefetch_related(
        "parts__bank_account__bank", "parts__category"
    ).get(pk=income.pk)
    return incomes.describe(income, clock.today())


@router.get("", response=IncomesOut, summary="List the recurring incomes")
def list_incomes(request):
    return incomes.listing(request.user, clock.today())


@router.post("", response=IncomeOut, summary="Create a recurring income with its parts")
@transaction.atomic
def create_income(request, payload: IncomeIn):
    values = _values(request.user, payload)
    return _out(incomes.create(request.user, values, today=clock.today()))


@router.get("/{income_id}", response=IncomeOut, summary="Read a recurring income")
def read_income(request, income_id: int):
    return _out(_income(request.user, income_id))


@router.put("/{income_id}", response=IncomeOut, summary="Change a recurring income and its parts")
@transaction.atomic
def change_income(request, income_id: int, payload: IncomeIn):
    income = _income(request.user, income_id)
    values = _values(request.user, payload)
    return _out(incomes.change(income, values, today=clock.today()))


@router.delete(
    "/{income_id}",
    response={204: None},
    summary="Delete a recurring income with every entry of its parts",
)
@transaction.atomic
def delete_income(request, income_id: int):
    _income(request.user, income_id).delete()
    return 204, None
