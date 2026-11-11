"""The occurrence engine.

A *source* is a recorded event with a schedule: a single event, a fixed
(recurring) schedule or an installment plan. An *occurrence* is one dated
amount of a source in one month. ``expand`` changes sources into
occurrences, and ``statement_totals`` adds the credit-card occurrences of each
card and month into the gross total of that card statement.

Offsets. The schedule of a source counts months from its first month, offset
0. For a source that settles through a credit card, offset 0 is the statement
month of the source date (``billing_offset`` months after the month of the
date). For other sources, offset 0 is the month of the date.

This module is pure. It imports only the standard library and
``banking.card_calendar``. It reads no model, database, setting, translation
or clock: callers supply the sources, the window and the horizon.
``Transaction`` methods and ``transactions.projection`` call the rule
functions of this module, so each rule has one implementation.
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from functools import lru_cache
from itertools import islice

from banking import card_calendar
from banking.card_calendar import days_in_month

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
# A fixed source may have at most this number of monthly occurrences through
# the synchronization horizon.
MAX_MONTHLY_OCCURRENCES = 1200
# The payment channel of a source that settles through a credit-card statement.
CREDIT_CARD = "CREDIT_CARD"
# Source types.
TRANSACTION = "transaction"
LOYALTY_PURCHASE = "loyalty_purchase"
# Occurrence statuses.
# SCHEDULED: the scheduled values. ADJUSTED: an ADJUSTED override changes the
# amount or the date. EXPECTED: the source requires confirmation and the month
# has no confirmation yet; the status does not depend on the date. CONFIRMED:
# a CONFIRMED override records the actual values. SKIPPED: a SKIPPED override
# removes the month; only expand(..., include_skipped=True) returns it.
SCHEDULED = "SCHEDULED"
ADJUSTED = "ADJUSTED"
EXPECTED = "EXPECTED"
CONFIRMED = "CONFIRMED"
SKIPPED = "SKIPPED"


def month_index(value):
    """Return the number of months from January of year 0 to the month of ``value``."""
    return value.year * 12 + value.month - 1


def month_at(index):
    """Return the first day of the month with this month index."""
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


LAST_MONTH_INDEX = month_index(date.max)
# The first day of the last month in the date range: 1 December 9999.
LAST_MONTH = month_at(LAST_MONTH_INDEX)


def months_between(start, year, month):
    """Return the number of calendar months from the month of ``start`` to ``(year, month)``."""
    return (year - start.year) * 12 + (month - start.month)


def day_in_month(index, day):
    """Return the date of ``day`` in the month with this index.

    A day after the end of the month becomes the last day of the month.
    """
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day, days_in_month(year, month)))


def offset_month(value, offset):
    """Return the first day of the month ``offset`` months after the month of ``value``.

    Return None when that month is outside the date range.
    """
    year, month = divmod(month_index(value) + offset, 12)
    if not date.min.year <= year <= date.max.year:
        return None
    return date(year, month + 1, 1)


def billing_offset(purchase_date, closing_day, override=None):
    """Return the months from the month of ``purchase_date`` to its statement month.

    ``closing_day`` is None for a source that does not settle through a credit
    card; the offset is then 0. For a card, the offset is 0 or 1
    (``banking.card_calendar.statement_month``), and a statement month after
    December 9999 raises ``ValueError``.
    """
    if closing_day is None:
        return 0
    statement = card_calendar.statement_month(closing_day, purchase_date, override)
    return months_between(purchase_date, statement.year, statement.month)


def last_fixed_offset(is_fixed, start, fixed_until):
    """Return the offset of the last occurrence of an ended fixed schedule.

    ``fixed_until`` is an event date: the offset counts calendar months from
    the month of ``start`` and does not include the billing offset. Return None
    for a schedule without an end and for a source that is not fixed.
    """
    if not is_fixed or fixed_until is None:
        return None
    return max(0, months_between(start, fixed_until.year, fixed_until.month))


def installment_amount(amount, installments):
    """Return each installment after the first: the total divided by the count, rounded down to the cent.

    A source with one installment returns its amount.
    """
    if installments <= 1:
        return amount
    return (amount / installments).quantize(CENT, rounding=ROUND_DOWN)


def first_installment_amount(amount, installments):
    """Return the first installment: the total minus the other installments.

    The first installment receives the rounding remainder, so the installments
    add up to the total.
    """
    if installments <= 1:
        return amount
    return amount - installment_amount(amount, installments) * (installments - 1)


def amount_at(
    offset, amount, is_fixed, last_offset, installments, installment_start, first=None, each=None
):
    """Return the amount that a schedule assigns to the month at ``offset``.

    - A fixed schedule has its amount at each offset from 0 through
      ``last_offset`` (no end when None). Installment fields do not apply.
    - An installment plan (more than one installment) has the first
      installment at offset 0 and the other installments at offsets 1 through
      ``installments - 1``. Offsets before ``installment_start - 1`` have no
      amount.
    - A single source has its amount at offset 0.

    Other offsets return ``ZERO``. ``first`` and ``each`` can supply the
    installment amounts that a caller calculated before.
    """
    if offset < 0:
        return ZERO
    if is_fixed:
        return ZERO if last_offset is not None and offset > last_offset else amount
    if installments > 1:
        # A reviewed opening import can omit already settled installments
        # without changing the original purchase date, total or numbering.
        if offset < installment_start - 1 or offset >= installments:
            return ZERO
        if offset == 0:
            return first_installment_amount(amount, installments) if first is None else first
        return installment_amount(amount, installments) if each is None else each
    return amount if offset == 0 else ZERO


def amount_through(offset, amount, is_fixed, last_offset, installments, installment_start):
    """Return the total that a schedule assigns from its first month through the month at ``offset``.

    Installments before ``installment_start`` are not included. When the first
    tracked installment is not the first one, every tracked installment has
    the rounded-down amount: the remainder of the first installment is not
    charged again.
    """
    if offset < 0:
        return ZERO
    if is_fixed:
        if last_offset is not None:
            offset = min(offset, last_offset)
        return amount * (offset + 1)
    if installments > 1:
        paid = min(offset + 1, installments)
        tracked = max(0, paid - installment_start + 1)
        if not tracked:
            return ZERO
        each = installment_amount(amount, installments)
        if installment_start == 1:
            return first_installment_amount(amount, installments) + each * (tracked - 1)
        return each * tracked
    return amount


def split_amount(amount, capacities):
    """Allocate ``amount`` to the capacities in proportion, in whole cents.

    Each share is first rounded down to the cent. The remaining cents go to
    the shares with the largest rounded-off remainders; equal remainders go
    in capacity order (the largest-remainder method). Return one value for
    each capacity, in capacity order.
    """
    total = sum(capacities, ZERO)
    if not amount or not total:
        return [ZERO for _value in capacities]
    exact = [amount * value / total for value in capacities]
    values = [value.quantize(CENT, rounding=ROUND_DOWN) for value in exact]
    cents = int((amount - sum(values, ZERO)) * 100)
    ranking = sorted(range(len(values)), key=lambda index: (-(exact[index] - values[index]), index))
    for index in ranking[:cents]:
        values[index] += CENT
    return values


def _installment_splits(capacities, first, each):
    """Yield the category values of installment 1, 2, ... of a split installment plan.

    Each installment is allocated against the capacities that the earlier
    installments left. Independent cumulative rounding can make a small final
    category negative; this replay keeps every value nonnegative and makes the
    plan close exactly on the split amounts.
    """
    remaining = list(capacities)
    index = 0
    while True:
        values = split_amount(first if index == 0 else each, remaining)
        remaining = [capacity - value for capacity, value in zip(remaining, values, strict=False)]
        yield values
        index += 1


def installment_split(offset, capacities, first, each):
    """Return the category values of the installment at ``offset`` (0 or more)."""
    return next(islice(_installment_splits(capacities, first, each), offset, None))


def schedule_window(
    first_month,
    horizon,
    *,
    settles_on_date,
    day,
    is_fixed,
    last_offset,
    installments,
    installment_start,
):
    """Return ``(start, count)``: the first month and the number of months of an occurrence window.

    The window is the run of months that synchronization visits for a source
    through ``horizon``. It does not visit empty calendar gaps:

    - ``first_month`` is the month at offset 0, or None outside the date range.
    - An installment plan starts at its first tracked installment. A start
      after December 9999 gives ``(None, 0)``.
    - The count ends at the horizon month, at the last fixed occurrence, after
      the last installment, or after one month for a single source.
    - For a source that ``settles_on_date`` (no credit card), the last month
      does not count when the source day in that month is after the horizon.

    The 1,200 occurrence limit applies to this count.
    """
    if first_month is None:
        return None, 0
    skipped = installment_start - 1 if installments > 1 else 0
    start = first_month
    if skipped:
        index = month_index(first_month) + skipped
        if index > LAST_MONTH_INDEX:
            return None, 0
        start = month_at(index)
    count = max(0, month_index(horizon) - month_index(start) + 1)
    if is_fixed:
        if last_offset is not None:
            # fixed_until is an event offset; billing can shift its last month.
            count = min(count, last_offset + 1)
    else:
        count = min(count, installments - skipped if installments > 1 else 1)
    if count and settles_on_date:
        if day_in_month(month_index(start) + count - 1, day) > horizon:
            count -= 1
    return start, count


@dataclass(frozen=True, slots=True)
class Instrument:
    """How a source settles.

    ``channel`` is the payment channel (``ACCOUNT``, ``PIX``, ``DEBIT_CARD`` or
    ``CREDIT_CARD``). ``instrument_id`` identifies the bank account, debit
    card or credit card. ``account_id`` is the settlement account. A credit
    card also has its ``closing_day`` and ``due_day``; other instruments have
    None.
    """

    channel: str
    instrument_id: int | None
    account_id: int | None
    closing_day: int | None = None
    due_day: int | None = None

    @property
    def is_credit_card(self):
        """Return whether the source settles through a credit-card statement."""
        return self.channel == CREDIT_CARD


@lru_cache(maxsize=1024)
def instrument(channel, instrument_id, account_id, closing_day=None, due_day=None):
    """Return the ``Instrument`` with these fields.

    Many sources share few instruments. Equal calls return the same frozen
    value, which costs less than a new value for each source.
    """
    return Instrument(channel, instrument_id, account_id, closing_day, due_day)


@dataclass(frozen=True, slots=True)
class Override:
    """The override of one month of a recurring source (one ``OccurrenceOverride`` row).

    ``month`` is the first day of the reference month. ``status`` is
    ``SKIPPED``, ``ADJUSTED`` or ``CONFIRMED``. ``amount`` and ``date``
    replace the scheduled amount and the scheduled date when they are not
    None. A source with a credit card never has a ``date``.
    """

    month: date
    status: str
    amount: Decimal | None = None
    # A string: the default None would otherwise replace the type in the
    # annotation, because the field has the name of the type.
    date: "date | None" = None


@dataclass(frozen=True, slots=True)
class ScheduleSource:
    """What the engine needs from one source.

    ``source_id`` is None for an unsaved source, for example in the effect
    preview of a form. ``flow`` is the transaction type (``INCOME`` or
    ``EXPENSE``). ``currency`` is the currency of the settlement account, or
    an empty text when the caller did not load it. ``splits`` contains the
    ``(category_id, amount)`` capacities of the category split in split order:
    an empty tuple for a source without a split, and None when the caller did
    not load the split rows. ``expand(..., allocations=True)`` needs them.

    The recurring commitments of R4 apply only to a fixed source with one
    installment (``is_commitment_source``); the engine ignores them for other
    sources:

    - ``amounts``: ``(effective_month, amount)`` pairs in month order. Each
      amount applies from its month until the next pair; ``amount`` applies
      before the first pair.
    - ``overrides``: ``Override`` values in month order, at most one for each
      month.
    - ``confirmation_start``: the first reference month that needs a
      confirmation, or None when the source does not require confirmation.
      A credit-card source never needs a confirmation.
    """

    source_type: str
    source_id: int | None
    date: date
    amount: Decimal
    currency: str
    flow: str
    instrument: Instrument
    is_fixed: bool = False
    fixed_until: date | None = None
    installments: int = 1
    installment_start: int = 1
    billing_override: int | None = None
    category_id: int | None = None
    splits: tuple | None = ()
    amounts: tuple = ()
    overrides: tuple = ()
    confirmation_start: date | None = None


def is_commitment_source(source):
    """Return whether R4 amount changes, overrides and confirmation apply to ``source``.

    Only a fixed source with one installment has them. The engine ignores the
    rows of an installment plan and of a legacy fixed row with installments.
    """
    return source.is_fixed and source.installments == 1


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One dated amount of a source.

    - ``key``: ``{source_type}:{source_id}:{YYYY-MM}`` with the reference
      month. For a transaction that does not settle through a credit card,
      this is the source key of its ledger movement. None for an unsaved
      source.
    - ``economic_date``: the modeled date of the event. Single sources and
      installments have the source date. A fixed occurrence has the source day
      in its event month (the reference month minus the billing offset),
      clamped to the month length.
    - ``reference_month``: the first day of the month that receives the
      amount: the statement month for a credit card, the occurrence month
      otherwise.
    - ``cash_date``: when the occurrence changes cash. For a credit card, the
      due date of the statement, or None when ``statement_due_date`` has no
      date. Otherwise the source date, or, for a fixed source, the source day
      in the reference month, clamped to the month length.
    - ``amount``: the amount of the reference month, never zero.
    - ``allocations``: ``(category_id, amount)`` pairs that add up to
      ``amount``, or None when ``expand`` was not asked for them. A legacy
      fixed source with more than one installment is the exception: its pairs
      replay the installment split, as the readers did before the engine.
    - ``installment``: ``(number, count)`` for an installment plan (a source
      that is not fixed and has more than one installment), otherwise None.
      The number of the first tracked installment is ``installment_start``.
    - ``status``: ``SCHEDULED``, ``ADJUSTED``, ``EXPECTED``, ``CONFIRMED`` or
      ``SKIPPED`` (see the constants of this module). The ``key`` and the
      ``reference_month`` of an occurrence never change with its status: a
      confirmation dated in a later month moves only ``economic_date`` and
      ``cash_date``.
    """

    key: str | None
    source_type: str
    source_id: int | None
    economic_date: date
    reference_month: date
    cash_date: date | None
    amount: Decimal
    currency: str
    flow: str
    instrument: Instrument
    allocations: tuple | None
    installment: tuple | None
    status: str


@dataclass(frozen=True, slots=True)
class Window:
    """The occurrences that ``expand`` returns.

    - ``Window.through(horizon)`` is the synchronization window. It contains
      the occurrence window of each source (``occurrence_window``) through
      the horizon: credit-card occurrences with a reference month through the
      horizon month, and other occurrences with a cash date on or before the
      horizon. A source without recurrence and without a credit card has one
      occurrence there, on its date.
    - ``Window.months(first, last)`` contains the occurrences with a
      reference month from the month of ``first`` through the month of
      ``last``, for readers of these months.
    """

    horizon: date | None = None
    first_month: date | None = None
    last_month: date | None = None

    def __post_init__(self):
        if self.horizon is not None:
            if self.first_month is not None or self.last_month is not None:
                raise ValueError("A window has a horizon or a month range, not both.")
        elif self.first_month is None or self.last_month is None:
            raise ValueError("A window needs a horizon or a first and a last month.")
        elif month_index(self.first_month) > month_index(self.last_month):
            raise ValueError("The first month of a window cannot follow its last month.")

    @classmethod
    def through(cls, horizon):
        """Return the synchronization window through ``horizon``."""
        return cls(horizon=horizon)

    @classmethod
    def months(cls, first, last=None):
        """Return the window of the months from ``first`` through ``last`` (default: ``first``)."""
        return cls(first_month=first, last_month=first if last is None else last)


def _first_month(source, billing):
    if source.instrument.is_credit_card:
        return offset_month(source.date, billing)
    return source.date.replace(day=1)


def occurrence_window(source, horizon):
    """Return ``(start, count)`` of the occurrence window of a source through ``horizon`` (``schedule_window``)."""
    return _occurrence_window(
        source,
        horizon,
        billing_offset(source.date, source.instrument.closing_day, source.billing_override),
    )


def _occurrence_window(source, horizon, billing):
    return schedule_window(
        _first_month(source, billing),
        horizon,
        settles_on_date=not source.instrument.is_credit_card,
        day=source.date.day,
        is_fixed=source.is_fixed,
        last_offset=last_fixed_offset(source.is_fixed, source.date, source.fixed_until),
        installments=source.installments,
        installment_start=source.installment_start,
    )


def statement_due_date(instrument, reference_month):
    """Return the due date of the statement of ``reference_month`` for a credit-card instrument.

    Return None for an instrument without a card calendar, and for a due date
    after 31 December 9999 (``date.max``), so that ``expand`` can return the
    occurrences of every statement month in the date range.
    ``banking.card_calendar.due_date`` and ``CreditCard.due_date_for`` raise
    ``ValueError`` for that due date.
    """
    closing_day = instrument.closing_day
    if closing_day is None:
        return None
    due_day = instrument.due_day
    # When a card is due in the month after the statement month, its
    # December 9999 statement is due in January 10000.
    if reference_month >= LAST_MONTH and card_calendar.due_month_offset(closing_day, due_day):
        return None
    return card_calendar.due_date(closing_day, due_day, reference_month)


def _month_text(year, month):
    """Return the ``YYYY-MM`` text of a key month."""
    # strftime('%Y') does not pad a year before 1000 on every platform. Keep
    # its exact text there, so that stored movement keys do not change.
    if year >= 1000:
        return f"{year}-{month:02d}"
    return f"{date(year, month, 1):%Y-%m}"


def _offsets(source, window, billing, base, last):
    """Return the range of offsets that the window contains for a source."""
    if window.horizon is not None:
        if not source.is_fixed and not source.instrument.is_credit_card:
            # A source without recurrence and without a credit card settles
            # once, on its date. Model validation allows installments only
            # on credit cards; for a legacy installment row on an account,
            # synchronization posts only the first installment.
            return range(0, 1 if source.date <= window.horizon else 0)
        start, count = _occurrence_window(source, window.horizon, billing)
        if not count:
            return range(0)
        low = month_index(start) - base
        return range(low, low + count)
    if source.is_fixed:
        low = 0
        high = LAST_MONTH_INDEX - base if last is None else last
    elif source.installments > 1:
        low, high = source.installment_start - 1, source.installments - 1
    else:
        low = high = 0
    low = max(low, month_index(window.first_month) - base)
    high = min(high, month_index(window.last_month) - base, LAST_MONTH_INDEX - base)
    return range(low, high + 1)


def _expand_source(source, window, allocations, occurrences):
    instrument = source.instrument
    card = instrument.channel == CREDIT_CARD
    start = source.date
    amount = source.amount
    installments = source.installments
    installment_start = source.installment_start
    is_fixed = source.is_fixed
    plan = installments > 1
    # Model validation rejects a fixed source with more than one installment.
    # For such a legacy row, amount_at applies the fixed rule; the economic
    # date and the split allocations follow the installment rules, as the
    # readers before the engine did. It has no installment number, because
    # its offsets are not installments.
    numbered = plan and not is_fixed
    # The billing offset and the installment amounts are calculated once for
    # each source; the months are then arithmetic.
    billing = (
        0
        if instrument.closing_day is None
        else billing_offset(start, instrument.closing_day, source.billing_override)
    )
    base = start.year * 12 + start.month - 1 + billing
    last = last_fixed_offset(is_fixed, start, source.fixed_until) if is_fixed else None
    first = first_installment_amount(amount, installments) if plan else amount
    each = installment_amount(amount, installments) if plan else amount
    # The offsets already contain only the months of the window: for a source
    # without a credit card, only cash dates on or before the horizon.
    offsets = _offsets(source, window, billing, base, last)
    if not offsets:
        return
    allocated = None
    if allocations:
        if source.splits is None:
            raise ValueError("Allocations need the split capacities of each source.")
        if source.splits:
            category_ids = tuple(category_id for category_id, _capacity in source.splits)
            capacities = [capacity for _category_id, capacity in source.splits]
            if plan:
                replay = _installment_splits(capacities, first, each)
                replayed, values = -1, None
    source_type, source_id = source.source_type, source.source_id
    prefix = None if source_id is None else f"{source_type}:{source_id}:"
    day = start.day
    for offset in offsets:
        value = amount_at(
            offset, amount, is_fixed, last, installments, installment_start, first, each
        )
        if not value:
            continue
        index = base + offset
        year, month = divmod(index, 12)
        month += 1
        reference = date(year, month, 1)
        if card:
            cash = statement_due_date(instrument, reference)
        elif is_fixed:
            cash = day_in_month(index, day)
        else:
            cash = start
        if plan or not is_fixed:
            economic = start
        elif billing:
            economic = day_in_month(index - billing, day)
        else:
            economic = cash if not card else day_in_month(index, day)
        if allocations:
            if not source.splits:
                allocated = ((source.category_id, value),)
            elif plan:
                while replayed < offset:
                    values = next(replay)
                    replayed += 1
                allocated = tuple(zip(category_ids, values, strict=False))
            else:
                allocated = tuple(zip(category_ids, split_amount(value, capacities), strict=False))
        if prefix is None:
            key = None
        elif year >= 1000:
            key = f"{prefix}{year}-{month:02d}"  # the common case of _month_text
        else:
            key = prefix + _month_text(year, month)
        occurrences.append(
            Occurrence(
                key,
                source_type,
                source_id,
                economic,
                reference,
                cash,
                value,
                source.currency,
                source.flow,
                instrument,
                allocated,
                (offset + 1, installments) if numbered else None,
                SCHEDULED,
            )
        )


def _first_reference_index(source, billing):
    """Return the month index of offset 0 of a source."""
    return month_index(source.date) + billing


def amount_steps(source):
    """Return the scheduled amount steps of a source as ``((month, amount), ...)``.

    The first pair is the first reference month (offset 0) with the source
    amount. Each amount change (``ScheduleSource.amounts``) after that month
    adds one pair. A change at or before the first month replaces the first
    amount. A source without R4 rows, or for which they do not apply
    (``is_commitment_source``), has one pair. Package 4.4 reads these steps
    for the price-increase check.
    """
    billing = (
        0
        if source.instrument.closing_day is None
        else billing_offset(source.date, source.instrument.closing_day, source.billing_override)
    )
    first = _first_reference_index(source, billing)
    steps = [(month_at(first), source.amount)]
    if not is_commitment_source(source):
        return tuple(steps)
    for month, amount in source.amounts:
        if month_index(month) <= first:
            steps[0] = (steps[0][0], amount)
        else:
            steps.append((month, amount))
    return tuple(steps)


def scheduled_amount(source, reference_month):
    """Return the amount that the amount steps give for ``reference_month``.

    This is the amount of the last step at or before the month, or the source
    amount before the first step. Overrides do not change it, and the
    function does not check that the month has an occurrence.
    """
    index = month_index(reference_month)
    amount = source.amount
    if not is_commitment_source(source):
        return amount
    for month, value in source.amounts:
        if month_index(month) > index:
            break
        amount = value
    return amount


def _expand_commitments(source, window, allocations, include_skipped, occurrences):
    """Expand a fixed source with amount changes, overrides or confirmation (R4).

    ``_expand_source`` is the fast path for all other sources and keeps its
    loop unchanged. This path applies, for each occurrence with reference
    month index ``r``:

    1. the scheduled amount: the last amount step at or before ``r``;
    2. the override of ``r``: SKIPPED removes the occurrence (or returns it
       with status SKIPPED and the scheduled values with
       ``include_skipped``); ADJUSTED and CONFIRMED replace the amount and,
       without a card, the economic and cash dates;
    3. the status: CONFIRMED, then EXPECTED (from ``confirmation_start``,
       never for a card), then ADJUSTED, then SCHEDULED;
    4. the allocations of the final amount with ``split_amount``.

    In a synchronization window, an occurrence without a card is included
    when its final cash date is on or before the horizon.
    """
    instrument = source.instrument
    card = instrument.channel == CREDIT_CARD
    start = source.date
    billing = (
        0
        if instrument.closing_day is None
        else billing_offset(start, instrument.closing_day, source.billing_override)
    )
    base = start.year * 12 + start.month - 1 + billing
    last = last_fixed_offset(True, start, source.fixed_until)
    horizon = window.horizon
    if horizon is not None:
        # The window without the trim of the last month by the source day:
        # an override date can move a cash date into the horizon. The final
        # cash dates are filtered below. A cash date is never before its
        # reference month, so later months cannot qualify.
        first_month, count = schedule_window(
            _first_month(source, billing),
            horizon,
            settles_on_date=False,
            day=start.day,
            is_fixed=True,
            last_offset=last,
            installments=1,
            installment_start=1,
        )
        if not count:
            return
        low = month_index(first_month) - base
        offsets = range(low, low + count)
    else:
        offsets = _offsets(source, window, billing, base, last)
    if not offsets:
        return
    if allocations:
        if source.splits is None:
            raise ValueError("Allocations need the split capacities of each source.")
        category_ids = tuple(category_id for category_id, _capacity in source.splits)
        capacities = [capacity for _category_id, capacity in source.splits]
    step_indices = [month_index(month) for month, _amount in source.amounts]
    step_amounts = [amount for _month, amount in source.amounts]
    by_month = {month_index(override.month): override for override in source.overrides}
    confirmation = (
        None
        if card or source.confirmation_start is None
        else month_index(source.confirmation_start)
    )
    source_type, source_id = source.source_type, source.source_id
    prefix = None if source_id is None else f"{source_type}:{source_id}:"
    day = start.day
    for offset in offsets:
        if not amount_at(offset, source.amount, True, last, 1, 1):
            continue
        index = base + offset
        step = bisect_right(step_indices, index) - 1
        scheduled = source.amount if step < 0 else step_amounts[step]
        year, month = divmod(index, 12)
        month += 1
        reference = date(year, month, 1)
        if card:
            cash = statement_due_date(instrument, reference)
            economic = day_in_month(index - billing, day) if billing else day_in_month(index, day)
        else:
            cash = economic = day_in_month(index, day)
        override = by_month.get(index)
        value = scheduled
        if override is None:
            status = SCHEDULED
        elif override.status == SKIPPED:
            if not include_skipped:
                continue
            status = SKIPPED
        else:
            status = override.status
            if override.amount is not None:
                value = override.amount
            if override.date is not None and not card:
                cash = economic = override.date
        if (
            status != CONFIRMED
            and status != SKIPPED
            and confirmation is not None
            and index >= confirmation
        ):
            status = EXPECTED
        if horizon is not None and not card and cash > horizon:
            continue
        allocated = None
        if allocations:
            if not source.splits:
                allocated = ((source.category_id, value),)
            else:
                allocated = tuple(zip(category_ids, split_amount(value, capacities), strict=False))
        key = None if prefix is None else prefix + _month_text(year, month)
        occurrences.append(
            Occurrence(
                key,
                source_type,
                source_id,
                economic,
                reference,
                cash,
                value,
                source.currency,
                source.flow,
                instrument,
                allocated,
                None,
                status,
            )
        )


def expand(sources, window, overrides=(), *, allocations=False, include_skipped=False):
    """Return the occurrences of ``sources`` in ``window``.

    The order is deterministic: sources in the given order, and the
    occurrences of each source in month order. Months without an amount have
    no occurrence. ``allocations=True`` adds the category allocations of each
    occurrence; each source must then have its split capacities.
    ``include_skipped=True`` also returns each skipped month, with status
    ``SKIPPED`` and its scheduled values; only the monthly schedule page
    reads them. The R4 rows of a source are fields of ``ScheduleSource``.
    ``overrides`` stays reserved and must be empty; another value raises
    ``ValueError``.

    The caller limits the window: ``transactions.projection.validate_occurrences``
    rejects a fixed source with more than ``MAX_MONTHLY_OCCURRENCES`` months
    before synchronization expands it.
    """
    if overrides:
        raise ValueError("Occurrence overrides are not supported yet.")
    if not isinstance(window, Window):
        raise TypeError("window must be a transactions.schedule.Window.")
    occurrences = []
    for source in sources:
        if (source.amounts or source.overrides or source.confirmation_start is not None) and (
            source.is_fixed and source.installments == 1
        ):
            _expand_commitments(source, window, allocations, include_skipped, occurrences)
        else:
            _expand_source(source, window, allocations, occurrences)
    return occurrences


def statement_totals(occurrences, totals=None):
    """Add the credit-card occurrences into gross statement totals.

    Return a dictionary from ``(card id, reference month)`` to the sum of the
    amounts. Each total starts at ``ZERO``, so it has at least two decimal
    places. Occurrences that do not settle through a credit card, and skipped
    occurrences, are ignored. ``totals`` is an existing dictionary to add to; its keys keep their order
    and new keys follow in the order of the occurrences.
    """
    if totals is None:
        totals = {}
    for occurrence in occurrences:
        instrument = occurrence.instrument
        if instrument.is_credit_card and occurrence.status != SKIPPED:
            key = (instrument.instrument_id, occurrence.reference_month)
            totals[key] = totals.get(key, ZERO) + occurrence.amount
    return totals
