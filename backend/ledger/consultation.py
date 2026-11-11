"""Reads for consulting transactions: the billed month and the effect of a source."""

from datetime import date, timedelta
from functools import lru_cache

from django.db.models import Q

from ledger import schedule
from ledger.models import attach_schedule_rows


def may_bill_between(first, last):
    """Return the filter of the transactions that can have an amount from ``first`` to ``last``.

    Both are first days of months. A repeating entry and an installment plan
    can reach any later month, so they always pass. A single entry counts in
    the month of its date or, on a credit card, in the month after it
    (``banking.card_calendar.statement_month``). The filter is wider than the
    answer; the occurrence engine decides.
    """
    earliest = schedule.offset_month(first, -1)
    latest = schedule.offset_month(last, 1) - timedelta(days=1)
    return Q(is_fixed=True) | Q(installments__gt=1) | Q(date__range=(earliest, latest))


def requested_billed_month(raw_month):
    """Return a valid ``(year, month)`` pair or ``None`` for no filter."""
    if len(raw_month) != 7:
        return None
    try:
        parsed = date.fromisoformat(raw_month + "-01")
    except ValueError:
        return None
    return (parsed.year, parsed.month) if parsed.isoformat()[:7] == raw_month else None


@lru_cache(maxsize=32)
def _billed_month_window(year, month_number):
    return schedule.Window.months(date(year, month_number, 1))


def billed_month_occurrence(item, year, month_number, *, allocations=False):
    """Return the occurrence of a transaction in a billed month, or None when that month has no amount.

    The billed month is the statement month for a credit card and the
    occurrence month otherwise (``ledger.schedule``).
    """
    occurrences = schedule.expand(
        (item.schedule_source(splits=allocations),),
        _billed_month_window(year, month_number),
        allocations=allocations,
    )
    return occurrences[0] if occurrences else None


def filter_by_billed_month(queryset, raw_month):
    requested_month = requested_billed_month(raw_month)
    if requested_month is None:
        return queryset
    year, month_number = requested_month
    # The R4 rows decide the amount of each month: a skipped month has none.
    if (
        hasattr(queryset, "with_schedule_flags")
        and "schedule_row_flags" not in queryset.query.annotations
    ):
        queryset = queryset.with_schedule_flags()
    items = attach_schedule_rows(queryset)
    return [txn for txn in items if billed_month_occurrence(txn, year, month_number)]


def financial_effect(item, *, pending_change=None):
    """Explain validated source semantics without synchronizing or posting rows.

    ``pending_change`` is the unsaved ``(month, amount)`` of the edit form's
    From month scope (A9). It joins the amount changes as Save would store it:
    it replaces a stored change of the same month.
    """
    source = item.schedule_source()
    if source.instrument.is_credit_card:
        # Opening installment imports skip earlier invoices. Reuse the same
        # first tracked month as projection, rather than showing a skipped bill.
        billed_month, _count = schedule.occurrence_window(source, date.max)
        payment_date = (
            schedule.statement_due_date(source.instrument, billed_month) if billed_month else None
        )
    else:
        billed_month, payment_date = schedule.offset_month(source.date, 0), source.date
    commitment = item.is_commitment_source and not item.reward_redemption_id
    amount_changes = ()
    if commitment:
        steps = schedule.amount_steps(source)
        amount_changes = steps[1:]
        if pending_change is not None and pending_change[0] > steps[0][0]:
            amount_changes = tuple(
                sorted(
                    [step for step in amount_changes if step[0] != pending_change[0]]
                    + [tuple(pending_change)]
                )
            )
    return {
        # The amount of the first month, read now: the edit preview restores
        # the submitted amount on the instance after this call.
        "item": item,
        "amount": source.amount,
        "currency": source.currency,
        "account": item.payment_account,
        "billed_month": billed_month,
        "payment_date": payment_date,
        # R4: the amount changes after the first month, and the first month to confirm.
        "amount_changes": amount_changes,
        "confirmation_month": source.confirmation_start if commitment else None,
        "can_confirm_months": commitment and item.can_require_confirmation,
    }
