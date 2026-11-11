"""Financial calendar dates.

The financial time zone is ``settings.TIME_ZONE``, set by ``TUXEDO_TIME_ZONE``.
Product code gets today's date and the calendar date of an aware datetime from
this module. An activated Django time zone and the time zone of the host do
not change these dates. Stored datetimes stay in UTC.
"""

from django.utils import timezone


def today():
    """Return the current date in the financial time zone."""
    # Get localdate through the module at call time, without a value. Then
    # tests that patch django.utils.timezone.localdate or django.utils.timezone.now
    # also control this date.
    return timezone.localdate(timezone=timezone.get_default_timezone())


def local_date(value):
    """Return the date of the aware datetime ``value`` in the financial time zone.

    A naive datetime raises ``ValueError``. A patched ``localdate`` does not
    change the result: the date of a given instant does not depend on today.
    """
    return timezone.localtime(value, timezone.get_default_timezone()).date()
