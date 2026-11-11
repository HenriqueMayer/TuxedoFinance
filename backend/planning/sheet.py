"""The months ahead: the cash that the records already expect, and a sheet to try changes.

The sheet has one row for each source of future cash and one column for each
month, from the current month on. It reads what the ledger already derived:

- Each bank movement dated after today. A repeating entry, an entry with a
  later date and the invoice of a card that is paid from its account on the
  due date all have such movements (``ledger.services.sync_user_ledger``).
- Each invoice that waits for a confirmed payment, with what is still to pay,
  in the month of its due date.
- Each month of a repeating entry that waits for confirmation, in the month
  of its date.

An amount that is already late counts in the current month. A transfer
between accounts is not cash in or out. What happened through today is in the
opening balance: the account balances of today.

``changes`` is the simulation, as a saved sheet stores it::

    {"cells": {row_key: {"YYYY-MM": "123.45"}},
     "manual": [{"id": "a1", "label": "Bonus", "section": "income", "amount": "1000.00"}]}

A changed cell replaces the recorded value in the sheet only. A manual row
has its amount in each month. Nothing here writes a financial record.

Amounts are in the currency of totals, converted with the exchange rate of
today. An amount without a rate is left out and its currency is listed.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from accounts.models import UserPreference
from banking.models import BankMovement, CardInvoice
from banking.services import MissingExchangeRate, account_balances, convert
from banking.settlements import attach_invoice_states
from ledger import schedule
from ledger.models import Transaction, attach_schedule_rows
from planning.models import SavedSheet

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
INCOME, EXPENSE = "income", "expense"
MAX_MANUAL = 40
MAX_AMOUNT = Decimal("999999999999.99")


def _events(user, today, end):
    """Yield ``(row_key, label, section, date, amount, currency)`` for the cash after today."""
    movements = (
        BankMovement.objects.filter(user=user, effective_date__gt=today, effective_date__lte=end)
        .exclude(kind=BankMovement.Kind.TRANSFER)
        .select_related("account", "invoice__card")
    )
    for movement in movements:
        section = INCOME if movement.direction == BankMovement.Direction.CREDIT else EXPENSE
        if movement.invoice_id:
            key, label = f"card:{movement.invoice.card_id}", movement.invoice.card.name
        elif movement.source_key.startswith("transaction:"):
            key = ":".join(movement.source_key.split(":")[:2])
            label = movement.description
        else:
            key, label = f"other:{section}", ""
        yield (
            key,
            label,
            section,
            movement.effective_date,
            movement.amount,
            movement.account.currency,
        )

    # An invoice that waits for a confirmed payment has no movement yet.
    invoices = attach_invoice_states(
        CardInvoice.objects.filter(user=user, due_date__lte=end, amount__gt=0)
        .select_related("card__account")
        .prefetch_related("payments"),
        as_of=today,
    )
    for invoice in invoices:
        state = invoice.current_state
        if state.manual_settlement and state.remaining_amount > ZERO:
            yield (
                f"card:{invoice.card_id}",
                invoice.card.name,
                EXPENSE,
                max(invoice.due_date, today),
                state.remaining_amount,
                invoice.card.account.currency,
            )

    # A month that waits for confirmation never becomes a movement by itself.
    waiting = attach_schedule_rows(
        Transaction.objects.filter(user=user, is_fixed=True, requires_confirmation=True)
        .exclude(payment_channel="CREDIT_CARD")
        .select_related("bank_account", "debit_card__account")
        .with_schedule_flags()
        .order_by("pk")
    )
    sources = tuple(item.schedule_source() for item in waiting)
    titles = {item.pk: item.title for item in waiting}
    for occurrence in schedule.expand(sources, schedule.Window.through(end)):
        if occurrence.status != schedule.EXPECTED or occurrence.cash_date is None:
            continue
        yield (
            f"transaction:{occurrence.source_id}",
            titles[occurrence.source_id],
            INCOME if occurrence.flow == "INCOME" else EXPENSE,
            max(occurrence.cash_date, today),
            occurrence.amount,
            occurrence.currency,
        )


def clean_changes(changes):
    """Return ``changes`` in the stored shape, or raise for a value out of range."""
    cells = {}
    for key, months in (changes.get("cells") or {}).items():
        for month, amount in months.items():
            amount = Decimal(amount)
            if not ZERO <= amount <= MAX_AMOUNT:
                raise ValidationError({"changes": _("Enter zero or a positive amount.")})
            cells.setdefault(str(key)[:100], {})[month] = f"{amount.quantize(CENTS)}"
    manual = []
    for row in changes.get("manual") or []:
        label = row["label"].strip()[:80]
        amount = row.get("amount")
        if not label:
            raise ValidationError({"changes": _("Enter a name.")})
        if amount is not None and not ZERO <= Decimal(amount) <= MAX_AMOUNT:
            raise ValidationError({"changes": _("Enter zero or a positive amount.")})
        manual.append(
            {
                "id": row["id"],
                "label": label,
                "section": row["section"],
                "amount": None if amount is None else f"{Decimal(amount).quantize(CENTS)}",
            }
        )
    if len(manual) > MAX_MANUAL:
        raise ValidationError({"changes": _("A sheet has at most 40 added rows.")})
    return {"cells": cells, "manual": manual}


def compose(user, today, months=6, changes=None):
    """Return the sheet of the ``months`` months that start with the month of ``today``."""
    changes = clean_changes(changes or {})
    base = UserPreference.for_user(user).base_currency
    first = today.replace(day=1)
    columns = [schedule.offset_month(first, offset) for offset in range(months)]
    last_day = schedule.offset_month(first, months) - timedelta(days=1)

    rates, missing = {}, set()

    def in_base(amount, currency):
        if currency not in rates:
            try:
                rates[currency] = convert(user, Decimal("1"), currency, base, as_of=today)
            except MissingExchangeRate:
                rates[currency] = None
                missing.add(currency)
        return None if rates[currency] is None else amount * rates[currency]

    opening = ZERO
    for row in account_balances(user, as_of=today):
        opening += in_base(row["balance"], row["account"].currency) or ZERO

    live = defaultdict(lambda: defaultdict(lambda: ZERO))
    meta = {}
    for key, label, section, when, amount, currency in _events(user, today, last_day):
        value = in_base(amount, currency)
        if value is None:
            continue
        live[key][when.replace(day=1)] += value
        meta.setdefault(key, (label, section))

    rows = [
        {"key": key, "label": label, "section": section, "manual": False, "default": None}
        for key, (label, section) in meta.items()
    ]
    rows.sort(key=lambda row: (row["section"] != INCOME, row["label"].casefold(), row["key"]))
    for manual in changes["manual"]:
        rows.append(
            {
                "key": f"manual:{manual['id']}",
                "label": manual["label"],
                "section": manual["section"],
                "manual": True,
                "default": Decimal(manual["amount"]) if manual["amount"] else None,
            }
        )
    rows.sort(key=lambda row: row["section"] != INCOME)  # Stable: income first.

    totals = {month: {INCOME: ZERO, EXPENSE: ZERO, "live": ZERO} for month in columns}
    for row in rows:
        typed = changes["cells"].get(row["key"], {})
        cells = []
        for month in columns:
            recorded = live[row["key"]][month].quantize(CENTS)
            text = typed.get(month.strftime("%Y-%m"))
            if text is not None:
                value, changed = Decimal(text), True
            elif row["default"] is not None:
                value, changed = row["default"], False
            else:
                value, changed = recorded, False
            sign = 1 if row["section"] == INCOME else -1
            totals[month][row["section"]] += value
            totals[month]["live"] += sign * recorded
            cells.append({"month": month, "live": recorded, "value": value, "changed": changed})
        row["cells"] = cells
        del row["default"]

    balance = live_balance = opening.quantize(CENTS)
    summary = []
    for month in columns:
        result = totals[month][INCOME] - totals[month][EXPENSE]
        balance += result
        live_balance += totals[month]["live"]
        summary.append(
            {
                "month": month,
                "income": totals[month][INCOME],
                "expenses": totals[month][EXPENSE],
                "result": result,
                "balance": balance,
                "live_balance": live_balance,
            }
        )
    return {
        "today": today,
        "currency": base,
        "opening_balance": opening.quantize(CENTS),
        "rows": rows,
        "totals": summary,
        "complete": not missing,
        "missing_currencies": sorted(missing),
    }


def _name(user, name, *, except_pk=None):
    name = name.strip()
    if not name:
        raise ValidationError({"name": _("Enter a name.")})
    taken = SavedSheet.objects.filter(user=user, name__iexact=name).exclude(pk=except_pk)
    if taken.exists():
        raise ValidationError({"name": _("A saved sheet with this name already exists.")})
    return name


def save_sheet(user, *, name, months, changes, sheet=None):
    """Create a saved sheet, or replace the name and the changes of ``sheet``."""
    sheet = sheet or SavedSheet(user=user)
    sheet.name = _name(user, name, except_pk=sheet.pk)
    sheet.months = months
    sheet.changes = clean_changes(changes)
    sheet.full_clean()
    sheet.save()
    return sheet
