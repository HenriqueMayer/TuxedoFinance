# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Arithmetic schedules for the monthly ledger projection."""
from datetime import date
from calendar import monthrange

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _


MAX_MONTHLY_OCCURRENCES = 1200
DEFAULT_PROJECTION_MONTHS = 12


class ProjectionLimitExceeded(ValidationError):
    def __init__(self):
        super().__init__(
            _('This recurring transaction would generate more than %(limit)s monthly occurrences. Review its start and end dates.'),
            code='projection_limit', params={'limit': MAX_MONTHLY_OCCURRENCES},
        )


def month_index(value):
    return value.year * 12 + value.month - 1


def month_at(index):
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


def projection_horizon(reference=None, months=DEFAULT_PROJECTION_MONTHS):
    reference = reference or timezone.localdate()
    target = month_at(month_index(reference) + months)
    return target.replace(day=min(reference.day, monthrange(target.year, target.month)[1]))


def occurrence_window(item, horizon):
    """Count actual billed occurrences without traversing empty calendar gaps."""
    start = item.billed_month if item.is_credit_card else item.date.replace(day=1)
    if start is None:
        return None, 0
    count = max(0, month_index(horizon) - month_index(start) + 1)
    if item.is_fixed:
        if item.last_fixed_offset is not None:
            # fixed_until is an event offset; billing can shift its last month.
            count = min(count, item.last_fixed_offset + 1)
    else:
        count = min(count, item.installments if item.is_installment_plan else 1)
    if count and not item.is_credit_card:
        last = month_at(month_index(start) + count - 1)
        effective = last.replace(day=min(item.date.day, monthrange(last.year, last.month)[1]))
        if effective > horizon:
            count -= 1
    return start, count


def occurrence_months(item, horizon):
    start, count = occurrence_window(item, horizon)
    if count:
        first = month_index(start)
        for offset in range(count):
            yield month_at(first + offset)


def validate_occurrences(item, horizon=None):
    if item.is_fixed and isinstance(item.date, date):
        _start, count = occurrence_window(item, horizon or projection_horizon())
        if count > MAX_MONTHLY_OCCURRENCES:
            raise ProjectionLimitExceeded()
