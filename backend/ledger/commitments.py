"""Write services and the read model of recurring commitments (R4).

Terms:

- A *commitment source* is a fixed transaction with one installment that no
  reward redemption manages.
- The *month* of an action is the reference month of the occurrence: the
  first day of the statement month for a credit card, of the occurrence
  month otherwise. Occurrence keys use the same month.

Each write service runs in one atomic block, locks the source, checks its
owner and eligibility, validates the row with ``full_clean`` and then
synchronizes the ledger of the user, unless ``synchronize=False``. A
``ValidationError`` has the keys ``month``, ``amount``, ``date`` or
``__all__``. A ``ProjectionLimitExceeded`` of the synchronization rolls the
write back and propagates. The services never read the request; the API
operations of ``ledger.api`` call them.
"""

from dataclasses import dataclass
from datetime import date as Date

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils.translation import gettext as _

from config import clock
from ledger import schedule
from ledger.models import OccurrenceOverride, ScheduleAmount, Transaction
from ledger.services import sync_user_ledger

# Model fields of the rows and the keys of the service errors.
_ERROR_KEYS = {"effective_month": "month", "confirmation_start": "month"}


def _service_error(error):
    """Return ``error`` with the keys of the services: ``month``, ``amount``, ``date`` or ``__all__``."""
    if not hasattr(error, "error_dict"):
        return ValidationError({"__all__": error.messages})
    mapped = {}
    for field, items in error.error_dict.items():
        key = _ERROR_KEYS.get(field, field)
        if key not in ("month", "amount", "date"):
            key = "__all__"
        mapped.setdefault(key, []).extend(items)
    return ValidationError(mapped)


def _check_month(month):
    if type(month) is not Date or month.day != 1:
        raise ValidationError({"month": _("Use the first day of the month.")})


def _locked_source(item, user):
    """Return the locked, owned commitment source of ``item``, or raise ``ValidationError``.

    SQLite takes the write lock when the atomic block starts
    (``transaction_mode`` IMMEDIATE); ``select_for_update`` keeps the same
    code correct on other databases.
    """
    locked = (
        Transaction.objects.select_for_update()
        .select_related(
            "bank_account",
            "debit_card__account",
            "credit_card__account",
        )
        .filter(pk=item.pk, user_id=user.pk)
        .first()
    )
    if locked is None or item.user_id != user.pk:
        raise ValidationError(
            {"__all__": _("This selection must belong to the transaction owner.")}, code="owner"
        )
    if locked.installments > 1:
        raise ValidationError({"__all__": _("Installment plans keep their amounts.")})
    if not locked.is_fixed or locked.reward_redemption_id:
        raise ValidationError(
            {"__all__": _("Only monthly recurring transactions have a monthly schedule.")}
        )
    return locked


def _save(row):
    try:
        row.full_clean()
    except ValidationError as error:
        raise _service_error(error) from None
    row.save()
    return row


def _finish(item, user, synchronize):
    # The caller's instance must not keep the rows that it loaded before the write.
    item.clear_schedule_rows()
    if synchronize:
        sync_user_ledger(user)


def _override(locked, month, user):
    row = OccurrenceOverride.objects.filter(transaction=locked, month=month).first()
    return row or OccurrenceOverride(user=user, transaction=locked, month=month)


def _occurrence(source, month, *, include_skipped=True):
    found = schedule.expand(
        (source,), schedule.Window.months(month), include_skipped=include_skipped
    )
    return found[0] if found else None


def change_amount_from(item, month, amount, *, user, synchronize=True):
    """Apply ``amount`` from ``month`` until the next amount change; return the ``ScheduleAmount``.

    An existing change in the same month takes the new amount. The month must
    be after the first month of the schedule and not after its last month,
    and the amount must differ from the amount that already applies then.
    Category splits keep their proportions (``schedule.split_amount``).
    """
    _check_month(month)
    with db_transaction.atomic():
        locked = _locked_source(item, user)
        row = ScheduleAmount.objects.filter(transaction=locked, effective_month=month).first()
        if row is None:
            row = ScheduleAmount(user=user, transaction=locked, effective_month=month)
        row.amount = amount
        _save(row)
        _finish(item, user, synchronize)
    return row


def remove_amount_change(item, effective_month, *, user, synchronize=True):
    """Delete the amount change of ``effective_month``; the amount before it then applies."""
    _check_month(effective_month)
    with db_transaction.atomic():
        locked = _locked_source(item, user)
        deleted, _rows = ScheduleAmount.objects.filter(
            transaction=locked, effective_month=effective_month
        ).delete()
        if not deleted:
            raise ValidationError({"month": _("This month has no amount change.")})
        _finish(item, user, synchronize)


def skip_occurrence(item, month, *, user, synchronize=True):
    """Remove the occurrence of ``month``; return the ``OccurrenceOverride`` (status SKIPPED).

    The override replaces an earlier adjustment or confirmation of the month.
    """
    _check_month(month)
    with db_transaction.atomic():
        locked = _locked_source(item, user)
        row = _override(locked, month, user)
        row.status, row.amount, row.date = OccurrenceOverride.Status.SKIPPED, None, None
        _save(row)
        _finish(item, user, synchronize)
    return row


def adjust_occurrence(item, month, *, user, amount=None, date=None, synchronize=True):
    """Change the amount or the date of the occurrence of ``month``; return the override (status ADJUSTED).

    A value equal to the scheduled value is not stored. The date stays in
    ``month``; a credit-card source has no date. When nothing differs from
    the schedule, the error asks for a change.
    """
    _check_month(month)
    with db_transaction.atomic():
        locked = _locked_source(item, user)
        row = _override(locked, month, user)
        row.status = OccurrenceOverride.Status.ADJUSTED
        scheduled = row.scheduled_occurrence()
        if scheduled is not None:
            # A month without an occurrence fails in full_clean below.
            amount = None if amount == scheduled.amount else amount
            if not locked.is_credit_card and date == scheduled.cash_date:
                date = None
            if amount is None and date is None:
                raise ValidationError({"amount": _("Change the amount or the date, or cancel.")})
        row.amount, row.date = amount, date
        _save(row)
        _finish(item, user, synchronize)
    return row


def confirm_occurrence(item, month, *, user, amount=None, date=None, today=None, synchronize=True):
    """Confirm the occurrence of ``month`` with its actual values; return the override (status CONFIRMED).

    The defaults are the expected values: the amount of the occurrence (with
    an earlier adjustment) and the earlier of its cash date and ``today``
    (default: ``core.clock.today()``). The date cannot be after today or
    before ``month``. The source must require confirmation from ``month``
    or earlier.
    """
    _check_month(month)
    today = clock.today() if today is None else today
    with db_transaction.atomic():
        locked = _locked_source(item, user)
        row = _override(locked, month, user)
        current = _occurrence(locked.schedule_source(), month, include_skipped=False)
        scheduled = row.scheduled_occurrence()
        if scheduled is not None:
            expected = current or scheduled
            if amount is None:
                amount = expected.amount
            if date is None and expected.cash_date is not None:
                date = min(expected.cash_date, today)
            amount = None if amount == scheduled.amount else amount
        row.status, row.amount, row.date = OccurrenceOverride.Status.CONFIRMED, amount, date
        row.validation_today = today
        _save(row)
        _finish(item, user, synchronize)
    return row


def restore_occurrence(item, month, *, user, synchronize=True):
    """Delete the override of ``month``: the month has its scheduled values again."""
    _check_month(month)
    with db_transaction.atomic():
        locked = _locked_source(item, user)
        deleted, _rows = OccurrenceOverride.objects.filter(transaction=locked, month=month).delete()
        if not deleted:
            raise ValidationError({"month": _("This month has no change to undo.")})
        _finish(item, user, synchronize)


def set_confirmation(item, enabled, start_month, *, user, synchronize=True):
    """Turn the confirmation of each month on from ``start_month``, or off; return the saved transaction.

    Off clears the start month. The CONFIRMED overrides of earlier months
    stay and keep their values. A credit-card source cannot require
    confirmation: its statements have their own settlement.
    """
    if enabled:
        _check_month(start_month)
    with db_transaction.atomic():
        locked = _locked_source(item, user)
        locked.requires_confirmation = bool(enabled)
        locked.confirmation_start = start_month if enabled else None
        try:
            locked.full_clean()
        except ValidationError as error:
            raise _service_error(error) from None
        locked.save(update_fields=["requires_confirmation", "confirmation_start", "updated_at"])
        item.requires_confirmation, item.confirmation_start = (
            locked.requires_confirmation,
            locked.confirmation_start,
        )
        _finish(item, user, synchronize)
    return locked


@dataclass(frozen=True, slots=True)
class MonthRow:
    """One month of the monthly schedule page (``schedule_months``).

    - ``month``: the first day of the reference month (the statement month
      for a credit card).
    - ``scheduled_amount``: the amount that the amount changes give for the
      month, without its override.
    - ``amount``: the final amount; the scheduled amount for a skipped month.
    - ``status``: ``schedule.SCHEDULED``, ``ADJUSTED``, ``EXPECTED``,
      ``CONFIRMED`` or ``SKIPPED``.
    - ``override``: the ``schedule.Override`` of the month, or None.
    - ``economic_date`` and ``cash_date``: the final dates of the occurrence.
    - ``statement_due``: the due date of the statement for a credit card,
      otherwise None.
    - ``awaiting``: the status is ``EXPECTED`` and the cash date is before
      today.
    - ``due_passed``: the cash date (for a card, the due date) is before
      today. A change of such a card month also changes the recorded
      automatic settlement of its statement.
    - ``can_skip``, ``can_adjust``, ``can_confirm``, ``can_restore``,
      ``can_change_from``: the actions that the month allows.
    """

    month: Date
    scheduled_amount: object
    amount: object
    status: str
    override: schedule.Override | None
    economic_date: Date
    cash_date: Date | None
    statement_due: Date | None
    awaiting: bool
    due_passed: bool
    can_skip: bool
    can_adjust: bool
    can_confirm: bool
    can_restore: bool
    can_change_from: bool


def _first_month_index(source):
    return schedule.month_index(schedule.amount_steps(source)[0][0])


def default_change_month(item, today):
    """Return the default month of "Change amount from month": the month of the next occurrence.

    That is the reference month of the first occurrence with a cash date (for
    a card, the due date) on or after ``today``, but at least the month after
    the first month of the schedule. A schedule without such an occurrence
    gives its last month, or the month after its first month when it has one
    month only.
    """
    source = item.schedule_source()
    first = _first_month_index(source)
    low = max(first, schedule.month_index(today) - 1)
    window = schedule.Window.months(
        schedule.month_at(low), schedule.month_at(min(low + 14, schedule.LAST_MONTH_INDEX))
    )
    found = schedule.expand((source,), window, include_skipped=True)
    for occurrence in found:
        if occurrence.cash_date is not None and occurrence.cash_date >= today:
            return schedule.month_at(
                max(schedule.month_index(occurrence.reference_month), first + 1)
            )
    last = schedule.last_fixed_offset(True, source.date, source.fixed_until)
    if last is None:
        return schedule.month_at(max(low + 1, first + 1))
    return schedule.month_at(first + max(last, 1))


def schedule_months(item, first, last, *, today):
    """Return a ``MonthRow`` for each month of the schedule from ``first`` through ``last``; never write.

    ``first`` and ``last`` are dates in the first and the last month to show.
    Months outside the schedule have no row, so the result is clipped to the
    schedule. Skipped months are included.
    """
    source = item.schedule_source()
    first_index = _first_month_index(source)
    overrides = {override.month: override for override in source.overrides}
    confirmation = None if source.instrument.is_credit_card else source.confirmation_start
    card = source.instrument.is_credit_card
    rows = []
    for occurrence in schedule.expand(
        (source,), schedule.Window.months(first, last), include_skipped=True
    ):
        month = occurrence.reference_month
        status = occurrence.status
        override = overrides.get(month)
        cash = occurrence.cash_date
        skipped = status == schedule.SKIPPED
        confirmable = confirmation is not None and month >= confirmation and month <= today
        rows.append(
            MonthRow(
                month,
                schedule.scheduled_amount(source, month),
                occurrence.amount,
                status,
                override,
                occurrence.economic_date,
                cash,
                cash if card else None,
                status == schedule.EXPECTED and cash is not None and cash < today,
                cash is not None and cash < today,
                not skipped,
                status in (schedule.SCHEDULED, schedule.ADJUSTED, schedule.EXPECTED),
                confirmable and status == schedule.EXPECTED,
                override is not None,
                schedule.month_index(month) > first_index,
            )
        )
    return tuple(rows)
