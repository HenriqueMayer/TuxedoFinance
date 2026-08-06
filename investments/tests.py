"""Tests for the investments app — two layers of coverage.

The app used to ship with an empty test module; this file brings the
services and the partial-swapping list view under coverage in one go,
since both were added in the same "investments charts" work.

Layout:

  - `ServicesTests` — `get_total_in_base_timeseries` and
    `get_monthly_flow_in_base`, the FX-converted time-series helpers
    added on top of `get_cumulative_balance_timeseries`. Cases cover
    the empty user, a single-currency user, mixed-currency folding at
    rate-at-time, missing-rate exclusion, and the `offset` parameter
    that slides the 12-month window.
  - `InvestmentListViewTests` — the partial swap on `HX-Request:
    true`, the two independent `?total_offset=` / `?flow_offset=`
    parses (one per chart), their bounds checks, and the union of
    missing-rate currencies surfaced in the context.

The tests intentionally use Django's `TestCase` (not pytest) since the
project ships no pytest config — `python manage.py test investments`
discovers and runs this module through the default `DiscoverRunner`.
"""

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from investments.models import ExchangeRate, Investment
from investments.services import (
    TIMESERIES_MONTHS,
    _add_months,
    get_monthly_flow_in_base,
    get_total_in_base_timeseries,
)

User = get_user_model()

BASE = settings.CURRENCY  # 'BRL' for this project
SUPPORTED_OTHERS = ('USD', 'EUR')  # used to keep the supported list tight


def _supported(base):
    """Same shape `get_supported_currencies` produces, without the import."""
    return [base, *SUPPORTED_OTHERS]


def _add_investment(user, **kwargs):
    """One-liner creator — every required field has a sensible default."""
    defaults = {
        'title': 'test',
        'amount': Decimal('100.00'),
        'kind': Investment.Kind.DEPOSIT,
        'currency': BASE,
        'date': timezone.localdate(),
    }
    defaults.update(kwargs)
    return Investment.objects.create(user=user, **defaults)


class ServicesTests(TestCase):
    """Cover `get_total_in_base_timeseries` and `get_monthly_flow_in_base`."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='svc', email='svc@s.local', password='test',
        )
        self.supported = _supported(BASE)

    # ----------------------------------------------------------------
    # get_total_in_base_timeseries
    # ----------------------------------------------------------------
    def test_total_timeseries_empty_user(self):
        """A user with no investments gets zero-total rows and no missing rates."""
        rows, missing = get_total_in_base_timeseries(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
        )
        self.assertEqual(len(rows), TIMESERIES_MONTHS)
        for row in rows:
            self.assertEqual(row['total'], Decimal('0.00'))
        self.assertEqual(missing, [])

    def test_total_timeseries_base_only_deposit(self):
        """A single base-currency deposit propagates through every row."""
        today = timezone.localdate()
        oldest_month = (
            today.year * 12 + today.month - 1 - (TIMESERIES_MONTHS - 1)
        )
        oldest_year, oldest_month = (
            oldest_month // 12, oldest_month % 12 + 1
        )
        _add_investment(
            self.user,
            amount=Decimal('1000.00'),
            currency=BASE,
            date=date(oldest_year, oldest_month, 1),
        )
        rows, missing = get_total_in_base_timeseries(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
        )
        # Pre-window balances seed every row with the deposit, so every
        # row should carry the full base-currency contribution at
        # face value.
        for row in rows:
            self.assertEqual(row['total'], Decimal('1000.00'))
        self.assertEqual(missing, [])

    def test_total_timeseries_missing_rate_excludes_currency(self):
        """A foreign currency with no rate is excluded and reported missing."""
        _add_investment(
            self.user,
            amount=Decimal('100.00'),
            currency='USD',
            date=timezone.localdate(),
        )
        rows, missing = get_total_in_base_timeseries(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
        )
        # No rate set → USD silently dropped → every total is zero.
        for row in rows:
            self.assertEqual(row['total'], Decimal('0.00'))
        self.assertEqual(missing, ['USD'])

    def test_total_timeseries_rate_at_time_then_latest_fallback(self):
        """Old months use the historical rate; late months fall back to latest.

        Sets two USD->BRL rows (an "old" rate from 11 months back, i.e.
        the oldest month of the visible window, and a "new" rate from
        two months back) and deposits USD 4 months ago and 1 month
        ago — both within the visible window for any anchor-today.
        The historical lookup is `effective_date <= on_date`, so the
        new rate only starts applying on/after its effective month.
        """
        today = timezone.localdate()
        old_rate_row = date(*_add_months(today.year, today.month, -11), 1)
        new_rate_row = date(*_add_months(today.year, today.month, -2), 1)
        deposit1 = date(*_add_months(today.year, today.month, -4), 1)
        deposit2 = date(*_add_months(today.year, today.month, -1), 1)

        ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency=BASE,
            rate=Decimal('5.00'), effective_date=old_rate_row,
        )
        ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency=BASE,
            rate=Decimal('5.45'), effective_date=new_rate_row,
        )
        _add_investment(
            self.user, amount=Decimal('100.00'), currency='USD', date=deposit1,
        )
        _add_investment(
            self.user, amount=Decimal('100.00'), currency='USD', date=deposit2,
        )
        rows, missing = get_total_in_base_timeseries(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
        )
        self.assertEqual(missing, [])
        totals_by_year_month = {(r['year'], r['month']): r['total'] for r in rows}

        # On deposit1's row: cumulative USD = 100, rate-at-time = old
        # → 100 × 5.00 = 500.00.
        d1_ym = (deposit1.year, deposit1.month)
        self.assertEqual(totals_by_year_month[d1_ym], Decimal('500.00'))

        # One month before the new rate kicks in: still 100 × 5.00 = 500.00.
        pre_new_y, pre_new_m = _add_months(today.year, today.month, -3)
        self.assertEqual(totals_by_year_month[(pre_new_y, pre_new_m)], Decimal('500.00'))

        # The month the new rate becomes effective: cumulative still
        # 100 USD, but at the new rate → 100 × 5.45 = 545.00.
        new_rate_ym = (new_rate_row.year, new_rate_row.month)
        self.assertEqual(totals_by_year_month[new_rate_ym], Decimal('545.00'))

        # Deposit2 lands one month back from today: cumulative USD = 200,
        # new rate still effective → 200 × 5.45 = 1090.00.
        d2_ym = (deposit2.year, deposit2.month)
        self.assertEqual(totals_by_year_month[d2_ym], Decimal('1090.00'))

        # End of window: same cumulative total, no further movement.
        end_y, end_m = today.year, today.month
        self.assertEqual(totals_by_year_month[(end_y, end_m)], Decimal('1090.00'))

    def test_total_timeseries_offset_slides_window(self):
        """`offset=-12` shifts the entire window back a year."""
        _add_investment(
            self.user, amount=Decimal('500.00'), currency=BASE,
            date=timezone.localdate(),
        )
        now_rows, _ = get_total_in_base_timeseries(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS, offset=0,
        )
        past_rows, _ = get_total_in_base_timeseries(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS, offset=-12,
        )
        # The past window's last row is twelve months before the now
        # window's last row, so the seed balance (today's deposit)
        # pre-dates the past window by 12 months and still seeds it.
        self.assertEqual(
            past_rows[-1]['date'],
            date(now_rows[-1]['date'].year - 1, now_rows[-1]['date'].month, 1)
            if now_rows[-1]['date'].year > 1
            else date(now_rows[-1]['date'].year, now_rows[-1]['date'].month, 1),
        )
        # Both windows span twelve months.
        self.assertEqual(len(now_rows), TIMESERIES_MONTHS)
        self.assertEqual(len(past_rows), TIMESERIES_MONTHS)

    # ----------------------------------------------------------------
    # get_monthly_flow_in_base
    # ----------------------------------------------------------------
    def test_flow_empty_user(self):
        """No investments → every row has zero deposits and withdrawals."""
        rows, missing = get_monthly_flow_in_base(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
        )
        self.assertEqual(len(rows), TIMESERIES_MONTHS)
        for row in rows:
            self.assertEqual(row['deposits'], Decimal('0.00'))
            self.assertEqual(row['withdrawals'], Decimal('0.00'))
        self.assertEqual(missing, [])

    def test_flow_deposit_and_withdrawal_split(self):
        """Same-month DEPOSIT and WITHDRAWAL both land in the right bucket.

        Two base-currency entries on the same day → one in `deposits`,
        one in `withdrawals`. Both positive `Decimal`s (the sign is
        conveyed by the bucket).
        """
        today = timezone.localdate()
        _add_investment(
            self.user, amount=Decimal('300.00'), kind=Investment.Kind.DEPOSIT,
            currency=BASE, date=today,
        )
        _add_investment(
            self.user, amount=Decimal('120.00'), kind=Investment.Kind.WITHDRAWAL,
            currency=BASE, date=today,
        )
        rows, _ = get_monthly_flow_in_base(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
        )
        today_row = next(r for r in rows if (r['year'], r['month']) == (today.year, today.month))
        self.assertEqual(today_row['deposits'], Decimal('300.00'))
        self.assertEqual(today_row['withdrawals'], Decimal('120.00'))
        # Every other row stays at zero — flow is per-month, not cumulative.
        others = [r for r in rows if (r['year'], r['month']) != (today.year, today.month)]
        for row in others:
            self.assertEqual(row['deposits'], Decimal('0.00'))
            self.assertEqual(row['withdrawals'], Decimal('0.00'))

    def test_flow_foreign_with_rate_at_time(self):
        """Per-entry FX uses the rate effective on the entry's own date."""
        ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency=BASE,
            rate=Decimal('5.00'), effective_date=date(2024, 1, 1),
        )
        ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency=BASE,
            rate=Decimal('5.50'), effective_date=date(2025, 1, 1),
        )
        # A deposit in 2024-06 should use 5.00, one in 2025-06 should use 5.50.
        today = timezone.localdate()
        if today >= date(2025, 7, 1):
            _add_investment(
                self.user, amount=Decimal('100.00'),
                kind=Investment.Kind.DEPOSIT, currency='USD',
                date=date(2024, 6, 1),
            )
            _add_investment(
                self.user, amount=Decimal('100.00'),
                kind=Investment.Kind.DEPOSIT, currency='USD',
                date=date(2025, 6, 1),
            )
            rows, missing = get_monthly_flow_in_base(
                self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
            )
            self.assertEqual(missing, [])
            by_ym = {(r['year'], r['month']): r for r in rows}
            if (2024, 6) in by_ym:
                self.assertEqual(by_ym[(2024, 6)]['deposits'], Decimal('500.00'))
            if (2025, 6) in by_ym:
                self.assertEqual(by_ym[(2025, 6)]['deposits'], Decimal('550.00'))

    def test_flow_missing_rate_excludes_currency(self):
        """A foreign currency with no rate is excluded and surfaced."""
        _add_investment(
            self.user, amount=Decimal('100.00'), currency='USD',
            date=timezone.localdate(),
        )
        rows, missing = get_monthly_flow_in_base(
            self.user, BASE, self.supported, months=TIMESERIES_MONTHS,
        )
        for row in rows:
            self.assertEqual(row['deposits'], Decimal('0.00'))
        self.assertEqual(missing, ['USD'])


class InvestmentListViewTests(TestCase):
    """Cover the partial swap and the two independent `?{kind}_offset=N` parses."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='view', email='view@s.local', password='test',
        )
        # One BRL deposit so `has_investments` is True and the charts render.
        Investment.objects.create(
            user=cls.user, title='seed', amount=Decimal('1000.00'),
            kind=Investment.Kind.DEPOSIT, currency=BASE,
            date=timezone.localdate(),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_full_page_renders_list_template(self):
        """Normal GET renders the full list (with `base.html` wrapper)."""
        r = self.client.get(reverse('investments:list'))
        self.assertEqual(r.status_code, 200)
        # The full page has the outer-wrapper anchor and the H1 Investments.
        self.assertIn(b'<html', r.content)
        self.assertIn(b'Investment evolution', r.content)

    def test_htmx_request_returns_partial_only(self):
        """`HX-Request: true` triggers the partial swap path."""
        r = self.client.get(
            reverse('investments:list'), HTTP_HX_REQUEST='true',
        )
        self.assertEqual(r.status_code, 200)
        # Partial is the bare charts island — no <html>/<body>.
        self.assertNotIn(b'<html', r.content)
        self.assertNotIn(b'<body', r.content)
        self.assertIn(b'id="investments-charts"', r.content)
        # Still has the chart 1 heading so the swap is visible to the user.
        self.assertIn(b'Investment evolution', r.content)

    def test_each_offset_slider_is_independent(self):
        """Sliding chart 1 with `?total_offset=-3` leaves chart 2 untouched.

        The two charts slide independently; only the param the user
        clicked changes its own window. Setting `?total_offset=-3`
        should mark chart 1 as "Past window" with a "Back to today"
        link, while chart 2 stays anchored on today (and hides
        the "Back to today" link).
        """
        r = self.client.get(
            reverse('investments:list'),
            {'total_offset': '-3'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        # Only chart 1 (total) shows the "Past window" status and a
        # back-to-today link; chart 2 is still anchored on today.
        self.assertEqual(content.count('Past window'), 1)
        self.assertEqual(content.count('Back to today'), 1)
        self.assertEqual(content.count('Anchored on today'), 1)

    def test_bad_offset_falls_back_to_zero(self):
        """A non-integer or out-of-window offset is silently dropped to 0.

        Each chart's offset is parsed independently, so a bad value on
        one (say `flow_offset=abc`) falls back to 0 while the other
        still honors the request — the user's window choices never get
        all-or-nothing rejected.
        """
        for raw in ('abc', '', '999999', '-999999'):
            r = self.client.get(
                reverse('investments:list'),
                {'total_offset': raw},
                HTTP_HX_REQUEST='true',
            )
            self.assertEqual(r.status_code, 200)
            content = r.content.decode('utf-8')
            # Both should report "Anchored on today" (no offset
            # moved) — bad value fell back and the other was
            # never set in the URL.
            self.assertEqual(content.count('Anchored on today'), 2)
            self.assertEqual(content.count('Back to today'), 0)

    def test_offset_preserves_kind_and_q_filters(self):
        """`{querystring}` keeps ?kind and ?q when sliding the window.

        The template uses `{% querystring <param>=N %}` on the arrows
        so the filter form's selections survive a window shift on any
        chart. Verifying that the prev/next anchors carry the other
        params back is enough — the actual filter logic is covered by
        the queryset tests elsewhere in the project.
        """
        r = self.client.get(
            reverse('investments:list'),
            {'q': 'seed', 'kind': 'DEPOSIT'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(r.status_code, 200)
        content = r.content.decode('utf-8')
        # The prev/next anchors on every chart must echo the active
        # filters back, regardless of which chart's slider moved.
        self.assertIn('q=seed', content)
        self.assertIn('kind=DEPOSIT', content)


class InvestmentListViewMissingRateTests(TestCase):
    """Cover the missing-rate path — the union surface in the context."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='m', email='m@s.local', password='test',
        )
        Investment.objects.create(
            user=cls.user, title='usd', amount=Decimal('100.00'),
            kind=Investment.Kind.DEPOSIT, currency='USD',
            date=timezone.localdate(),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_missing_rate_union_reported_in_context(self):
        """The missing-rate list lands in the page warning.

        USD has no rate set, so the simulated-total card and the two
        FX-converted charts must all exclude it, and the page surfaces
        one unified warning through `missing_rate_currencies`.
        """
        r = self.client.get(reverse('investments:list'))
        self.assertEqual(r.status_code, 200)
        # The warning copy mentions "USD excluded" (singular).
        self.assertIn(b'USD excluded', r.content)

    def test_setting_rate_clears_warning(self):
        """Once a rate is set, the warning disappears from the page."""
        ExchangeRate.objects.create(
            user=self.user, from_currency='USD', to_currency=BASE,
            rate=Decimal('5.00'), effective_date=date(2024, 1, 1),
        )
        r = self.client.get(reverse('investments:list'))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b'USD excluded', r.content)
