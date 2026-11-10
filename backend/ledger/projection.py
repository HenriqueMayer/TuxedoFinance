"""The synchronization horizon and the translated occurrence limit.

The rules are in the occurrence engine, ``transactions.schedule``. This
module adds what the engine must not read: the financial date of
``core.clock`` and the translated error. ``occurrence_window`` and
``occurrence_months`` accept a ``Transaction``; they stay for callers outside
the transactions app until those callers use the engine directly.
"""

from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from config import clock
from ledger import schedule
from ledger.schedule import MAX_MONTHLY_OCCURRENCES, month_at, month_index

DEFAULT_PROJECTION_MONTHS = 12


class ProjectionLimitExceeded(ValidationError):
    def __init__(self):
        super().__init__(
            _(
                "This recurring transaction would generate more than %(limit)s monthly occurrences. Review its start and end dates."
            ),
            code="projection_limit",
            params={"limit": MAX_MONTHLY_OCCURRENCES},
        )


def _month_end(month):
    return month.replace(day=monthrange(month.year, month.month)[1])


def projection_horizon(reference=None, months=DEFAULT_PROJECTION_MONTHS):
    """Return the last day of the month ``months`` after the month of ``reference``.

    ``reference`` defaults to today. Synchronization projects through this
    date, and ``validate_occurrences`` counts through it. Example: 2026-11-02
    with 12 months gives 2027-11-30. Because the horizon ends on a month end,
    it changes once each month (LEDGER_RULES_VERSION 2).
    """
    reference = reference or clock.today()
    return _month_end(month_at(month_index(reference) + months))


def last_forecast_month(covered_through, today):
    """Return the first day of the last month that a page may forecast.

    Pages forecast through the month of ``today`` plus 11 months. A month
    also needs complete derived rows: its last day must be on or before
    ``covered_through`` (``LedgerReadState.covered_through``). With
    ``covered_through`` None there is no coverage limit. Example: on
    2026-12-05 with rows through 2027-10-31, the result is 2027-10-01.
    """
    window = month_at(month_index(today) + DEFAULT_PROJECTION_MONTHS - 1)
    if covered_through is None:
        return window
    covered = covered_through.replace(day=1)
    if covered_through != _month_end(covered_through):
        # The rows of a partly covered month are incomplete.
        covered = month_at(month_index(covered) - 1)
    return min(window, covered)


def occurrence_window(item, horizon):
    """Return ``(start, count)`` of the occurrence window of a transaction (``schedule.schedule_window``).

    The window does not visit empty calendar gaps. It reads only the calendar
    fields of ``item``, so the preflight of ``sync_user_ledger`` can pass
    instances with deferred fields.
    """
    card = item.is_credit_card
    return schedule.schedule_window(
        item.billed_month if card else item.date.replace(day=1),
        horizon,
        settles_on_date=not card,
        day=item.date.day,
        is_fixed=item.is_fixed,
        last_offset=item.last_fixed_offset if item.is_fixed else None,
        installments=item.installments,
        installment_start=getattr(item, "installment_start", 1) if item.is_installment_plan else 1,
    )


def occurrence_months(item, horizon):
    start, count = occurrence_window(item, horizon)
    if count:
        first = month_index(start)
        for offset in range(count):
            yield month_at(first + offset)


def validate_occurrences(item, horizon=None):
    """Raise ``ProjectionLimitExceeded`` when a fixed transaction has more than 1,200 occurrences.

    The count is the occurrence window through ``horizon`` (default: the
    synchronization horizon of today).
    """
    if item.is_fixed and isinstance(item.date, date):
        _start, count = occurrence_window(item, horizon or projection_horizon())
        if count > MAX_MONTHLY_OCCURRENCES:
            raise ProjectionLimitExceeded()
