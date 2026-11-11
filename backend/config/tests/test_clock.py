"""Financial time zone setting and the core.clock helpers (R10).

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""

import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from banking.models import CardInvoice
from config import clock

ROOT = Path(__file__).resolve().parents[2]
PRINT_SETTINGS = "from django.conf import settings; print(settings.TIME_ZONE, settings.USE_TZ)"

# 00:30 UTC on 2026-10-19 is 21:30 on 2026-10-18 in Sao Paulo (UTC-3).
BEFORE_LOCAL_MIDNIGHT = datetime(2026, 10, 19, 0, 30, tzinfo=UTC)
# 03:30 UTC on 2026-10-19 is 00:30 on 2026-10-19 in Sao Paulo.
AFTER_LOCAL_MIDNIGHT = datetime(2026, 10, 19, 3, 30, tzinfo=UTC)
OCTOBER_18 = date(2026, 10, 18)
OCTOBER_19 = date(2026, 10, 19)


def at(instant):
    """Fix Django's current instant."""
    return patch("django.utils.timezone.now", return_value=instant)


class TimeZoneSettingTests(SimpleTestCase):
    """Settings read TUXEDO_TIME_ZONE like the other settings and validate it."""

    def run_django(self, command, *, process_value=None, file_text=""):
        """Run a Django command in a new process and return the completed process.

        The environment file is a new file with ``file_text``, so the process
        never reads an installation file. TUXEDO_TIME_ZONE of this process is
        removed; ``process_value`` sets it again.
        """
        environment = os.environ.copy()
        environment.pop("TUXEDO_TIME_ZONE", None)
        environment["SECRET_KEY"] = "clock-test-secret"
        environment["DJANGO_SETTINGS_MODULE"] = "config.settings"
        if process_value is not None:
            environment["TUXEDO_TIME_ZONE"] = process_value
        with tempfile.TemporaryDirectory(prefix="tuxedo-clock-settings-") as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(file_text, encoding="utf-8")
            environment["TUXEDO_ENV_FILE"] = str(env_file)
            environment["TUXEDO_DATA_DIR"] = directory
            return subprocess.run(
                [sys.executable, *command],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

    def settings_line(self, **options):
        result = self.run_django(["-c", PRINT_SETTINGS], **options)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_default_financial_time_zone_is_sao_paulo(self):
        self.assertEqual(self.settings_line(), "America/Sao_Paulo True")

    def test_process_environment_selects_the_time_zone(self):
        self.assertEqual(self.settings_line(process_value="UTC"), "UTC True")
        self.assertEqual(self.settings_line(process_value=" Asia/Tokyo "), "Asia/Tokyo True")

    def test_environment_file_selects_the_time_zone_and_the_process_value_wins(self):
        file_text = "TUXEDO_TIME_ZONE=Asia/Tokyo\n"
        self.assertEqual(self.settings_line(file_text=file_text), "Asia/Tokyo True")
        self.assertEqual(self.settings_line(process_value="UTC", file_text=file_text), "UTC True")

    def test_unknown_time_zone_stops_startup_with_the_variable_name(self):
        for value in ("Mars/Olympus", "", "../etc/passwd", "zone.tab"):
            with self.subTest(value=value):
                result = self.run_django(["manage.py", "check"], process_value=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)
                self.assertIn("TUXEDO_TIME_ZONE must be an IANA time zone name", result.stderr)
                self.assertIn(f"{value!r} is not a known time zone.", result.stderr)


@override_settings(TIME_ZONE="America/Sao_Paulo", USE_TZ=True)
class FinancialClockTests(SimpleTestCase):
    """config.clock uses the financial time zone, never the active or host zone."""

    def test_today_uses_the_financial_time_zone(self):
        with at(BEFORE_LOCAL_MIDNIGHT):
            self.assertEqual(clock.today(), OCTOBER_18)
            with self.settings(TIME_ZONE="UTC"):
                self.assertEqual(clock.today(), OCTOBER_19)
        with at(AFTER_LOCAL_MIDNIGHT):
            self.assertEqual(clock.today(), OCTOBER_19)

    def test_today_ignores_an_activated_time_zone(self):
        with at(BEFORE_LOCAL_MIDNIGHT):
            for zone in ("UTC", "Pacific/Kiritimati"):
                with self.subTest(zone=zone), timezone.override(zone):
                    self.assertEqual(timezone.localdate(), OCTOBER_19)
                    self.assertEqual(clock.today(), OCTOBER_18)

    def test_today_ignores_the_host_time_zone(self):
        # Django copies TIME_ZONE to the process TZ variable. Another host zone
        # changes the host date, but not the financial date.
        previous = os.environ.get("TZ")

        def restore():
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            time.tzset()

        self.addCleanup(restore)
        os.environ["TZ"] = "Pacific/Kiritimati"
        time.tzset()
        self.assertEqual(date.fromtimestamp(BEFORE_LOCAL_MIDNIGHT.timestamp()), OCTOBER_19)
        with at(BEFORE_LOCAL_MIDNIGHT):
            self.assertEqual(clock.today(), OCTOBER_18)

    def test_a_patched_localdate_controls_today(self):
        # Phase 0 tests fix the day with this patch; core.clock must follow it.
        with patch("django.utils.timezone.localdate", return_value=date(2026, 3, 15)):
            self.assertEqual(clock.today(), date(2026, 3, 15))

    def test_local_date_converts_an_aware_datetime_in_the_financial_time_zone(self):
        self.assertEqual(clock.local_date(BEFORE_LOCAL_MIDNIGHT), OCTOBER_18)
        self.assertEqual(clock.local_date(AFTER_LOCAL_MIDNIGHT), OCTOBER_19)
        with timezone.override("Pacific/Kiritimati"):
            self.assertEqual(clock.local_date(BEFORE_LOCAL_MIDNIGHT), OCTOBER_18)
        with self.settings(TIME_ZONE="UTC"):
            self.assertEqual(clock.local_date(BEFORE_LOCAL_MIDNIGHT), OCTOBER_19)
        # A fixed "today" does not change the date of a given instant.
        with patch("django.utils.timezone.localdate", return_value=date(2026, 3, 15)):
            self.assertEqual(clock.local_date(BEFORE_LOCAL_MIDNIGHT), OCTOBER_18)
        with self.assertRaises(ValueError):
            clock.local_date(datetime(2026, 10, 19, 0, 30))

    def test_invoice_due_date_stays_current_until_local_midnight(self):
        # Only a manual invoice can be overdue: an automatic invoice is paid on
        # its due date. The status is calculated as of today.
        invoice = CardInvoice(due_date=OCTOBER_18, amount=Decimal("10.00"), manual_settlement=True)
        with at(BEFORE_LOCAL_MIDNIGHT):
            # 21:30 on the due date in Sao Paulo: the invoice is not overdue yet.
            self.assertFalse(invoice.is_overdue)
            with self.settings(TIME_ZONE="UTC"):
                # The UTC calendar of earlier versions ended the due day at 21:00.
                self.assertTrue(invoice.is_overdue)
        with at(AFTER_LOCAL_MIDNIGHT):
            # 00:30 on the next local day.
            self.assertTrue(invoice.is_overdue)
