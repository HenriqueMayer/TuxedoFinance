"""Net worth on a date: accounts and investments, less the incurred card debt.

Terms:

- The *incurred* amount of a card statement on a date is the sum of its
  purchases, installments and points purchases dated on or before that date,
  less its invoice credits posted on or before that date. A purchase in
  installments is debt for its full unpaid amount, including later
  installments. A repeating purchase is debt only from its date in each month.
- The *paid* amount is the confirmed payments of a statement that waits for
  confirmation, or the settlement debit of a statement that settles from its
  account, on or before the date.
- A statement owes ``incurred - paid``. A negative result is a card credit:
  money that the card owes to the owner.

Every amount is converted to the base currency with the rate of the date. An
amount without a rate adds nothing, and its currency is named.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from banking.models import CardInvoice, CardInvoiceCredit, LoyaltyEntry
from banking.services import ConversionContext, MissingExchangeRate, account_balances
from investments.positions import load_position_sources, replay_positions, value_positions
from ledger import schedule
from ledger.models import Transaction, attach_schedule_rows

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
SERIES_MONTHS = 12


class Sources:
    """The records of one owner that a net worth read needs, loaded once.

    A series reads the same records for each of its dates.
    """

    def __init__(self, user):
        self.user = user
        self.conversion = ConversionContext(user)
        purchases = attach_schedule_rows(
            Transaction.objects.filter(user=user, payment_channel="CREDIT_CARD")
            .select_related("credit_card__account")
            .with_schedule_flags()
            .order_by("pk")
        )
        self.purchases = [(item, item.schedule_source()) for item in purchases]
        self.points_purchases = list(
            LoyaltyEntry.objects.filter(
                user=user, kind=LoyaltyEntry.Kind.PURCHASE, funding_credit_card__isnull=False
            ).select_related("funding_credit_card__account")
        )
        self.credits = list(
            CardInvoiceCredit.objects.filter(user=user).select_related("card__account")
        )
        self.invoices = list(
            CardInvoice.objects.filter(user=user)
            .select_related("card__account", "settlement_movement")
            .prefetch_related("payments")
        )
        self.assets, self.operations, self.prices = load_position_sources(user)


def _incurred(sources, as_of):
    """Return the incurred amount of each ``(card id, statement month)`` and the cards."""
    amounts = defaultdict(lambda: ZERO)
    cards = {}
    this_month = as_of.replace(day=1)
    for item, source in sources.purchases:
        if item.date > as_of:
            continue
        start = source.date
        # The statement month of the purchase date: offset 0 of the schedule.
        billed = schedule.offset_month(
            start,
            schedule.billing_offset(start, source.instrument.closing_day, source.billing_override),
        )
        if (
            item.is_installment_plan
            and item.installment_start > 1
            and schedule.offset_month(billed, item.installment_start - 1) > this_month
        ):
            # A plan recorded from a later installment proves the balance from
            # its first tracked month, not the balance before it.
            continue
        cards[item.credit_card_id] = item.credit_card
        if item.is_fixed:
            final = schedule.months_between(start, as_of.year, as_of.month)
            last = schedule.last_fixed_offset(True, start, source.fixed_until)
            offsets = range((final if last is None else min(final, last)) + 1)
        else:
            offsets = range(item.installments)
        if not offsets:
            continue
        window = schedule.Window.months(billed, schedule.offset_month(billed, offsets[-1]))
        statements = {
            occurrence.reference_month: occurrence.amount
            for occurrence in schedule.expand((source,), window)
        }
        for offset in offsets:
            # A repeating purchase is debt from its date in the month.
            event = schedule.day_in_month(schedule.month_index(start) + offset, start.day)
            if item.is_fixed and event > as_of:
                continue
            reference = schedule.offset_month(billed, offset)
            amounts[item.credit_card_id, reference] += statements.get(reference, ZERO)
    for entry in sources.points_purchases:
        if entry.date > as_of:
            continue
        card = entry.funding_credit_card
        cards[card.pk] = card
        amounts[card.pk, card.statement_month(entry.date)] += entry.cash_amount or ZERO
    for credit in sources.credits:
        if credit.date > as_of:
            continue
        cards[credit.card_id] = credit.card
        amounts[credit.card_id, credit.reference_month] -= credit.amount
    return amounts, cards


def _settlement(invoice):
    """Return the debit that settled an invoice from its account, or None."""
    return getattr(invoice, "settlement_movement", None)


def card_debt(sources, as_of):
    """Return what each card statement owes on ``as_of``, in the currency of its account.

    Each row has ``card_id``, ``card_name``, ``invoice_id`` (None without a
    stored invoice), ``month``, ``amount`` and ``currency``. A statement that
    owes nothing has no row. A negative amount is a card credit.
    """
    amounts, cards = _incurred(sources, as_of)
    stored = {}
    for invoice in sources.invoices:
        stored[invoice.card_id, invoice.reference_month] = invoice
        cards[invoice.card_id] = invoice.card
        movement = _settlement(invoice)
        # A statement with a payment counts even when nothing is incurred yet.
        if (
            invoice.manual_settlement
            and any(payment.date <= as_of for payment in invoice.payments.all())
        ) or (not invoice.manual_settlement and movement and movement.effective_date <= as_of):
            amounts.setdefault((invoice.card_id, invoice.reference_month), ZERO)
    rows = []
    for (card_id, month), amount in amounts.items():
        card = cards[card_id]
        invoice = stored.get((card_id, month))
        due = card.due_date_for(month)
        waits_for_payment = (invoice is not None and invoice.manual_settlement) or bool(
            card.manual_settlement_from and due >= card.manual_settlement_from
        )
        if waits_for_payment:
            paid = sum(
                (
                    payment.amount
                    for payment in (invoice.payments.all() if invoice else ())
                    if payment.date <= as_of
                ),
                ZERO,
            )
        else:
            movement = _settlement(invoice) if invoice else None
            if movement and movement.effective_date <= as_of:
                # A debit before the purchase date counts as a card credit
                # until the purchase is incurred.
                paid = movement.amount
            else:
                paid = max(ZERO, amount) if invoice is None and due <= as_of else ZERO
        owed = amount - paid
        if owed:
            rows.append(
                {
                    "card_id": card_id,
                    "card_name": card.name,
                    "invoice_id": invoice.pk if invoice else None,
                    "month": month,
                    "amount": owed,
                    "currency": card.account.currency,
                }
            )
    return rows


def net_worth(sources, as_of):
    """Return the net worth of the owner on ``as_of``, in the base currency."""
    conversion = sources.conversion
    missing = set()

    def in_base(amount, currency):
        if not amount:
            return ZERO
        try:
            return conversion.convert(amount, currency, as_of=as_of)
        except MissingExchangeRate:
            missing.add(currency)
            return ZERO

    accounts = sum(
        (
            in_base(row["balance"], row["account"].currency)
            for row in account_balances(sources.user, as_of)
        ),
        ZERO,
    )
    valuation = value_positions(
        sources.user,
        replay_positions(sources.assets, sources.operations, as_of),
        sources.prices,
        conversion.base_currency,
        as_of,
        historical=True,
        conversion=conversion,
    )
    missing.update(valuation["missing_currencies"])
    debt = credits = ZERO
    for row in card_debt(sources, as_of):
        value = in_base(row["amount"], row["currency"])
        if value > ZERO:
            debt += value
        else:
            credits -= value
    assets = accounts + valuation["total"] + credits
    return {
        "as_of": as_of,
        "currency": conversion.base_currency,
        "accounts": accounts.quantize(CENTS),
        "investments": valuation["total"],
        # What the positions cost. The value less the cost is what they earned.
        "investments_cost": valuation["cost_total"],
        "card_credits": credits.quantize(CENTS),
        "card_debt": debt.quantize(CENTS),
        "net_worth": (assets - debt).quantize(CENTS),
        "complete": not missing,
        "missing_currencies": sorted(missing),
    }


def positions(sources, as_of):
    """Return the positions that hold a value on ``as_of``, largest first.

    Each row has the value in the base currency and its part of the total,
    in percent. A position without an exchange rate is not listed.
    """
    valuation = value_positions(
        sources.user,
        replay_positions(sources.assets, sources.operations, as_of),
        sources.prices,
        sources.conversion.base_currency,
        as_of,
        historical=True,
        conversion=sources.conversion,
    )
    values = defaultdict(lambda: ZERO)
    assets = {}
    for row in valuation["positions"]:
        if row["base_value"]:
            assets[row["asset"].pk] = (row["asset"], row["product"])
            values[row["asset"].pk] += row["base_value"]
    held = sum(values.values(), ZERO)
    return sorted(
        (
            {
                "id": asset.pk,
                "name": asset.name,
                "institution_name": product.bank.name,
                "value": values[asset.pk].quantize(CENTS),
                "share": (values[asset.pk] * 100 / held).quantize(Decimal("0.1"))
                if held > ZERO
                else None,
            }
            for asset, product in assets.values()
        ),
        key=lambda row: (-row["value"], row["name"]),
    )


def composition(sources, as_of):
    """Return what the net worth of ``as_of`` is made of, in the base currency.

    ``accounts`` are the accounts with a balance, ``positions`` the
    investments with a value, and ``cards`` the statements that owe an
    amount; a negative card amount is a card credit. An amount without an
    exchange rate is None.
    """
    conversion = sources.conversion

    def in_base(amount, currency):
        try:
            return conversion.convert(amount, currency, as_of=as_of).quantize(CENTS)
        except MissingExchangeRate:
            return None

    accounts = [
        {
            "id": row["account"].pk,
            "name": row["account"].name,
            "bank_name": row["account"].bank.name,
            "amount": in_base(row["balance"], row["account"].currency),
        }
        for row in account_balances(sources.user, as_of)
        if row["balance"]
    ]
    cards = [
        {
            "card_id": row["card_id"],
            "card_name": row["card_name"],
            "month": row["month"],
            "amount": in_base(row["amount"], row["currency"]),
        }
        for row in card_debt(sources, as_of)
    ]
    return {
        "accounts": sorted(accounts, key=lambda row: (-(row["amount"] or ZERO), row["name"])),
        "positions": positions(sources, as_of),
        "cards": sorted(cards, key=lambda row: (row["month"], row["card_name"])),
    }


def summary(user, today):
    """Return the net worth of today and of the end of the month before, for Home."""
    sources = Sources(user)
    current = net_worth(sources, today)
    previous = net_worth(sources, today.replace(day=1) - timedelta(days=1))
    return {
        "currency": current["currency"],
        "net_worth": current["net_worth"],
        "previous": previous["net_worth"],
        "change": current["net_worth"] - previous["net_worth"],
        "complete": current["complete"] and previous["complete"],
    }


def series(user, today, months=SERIES_MONTHS):
    """Return the net worth of today and of each month end of the ``months`` months to today.

    The row of the current month is the net worth of today.
    """
    sources = Sources(user)
    current = net_worth(sources, today)
    rows = []
    for offset in range(-(months - 1), 1):
        month = schedule.offset_month(today, offset)
        if offset == 0:
            point = current
        else:
            point = net_worth(sources, schedule.offset_month(month, 1) - timedelta(days=1))
        rows.append(
            {
                "month": month,
                "accounts": point["accounts"],
                "investments": point["investments"],
                "card_debt": point["card_debt"],
                "net_worth": point["net_worth"],
                "complete": point["complete"],
            }
        )
    return {"today": current, "months": rows}
