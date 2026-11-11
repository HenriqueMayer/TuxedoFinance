"""Recurring incomes: a salary or another income that arrives every month.

An income has one part or more. Each part is a repeating income entry on the
account of the income, dated on its day of the month. The entry follows the
rules of every repeating entry: its months are in the monthly schedule, a
month can wait for a confirmation, and an amount change holds from a month.

The income owns its entries. With a past month, a part keeps what is
recorded: its day does not change, a new amount holds from the month of the
next receipt, and a removed part ends in the month before the current one.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from ledger import commitments, schedule
from ledger.models import RecurringIncome, Transaction

ZERO = Decimal("0.00")
MAX_PARTS = 6
# How far ahead the next receipt of a part is looked for.
NEXT_MONTHS = 13


def _first(day):
    return day.replace(day=1)


def _has_past_month(entry, today):
    return _first(entry.date) < _first(today)


def _active(entry, today):
    return entry.fixed_until is None or _first(entry.fixed_until) >= _first(today)


def entries_of(income, today):
    """Return the entries of the parts that still repeat, by day of the month."""
    found = [entry for entry in income.parts.all() if _active(entry, today)]
    return sorted(found, key=lambda entry: (entry.date.day, entry.pk))


def _check_parts(parts):
    if not parts:
        raise ValidationError({"parts": _("Add one part at least.")})
    if len(parts) > MAX_PARTS:
        raise ValidationError(
            {"parts": _("An income has at most %(count)s parts.") % {"count": MAX_PARTS}}
        )
    for part in parts:
        if not 1 <= part["day"] <= 31:
            raise ValidationError({"parts": _("The day of a part is from 1 to 31.")})
        if part["amount"] <= ZERO:
            raise ValidationError({"parts": _("The amount of a part is greater than zero.")})


def _set_confirmation(entry, confirm, today):
    if confirm and not entry.requires_confirmation:
        # Confirmation starts with the current month, or with the first month
        # of a part that starts later. Earlier months stay as recorded.
        entry.confirmation_start = _first(max(entry.date, today))
    elif not confirm:
        entry.confirmation_start = None
    entry.requires_confirmation = confirm


def _save(entry):
    try:
        entry.full_clean()
    except ValidationError as error:
        errors = dict(error.message_dict)
        renamed = {"category": "category_id", "bank_account": "account_id", "title": "name"}
        raise ValidationError(
            {renamed.get(name, "parts"): messages for name, messages in errors.items()}
        ) from error
    entry.save()


def _new_part(income, month, part, *, account, category, until, confirm, today):
    entry = Transaction(
        user=income.user,
        recurring_income=income,
        title=income.name,
        transaction_type=Transaction.TransactionType.INCOME,
        payment_channel=Transaction.PaymentChannel.ACCOUNT,
        bank_account=account,
        category=category,
        amount=part["amount"],
        date=schedule.day_in_month(schedule.month_index(month), part["day"]),
        is_fixed=True,
        fixed_until=until,
    )
    _set_confirmation(entry, confirm, today)
    _save(entry)
    return entry


def _save_income(income):
    try:
        income.full_clean()
    except ValidationError as error:
        raise ValidationError(error.message_dict) from error
    income.save()


def create(user, values, *, today):
    """Create an income with its parts. ``values`` has the fields of the request.

    The first month is ``start``, or the current month. A part whose day
    already passed in that month is an entry of that day.
    """
    _check_parts(values["parts"])
    income = RecurringIncome(
        user=user,
        name=values["name"].strip(),
        gross=values.get("gross"),
        advance_percent=values.get("advance_percent"),
    )
    _save_income(income)
    month = _first(values.get("start") or today)
    for part in values["parts"]:
        _new_part(
            income,
            month,
            part,
            account=values["account"],
            category=values["category"],
            until=values.get("until"),
            confirm=values.get("confirm", False),
            today=today,
        )
    return income


def change(income, values, *, today):
    """Change an income and its parts.

    A part of the request with an ``id`` is an existing part; one without is
    new and starts in the current month. An existing part that the request
    leaves out is removed.
    """
    _check_parts(values["parts"])
    user = income.user
    income.name = values["name"].strip()
    income.gross = values.get("gross")
    income.advance_percent = values.get("advance_percent")
    _save_income(income)
    current = {entry.pk: entry for entry in entries_of(income, today)}
    wanted = {part["id"]: part for part in values["parts"] if part.get("id") is not None}
    if set(wanted) - set(current):
        raise ValidationError({"parts": _("Choose the parts of this income.")})
    until, confirm = values.get("until"), values.get("confirm", False)
    for pk, entry in current.items():
        part = wanted.get(pk)
        past = _has_past_month(entry, today)
        if part is None:
            if past:
                # The past months stay: the part ends with the month before this one.
                entry.fixed_until = _first(today) - timedelta(days=1)
                _save(entry)
            else:
                entry.delete()
            continue
        entry.title = income.name
        entry.category = values["category"]
        entry.bank_account = values["account"]
        entry.fixed_until = until
        _set_confirmation(entry, confirm, today)
        new_amount = None
        if part["day"] != entry.date.day:
            if past:
                raise ValidationError(
                    {
                        "parts": _(
                            "A part with past months keeps its day. Remove it and add a part with the new day."
                        )
                    }
                )
            entry.date = schedule.day_in_month(schedule.month_index(entry.date), part["day"])
        if part["amount"] != next_receipt(entry, today)[1]:
            if past:
                new_amount = part["amount"]
            else:
                entry.amount = part["amount"]
        _save(entry)
        if new_amount is not None:
            commitments.change_amount_from(
                entry, commitments.default_change_month(entry, today), new_amount, user=user
            )
    for part in values["parts"]:
        if part.get("id") is None:
            _new_part(
                income,
                _first(today),
                part,
                account=values["account"],
                category=values["category"],
                until=until,
                confirm=confirm,
                today=today,
            )
    return income


def next_receipt(entry, today):
    """Return the date and the amount of the next receipt of a part.

    A part without a receipt from today on gives no date and the amount of
    the current month.
    """
    last = schedule.offset_month(today, NEXT_MONTHS)
    for row in commitments.schedule_months(entry, today, last, today=today):
        if row.status != schedule.SKIPPED and row.cash_date and row.cash_date >= today:
            return row.cash_date, row.amount
    return None, schedule.scheduled_amount(entry.schedule_source(), _first(today))


def describe(income, today):
    """Return an income for a response: its parts by day and the total of a month."""
    entries = entries_of(income, today)
    parts = []
    for entry in entries:
        date, amount = next_receipt(entry, today)
        parts.append({"id": entry.pk, "day": entry.date.day, "amount": amount, "next_date": date})
    first = entries[0] if entries else None
    return {
        "id": income.pk,
        "name": income.name,
        "category": first.category if first else None,
        "account": first.bank_account if first else None,
        "currency": first.bank_account.currency if first else "",
        "until": first.fixed_until if first else None,
        "confirm": bool(first and first.requires_confirmation),
        "gross": income.gross,
        "advance_percent": income.advance_percent,
        "total": sum((part["amount"] for part in parts), ZERO),
        "parts": parts,
    }


def listing(user, today):
    """Return the incomes of ``user`` that still repeat, and their total of a month by currency."""
    incomes = RecurringIncome.objects.filter(user=user).prefetch_related(
        "parts__bank_account__bank", "parts__category"
    )
    items = [row for row in (describe(income, today) for income in incomes) if row["parts"]]
    totals = {}
    for item in items:
        totals[item["currency"]] = totals.get(item["currency"], ZERO) + item["total"]
    return {
        "items": items,
        "totals": [
            {"currency": currency, "amount": amount} for currency, amount in sorted(totals.items())
        ],
    }
