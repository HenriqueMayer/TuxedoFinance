"""Writes on a position: create it, record or delete an operation, set its current value.

A position is one asset in the product that holds it. ``create_position``
creates both together, so ``asset.opening_product`` is the product of the
position and the asset identifies the position.

Each function validates with the models and with the position replay
(``investments.positions``), and keeps the bank side of an operation current
(``investments.services.sync_investment_ledger``).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from config import clock
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation
from investments.positions import validate_position_history
from investments.services import (
    YIELD_INPUT_AMOUNT,
    YIELD_INPUT_ENDING_BALANCE,
    available_quantity,
    available_value,
    calculate_monetary_yield,
    cleanup_investment_ledger,
    create_guided_investment,
    monetary_position_before,
    refresh_fx_snapshot,
    sync_investment_ledger,
)

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")


def create_position(
    user,
    *,
    name,
    currency,
    valuation_mode,
    institution=None,
    institution_name="",
    purpose=InvestmentProduct.Purpose.INVESTMENT,
    opening_balance=ZERO,
    opening_quantity=ZERO,
    opening_unit_price=ZERO,
    opening_date=None,
):
    """Create a position and return its asset.

    ``institution`` is an owned bank; without it, ``institution_name`` names a
    new one. The opening values are what the position held before the first
    recorded operation; they move no money. They need ``opening_date``.
    """
    _product, asset = create_guided_investment(
        user,
        {
            "new_institution": institution is None,
            "institution": institution,
            "institution_name": institution_name,
            "name": name,
            "code": "",
            "purpose": purpose,
            "currency": currency,
            "valuation_mode": valuation_mode,
            "opening_balance": opening_balance,
            "opening_quantity": opening_quantity,
            "opening_unit_price": opening_unit_price,
            "opening_date": opening_date,
            "planning_enabled": True,
        },
    )
    return asset


@transaction.atomic
def rename_position(asset, name):
    """Give the position, and the product that holds it, the name ``name``."""
    product = asset.opening_product
    product.name = asset.name = name
    product.full_clean()
    asset.full_clean()
    product.save(update_fields=["name", "updated_at"])
    asset.save(update_fields=["name", "updated_at"])
    return asset


def set_archived(asset, archived):
    """Archive or restore a position. An archived position accepts no new operation."""
    asset.is_archived = archived
    asset.save(update_fields=["is_archived", "updated_at"])
    return asset


@transaction.atomic
def delete_position(asset):
    """Delete a position that has no operation, with its product and prices.

    A position with operations is history: it can be archived, not deleted.
    """
    if asset.operations.exists():
        raise ValidationError(
            _("This investment has operations. Delete them first, or archive the investment.")
        )
    product = asset.opening_product
    # The opening position is removed first: an asset that holds one refuses deletion.
    Asset.objects.filter(pk=asset.pk).update(
        opening_balance=ZERO,
        opening_quantity=ZERO,
        opening_unit_price=ZERO,
        opening_date=None,
        opening_product=None,
    )
    Asset.objects.get(pk=asset.pk).delete()
    if product and not product.operations.exists() and not product.opening_balance_assets.exists():
        product.delete()


@transaction.atomic
def record_operation(
    user,
    asset,
    *,
    kind,
    date,
    amount=None,
    quantity=None,
    unit_price=None,
    cash_amount=None,
    account=None,
    ending_balance=None,
):
    """Record a deposit, a withdrawal or a yield on the position of ``asset``.

    ``account`` pays a deposit or receives a withdrawal. A balance position
    uses ``amount``; its yield can give ``ending_balance`` instead, and the
    yield is the difference. A position in units uses ``quantity`` and
    ``unit_price``; ``cash_amount`` is the money that moved in the account,
    by default their product.
    """
    product = asset.opening_product
    monetary = asset.valuation_mode == Asset.ValuationMode.MONETARY
    operation = Investment(
        user=user,
        product=product,
        asset=asset,
        kind=kind,
        date=date,
        amount=amount if monetary else None,
        quantity=None if monetary else quantity,
        unit_price=None if monetary else unit_price,
    )
    if kind == Investment.Kind.DEPOSIT:
        operation.source_account = account
    elif kind == Investment.Kind.WITHDRAWAL:
        operation.destination_account = account
    if monetary and kind == Investment.Kind.YIELD:
        by_balance = ending_balance is not None
        operation.amount = calculate_monetary_yield(
            user=user,
            product=product,
            asset=asset,
            operation_date=date,
            input_mode=YIELD_INPUT_ENDING_BALANCE if by_balance else YIELD_INPUT_AMOUNT,
            value=ending_balance if by_balance else amount,
            lock=True,
        ).yield_amount
    elif kind != Investment.Kind.YIELD:
        if monetary:
            operation.cash_amount = amount
        elif cash_amount is not None:
            operation.cash_amount = cash_amount
        elif quantity is not None and unit_price is not None:
            operation.cash_amount = (quantity * unit_price).quantize(CENTS)
    if kind == Investment.Kind.WITHDRAWAL:
        _check_available(operation, monetary)
    operation.full_clean()
    operation.save()
    refresh_fx_snapshot(operation)
    sync_investment_ledger(operation)
    return operation


def _check_available(operation, monetary):
    """Refuse a withdrawal of more than the position holds on its date.

    The replay refuses it too, with an error on the date. This check names
    the value that the owner typed.
    """
    field = "amount" if monetary else "quantity"
    requested = operation.amount if monetary else operation.quantity
    if requested is None or operation.date is None:
        return  # The model reports the missing value.
    available = available_value(operation) if monetary else available_quantity(operation)
    if requested > available:
        raise ValidationError({field: _("Withdrawal exceeds the available position on this date.")})


@transaction.atomic
def delete_operation(operation):
    """Delete an operation and its bank side, when the later operations stay valid."""
    validate_position_history(
        operation.user,
        [(operation.product_id, operation.asset_id)],
        exclude_pk=operation.pk,
    )
    cleanup_investment_ledger(operation)
    operation.delete()


@transaction.atomic
def set_current_value(user, asset, value):
    """Record what the position is worth today from one number.

    For a position in units, ``value`` is the unit price of today. For a
    balance position, ``value`` is the balance of today, and the difference
    from the recorded balance becomes a yield. A lower balance is not a
    yield: it needs a withdrawal, which names the account that received it.
    """
    if value is None or not value.is_finite() or value <= 0:
        raise ValidationError({"value": _("Enter a value greater than zero.")})
    if asset.is_archived:
        raise ValidationError(
            {"value": _("This investment is archived. Restore it to record a new value.")}
        )
    today = clock.today()
    if asset.valuation_mode == Asset.ValuationMode.UNITS:
        observation = PriceObservation.objects.filter(asset=asset, date=today).first()
        observation = observation or PriceObservation(
            user=user, asset=asset, date=today, source=_("Typed in the Wallet")
        )
        observation.unit_price = value
        observation.full_clean()
        observation.save()
        return
    current = monetary_position_before(
        user=user, product=asset.opening_product, asset=asset, operation_date=today, lock=True
    )
    if value.quantize(CENTS) == current:
        return
    try:
        record_operation(user, asset, kind=Investment.Kind.YIELD, date=today, ending_balance=value)
    except ValidationError as error:
        if not hasattr(error, "error_dict"):
            raise
        messages = [message for items in error.message_dict.values() for message in items]
        raise ValidationError({"value": messages}) from None
