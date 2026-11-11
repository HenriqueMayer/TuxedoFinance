"""Loyalty operations of the API: points and miles in the Wallet.

An operation reads a schema and calls ``banking.loyalty``.
"""

import datetime as dt
from decimal import Decimal
from typing import Literal

from django.core.exceptions import ValidationError
from ninja import Router, Schema

from banking import loyalty
from banking.models import BankAccount, LoyaltyEntry, LoyaltyProgram
from config import clock
from config.ownership import owned, owned_choice
from config.validation import renamed

router = Router()


class ProgramOut(Schema):
    id: int
    name: str
    #: What the program counts, as the owner named it: points, miles.
    unit_name: str
    balance: Decimal


class EntryOut(Schema):
    id: int
    #: REDEEMED: points that became money in an account.
    kind: Literal["EARNED", "USED", "EXPIRED", "REDEEMED"]
    amount: Decimal
    date: dt.date
    notes: str
    #: For a redemption: the money, its currency and the account that received it.
    cash_amount: Decimal | None
    cash_currency: str | None
    account_name: str | None
    undoable: bool


class ProgramDetailOut(ProgramOut):
    entries: list[EntryOut]


class ProgramIn(Schema):
    name: str
    unit_name: str = ""


class EntryIn(Schema):
    kind: Literal["EARNED", "USED", "EXPIRED"]
    amount: Decimal
    date: dt.date | None = None  # Today when omitted.
    notes: str = ""


class RedemptionIn(Schema):
    points: Decimal
    #: The account that receives the money.
    account_id: int
    amount: Decimal
    date: dt.date | None = None  # Today when omitted.
    notes: str = ""


class Created(Schema):
    id: int


@router.get("/programs", response=list[ProgramOut], summary="List the loyalty programs")
def list_programs(request):
    return loyalty.overview(request.user)


@router.post("/programs", response=Created, summary="Create a loyalty program")
def create_program(request, payload: ProgramIn):
    program = loyalty.save_program(request.user, name=payload.name, unit_name=payload.unit_name)
    return {"id": program.pk}


@router.get("/programs/{program_id}", response=ProgramDetailOut, summary="Read a loyalty program")
def read_program(request, program_id: int):
    return loyalty.detail(owned(LoyaltyProgram, request.user, program_id))


@router.put("/programs/{program_id}", response=Created, summary="Rename a loyalty program")
def update_program(request, program_id: int, payload: ProgramIn):
    program = owned(LoyaltyProgram, request.user, program_id)
    loyalty.save_program(
        request.user, name=payload.name, unit_name=payload.unit_name, program=program
    )
    return {"id": program.pk}


@router.delete(
    "/programs/{program_id}", response={204: None}, summary="Delete a program without entries"
)
def delete_program(request, program_id: int):
    loyalty.delete_program(owned(LoyaltyProgram, request.user, program_id))
    return 204, None


@router.post(
    "/programs/{program_id}/entries",
    response=Created,
    summary="Record points earned, used or expired",
)
def record_entry(request, program_id: int, payload: EntryIn):
    program = owned(LoyaltyProgram, request.user, program_id)
    entry = loyalty.record_entry(
        program,
        kind=payload.kind,
        amount=payload.amount,
        date=payload.date or clock.today(),
        notes=payload.notes,
    )
    return {"id": entry.pk}


@router.post(
    "/programs/{program_id}/redemptions",
    response=Created,
    summary="Redeem points for money in an account",
)
def redeem(request, program_id: int, payload: RedemptionIn):
    program = owned(LoyaltyProgram, request.user, program_id)
    account = owned_choice(BankAccount, request.user, payload.account_id, "account_id")
    try:
        redemption = loyalty.redeem(
            program,
            points=payload.points,
            account=account,
            amount=payload.amount,
            date=payload.date or clock.today(),
            notes=payload.notes,
        )
    except ValidationError as error:
        raise renamed(error, {"target_amount": "amount", "target_account": "account_id"}) from None
    return {"id": redemption.pk}


@router.delete("/entries/{entry_id}", response={204: None}, summary="Undo a loyalty entry")
def undo_entry(request, entry_id: int):
    entry = owned(LoyaltyEntry, request.user, entry_id, select_related=("program",))
    loyalty.undo_entry(entry)
    return 204, None
