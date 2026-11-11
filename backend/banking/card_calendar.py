"""Credit-card statement calendar.

A statement month is the month of the card invoice that receives a purchase.
The due date is the date when that invoice is due. Both depend only on the
closing day and the due day of the card, so these functions take those days
as numbers. The module imports only the standard library: it reads no model,
setting or clock.

``CreditCard.statement_month`` and ``CreditCard.due_date_for`` call these
functions, and so does the occurrence engine in ``transactions.schedule``.
"""

from calendar import isleap
from datetime import date
from functools import lru_cache

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def days_in_month(year, month):
    """Return the number of days of a month.

    The value equals ``calendar.monthrange(year, month)[1]``, which also
    calculates a weekday and is slower.
    """
    return 29 if month == 2 and isleap(year) else _MONTH_DAYS[month]


def statement_month(closing_day, purchase_date, override=None):
    """Return the first day of the statement month of a purchase.

    ``override`` is the bill choice of the purchase:

    - ``None`` (automatic): a purchase on or after the closing day goes to the
      statement of the next month. The closing day is clamped to the length of
      the purchase month, so a card that closes on the 31st closes on
      30 April and on the last day of February.
    - ``0`` (current bill): the statement of the purchase month.
    - ``1`` (next bill): the statement of the next month.

    Raise ``ValueError`` for another override, and for a statement month after
    December 9999.
    """
    if override not in (None, 0, 1):
        raise ValueError("override must be None, 0, or 1.")
    if override is None:
        closing_day = min(closing_day, days_in_month(purchase_date.year, purchase_date.month))
        offset = 1 if purchase_date.day >= closing_day else 0
    else:
        offset = override
    index = purchase_date.year * 12 + purchase_date.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


def due_month_offset(closing_day, due_day):
    """Return the number of months from a statement month to its due month: 0 or 1.

    When the due day is before the closing day, the invoice is paid in the
    following calendar month. For example, a card that closes on the 24th and
    is due on the 1st has its August invoice due on September 1st, not
    August 1st. Equal days give 0.
    """
    return 1 if due_day < closing_day else 0


# Synchronization asks for the same few statements many times; the function
# is pure, so a bounded cache returns the same date objects.
@lru_cache(maxsize=4096)
def due_date(closing_day, due_day, reference_month):
    """Return the due date of the statement of ``reference_month``.

    ``reference_month`` can be any day of the statement month. The due month
    is ``due_month_offset`` months after the statement month, and the due day
    is clamped to the length of the due month. Raise ``ValueError`` for a due
    date after 31 December 9999: the December 9999 statement of a card with a
    due month offset of 1.
    """
    reference_month = reference_month.replace(day=1)
    if due_month_offset(closing_day, due_day):
        index = reference_month.year * 12 + reference_month.month
        year, month = divmod(index, 12)
        reference_month = date(year, month + 1, 1)
    day = min(due_day, days_in_month(reference_month.year, reference_month.month))
    return reference_month.replace(day=day)
