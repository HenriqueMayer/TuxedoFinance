"""Banking operations of the API.

Part 2 exposes what an entry needs: the instruments, and the creation of a
first account and card. The Wallet part adds the remaining operations.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from django.db import transaction
from ninja import Router, Schema

from banking.instruments import instruments_of
from banking.models import Bank, BankAccount, CreditCard, DebitCard
from config.currencies import CURRENCIES
from config.ownership import owned_choice

router = Router()

CurrencyCode = Literal[tuple(CURRENCIES)]


class InstrumentOut(Schema):
    id: str
    kind: Literal["account", "debit", "credit"]
    name: str
    bank_name: str
    account_name: str
    currency: str
    color: str


class AccountIn(Schema):
    bank_name: str
    name: str
    currency: CurrencyCode = "BRL"
    opening_balance: Decimal = Decimal("0")
    opening_date: date | None = None


class CardIn(Schema):
    account: str  # An instrument id of kind "account".
    name: str


class CreditCardIn(CardIn):
    closing_day: int
    due_day: int


@router.get("/instruments", response=list[InstrumentOut], summary="List accounts and cards")
def list_instruments(request):
    return instruments_of(request.user)


@router.post("/accounts", response=InstrumentOut, summary="Create an account")
@transaction.atomic
def create_account(request, payload: AccountIn):
    # One step for the owner: a bank with this name is reused or created.
    bank_name = payload.bank_name.strip()
    bank = Bank.objects.filter(user=request.user, name__iexact=bank_name).first()
    if bank is None:
        bank = Bank(user=request.user, name=bank_name)
        bank.full_clean()
        bank.save()
    account = BankAccount(
        user=request.user,
        bank=bank,
        name=payload.name.strip(),
        currency=payload.currency,
        opening_balance=payload.opening_balance,
        opening_date=payload.opening_date,
    )
    account.full_clean()
    account.save()
    return next(item for item in instruments_of(request.user) if item.id == f"account:{account.pk}")


def _account_of(user, instrument_id):
    kind, _separator, pk = instrument_id.partition(":")
    return owned_choice(
        BankAccount, user, pk if kind == "account" and pk.isdecimal() else None, "account"
    )


def _card_out(user, kind, card):
    return next(item for item in instruments_of(user) if item.id == f"{kind}:{card.pk}")


@router.post("/credit-cards", response=InstrumentOut, summary="Create a credit card")
@transaction.atomic
def create_credit_card(request, payload: CreditCardIn):
    card = CreditCard(
        user=request.user,
        account=_account_of(request.user, payload.account),
        name=payload.name.strip(),
        closing_day=payload.closing_day,
        due_day=payload.due_day,
    )
    card.full_clean()
    card.save()
    return _card_out(request.user, "credit", card)


@router.post("/debit-cards", response=InstrumentOut, summary="Create a debit card")
@transaction.atomic
def create_debit_card(request, payload: CardIn):
    card = DebitCard(
        user=request.user,
        account=_account_of(request.user, payload.account),
        name=payload.name.strip(),
    )
    card.full_clean()
    card.save()
    return _card_out(request.user, "debit", card)
