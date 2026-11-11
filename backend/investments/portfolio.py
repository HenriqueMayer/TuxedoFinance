"""Read models of the investments in the Wallet.

These functions only read. Quantities, costs and values come from the
position replay and its valuation (``investments.positions``).
"""

from decimal import Decimal

from config import clock
from investments.models import Asset, Investment
from investments.positions import get_portfolio_valuation

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
OPERATION_LIMIT = 60


def _cents(value):
    return None if value is None else value.quantize(CENTS)


def _row(asset, valued):
    """Return the Wallet row of the position of ``asset``.

    ``valued`` is its row in the valuation, or None for a position that holds
    nothing yet.
    """
    product = asset.opening_product
    units = asset.valuation_mode == Asset.ValuationMode.UNITS
    observation = valued["price_observation"] if valued else None
    return {
        "id": asset.pk,
        "name": asset.name,
        "institution_id": product.bank_id,
        "institution_name": product.bank.name,
        "currency": asset.currency,
        "valuation_mode": asset.valuation_mode,
        "purpose": product.purpose,
        "is_archived": asset.is_archived,
        "value": _cents(valued["valuation"]) if valued else ZERO,
        "base_value": _cents(valued["base_value"]) if valued else ZERO,
        "quantity": (valued["quantity"] if valued else Decimal("0")) if units else None,
        "cost": _cents(valued["remaining_cost"]) if valued else ZERO,
        # The gain of units that are still held, at the last recorded price.
        "gain": _cents(valued["unrealized_gain"]) if valued and units else None,
        "yields": _cents(valued["yields"]) if valued else ZERO,
        "unit_price": observation.unit_price if observation else None,
        "price_date": observation.date if observation else None,
        # False: units are held and no price was recorded, so the value is the cost.
        "has_price": valued["market_available"] if valued else True,
    }


def overview(user):
    """Return the positions of ``user`` as of today and their total in the base currency.

    ``complete`` is false when a value could not be converted to the base
    currency; ``missing_currencies`` names the currencies without a rate.
    """
    valuation = get_portfolio_valuation(user)
    valued = {(row["product"].pk, row["asset"].pk): row for row in valuation["positions"]}
    assets = (
        Asset.objects.filter(user=user, opening_product__isnull=False)
        .select_related("opening_product__bank")
        .order_by("opening_product__bank__name", "name", "pk")
    )
    return {
        "positions": [
            _row(asset, valued.get((asset.opening_product_id, asset.pk))) for asset in assets
        ],
        "currency": valuation["base_currency"],
        "total": valuation["total"],
        "complete": not valuation["missing_currencies"],
        "missing_currencies": valuation["missing_currencies"],
    }


def detail(asset):
    """Return one position with its latest operations, newest first."""
    valuation = get_portfolio_valuation(asset.user)
    valued = next(
        (
            row
            for row in valuation["positions"]
            if (row["product"].pk, row["asset"].pk) == (asset.opening_product_id, asset.pk)
        ),
        None,
    )
    operations = (
        Investment.objects.filter(asset=asset, product=asset.opening_product)
        .select_related("source_account", "destination_account")
        .order_by("-date", "-created_at", "-pk")[:OPERATION_LIMIT]
    )
    opening = None
    if asset.has_opening_position:
        opening = {
            "date": asset.opening_date,
            "value": _cents(
                asset.opening_balance + asset.opening_quantity * asset.opening_unit_price
            ),
            "quantity": asset.opening_quantity
            if asset.valuation_mode == Asset.ValuationMode.UNITS
            else None,
        }
    return {
        **_row(asset, valued),
        "today": clock.today(),
        "opening": opening,
        "operations": [
            {
                "id": operation.pk,
                "kind": operation.kind,
                "date": operation.date,
                "value": _cents(operation.gross_value),
                "quantity": operation.quantity,
                "unit_price": operation.unit_price,
                "account_name": (operation.source_account or operation.destination_account).name
                if (operation.source_account_id or operation.destination_account_id)
                else "",
            }
            for operation in operations
        ],
    }
