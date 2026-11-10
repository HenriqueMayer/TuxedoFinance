"""Investment operations of the API: the positions in the Wallet.

A position is one investment of the owner: an asset and the product that
holds it. Its id is the id of the asset. An operation reads a schema and
calls ``investments.operations``; values are read from
``investments.portfolio``.
"""

import datetime as dt
from decimal import Decimal
from typing import Literal

from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils.translation import gettext as _
from ninja import Router, Schema

from banking.models import Bank, BankAccount
from config import clock
from config.currencies import CURRENCIES
from config.ownership import owned, owned_choice
from config.validation import renamed
from investments import operations, portfolio
from investments.models import Asset, Investment, InvestmentProduct

router = Router()

CurrencyCode = Literal[tuple(CURRENCIES)]
ValuationMode = Literal["MONETARY", "UNITS"]


class PositionOut(Schema):
    id: int
    name: str
    institution_id: int
    institution_name: str
    currency: str
    #: MONETARY: a balance. UNITS: a quantity with a unit price.
    valuation_mode: ValuationMode
    purpose: Literal["INVESTMENT", "MONTHLY_CASH"]
    is_archived: bool
    #: What the position is worth today, in its currency.
    value: Decimal
    #: The same value in the base currency. Null without an exchange rate.
    base_value: Decimal | None
    quantity: Decimal | None
    cost: Decimal
    gain: Decimal | None
    yields: Decimal
    unit_price: Decimal | None
    price_date: dt.date | None
    #: False: units are held and no price was recorded, so the value is the cost.
    has_price: bool


class OverviewOut(Schema):
    positions: list[PositionOut]
    currency: str
    total: Decimal
    complete: bool
    missing_currencies: list[str]


class OpeningOut(Schema):
    date: dt.date | None
    value: Decimal
    quantity: Decimal | None


class OperationOut(Schema):
    id: int
    kind: Literal["DEPOSIT", "WITHDRAWAL", "YIELD"]
    date: dt.date
    value: Decimal
    quantity: Decimal | None
    unit_price: Decimal | None
    account_name: str


class PositionDetailOut(PositionOut):
    today: dt.date
    opening: OpeningOut | None
    operations: list[OperationOut]


class PositionIn(Schema):
    name: str
    #: An existing institution of the owner. Without it, ``institution_name`` names one.
    institution_id: int | None = None
    institution_name: str = ""
    currency: CurrencyCode = "BRL"
    valuation_mode: ValuationMode = "MONETARY"
    #: What the position already held before the first recorded operation.
    opening_balance: Decimal = Decimal("0")
    opening_quantity: Decimal = Decimal("0")
    opening_unit_price: Decimal = Decimal("0")
    opening_date: dt.date | None = None


class PositionEdit(Schema):
    name: str
    is_archived: bool = False


class OperationIn(Schema):
    kind: Literal["DEPOSIT", "WITHDRAWAL", "YIELD"]
    date: dt.date | None = None
    #: The account that pays a deposit or receives a withdrawal.
    account_id: int | None = None
    #: For a balance position.
    amount: Decimal | None = None
    #: For a position in units.
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    #: The money that moved in the account, when it is not quantity times price.
    cash_amount: Decimal | None = None


class ValueIn(Schema):
    #: The balance of today, or the unit price of today for a position in units.
    value: Decimal


class Created(Schema):
    id: int


def _position(user, position_id):
    """Return the owned asset of a position, or 404."""
    asset = owned(Asset, user, position_id, select_related=("opening_product__bank",))
    if asset.opening_product_id is None:
        raise Http404
    return asset


def _name(value, user, bank, *, except_product=None):
    """Return the stripped name, or raise when it is empty or taken at ``bank``."""
    name = value.strip()
    if not name:
        raise ValidationError({"name": _("Enter a name.")})
    taken = InvestmentProduct.objects.filter(user=user, bank=bank, name__iexact=name)
    if except_product is not None:
        taken = taken.exclude(pk=except_product.pk)
    if bank is not None and taken.exists():
        raise ValidationError(
            {"name": _("An investment with this name already exists at this institution.")}
        )
    return name


@router.get("/positions", response=OverviewOut, summary="List the investments and their total")
def list_positions(request):
    return portfolio.overview(request.user)


@router.post("/positions", response=Created, summary="Create an investment")
def create_position(request, payload: PositionIn):
    user = request.user
    if payload.institution_id is not None:
        bank = owned_choice(Bank, user, payload.institution_id, "institution_id")
    else:
        typed = payload.institution_name.strip()
        if not typed:
            raise ValidationError({"institution_name": _("Enter the institution.")})
        # A typed name of an existing institution means that institution.
        bank = Bank.objects.filter(user=user, name__iexact=typed).first()
    name = _name(payload.name, user, bank)
    has_opening = any(
        (payload.opening_balance, payload.opening_quantity, payload.opening_unit_price)
    )
    try:
        asset = operations.create_position(
            user,
            name=name,
            currency=payload.currency,
            valuation_mode=payload.valuation_mode,
            institution=bank,
            institution_name=payload.institution_name.strip(),
            opening_balance=payload.opening_balance,
            opening_quantity=payload.opening_quantity,
            opening_unit_price=payload.opening_unit_price,
            opening_date=(payload.opening_date or clock.today()) if has_opening else None,
        )
    except ValidationError as error:
        raise renamed(error, {"opening_product": None}) from None
    return {"id": asset.pk}


@router.get("/positions/{position_id}", response=PositionDetailOut, summary="Read an investment")
def read_position(request, position_id: int):
    return portfolio.detail(_position(request.user, position_id))


@router.put("/positions/{position_id}", response=Created, summary="Rename or archive an investment")
def update_position(request, position_id: int, payload: PositionEdit):
    asset = _position(request.user, position_id)
    product = asset.opening_product
    name = _name(payload.name, request.user, product.bank, except_product=product)
    if name != asset.name or name != product.name:
        operations.rename_position(asset, name)
    if payload.is_archived != asset.is_archived:
        operations.set_archived(asset, payload.is_archived)
    return {"id": asset.pk}


@router.delete(
    "/positions/{position_id}",
    response={204: None},
    summary="Delete an investment that has no operation",
)
def delete_position(request, position_id: int):
    operations.delete_position(_position(request.user, position_id))
    return 204, None


@router.post(
    "/positions/{position_id}/value",
    response=Created,
    summary="Record what an investment is worth today",
)
def set_value(request, position_id: int, payload: ValueIn):
    asset = _position(request.user, position_id)
    operations.set_current_value(request.user, asset, payload.value)
    return {"id": asset.pk}


@router.post(
    "/positions/{position_id}/operations",
    response=Created,
    summary="Record a deposit, a withdrawal or a yield",
)
def record_operation(request, position_id: int, payload: OperationIn):
    user = request.user
    asset = _position(user, position_id)
    if asset.is_archived:
        raise ValidationError(_("This investment is archived. Restore it to record an operation."))
    account = None
    if payload.kind != "YIELD":
        if payload.account_id is None:
            raise ValidationError({"account_id": _("Choose the account.")})
        account = owned_choice(BankAccount, user, payload.account_id, "account_id")
    try:
        operation = operations.record_operation(
            user,
            asset,
            kind=payload.kind,
            date=payload.date or clock.today(),
            amount=payload.amount,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            cash_amount=payload.cash_amount,
            account=account,
        )
    except ValidationError as error:
        raise renamed(
            error,
            {
                "source_account": "account_id",
                "destination_account": "account_id",
                "source_program": None,
                "asset": "__all__",
                # A balance position has one amount; the cash side repeats it.
                **({"cash_amount": "amount"} if asset.valuation_mode == "MONETARY" else {}),
            },
        ) from None
    return {"id": operation.pk}


@router.delete(
    "/operations/{operation_id}",
    response={204: None},
    summary="Delete an operation of an investment",
)
def delete_operation(request, operation_id: int):
    operations.delete_operation(owned(Investment, request.user, operation_id))
    return 204, None
