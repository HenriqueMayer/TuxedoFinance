"""Yield coverage for sandbox."""

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase


D = Decimal


class YieldSimulationTests(TestCase):
    def test_month_end_cashflows_and_effective_annual_rate(self):
        from datetime import date
        from sandbox.planning import simulate_yield
        result = simulate_yield(initial=D('100'), start_month=date(2026, 12, 1), months=2, rate=D('1'),
            rate_period='monthly', contribution=D('100'), withdrawal=D('0'), overrides={})
        self.assertEqual([row['closing'] for row in result['rows']], [D('201.00'), D('303.01')])
        self.assertEqual(result['rows'][1]['month'], date(2027, 1, 1))
        annual = simulate_yield(initial=D('1000'), start_month=date(2026, 1, 1), months=12, rate=D('12'),
            rate_period='annual', contribution=D('0'), withdrawal=D('0'), overrides={})
        self.assertLess(abs(annual['ending'] - D('1120')), D('.10'))
        self.assertLess(annual['monthly_rate'], D('1'))

    def test_negative_rate_explicit_zero_override_and_overdraw_rejection(self):
        from datetime import date
        from sandbox.planning import simulate_yield
        result = simulate_yield(initial=D('100'), start_month=date(2026, 1, 1), months=1, rate=D('-10'),
            rate_period='monthly', contribution=D('100'), withdrawal=D('0'), overrides={0: (D('0'), D('0'))})
        self.assertEqual(result['ending'], D('90'))
        with self.assertRaises(ValidationError):
            simulate_yield(initial=D('100'), start_month=date(2026, 1, 1), months=1, rate=D('0'),
                rate_period='monthly', contribution=D('0'), withdrawal=D('101'), overrides={})

    def test_form_rejects_incomplete_nonfinite_rate_and_invalid_override(self):
        from sandbox.forms import YieldSimulationForm
        defaults = {'currency': 'BRL', 'start_month': '2026-09', 'months': '12', 'initial_balance': '1000',
            'rate': '1', 'rate_period': 'monthly', 'contribution': '0', 'withdrawal': '0'}
        for change in ({'rate': 'NaN'}, {'rate': '-100'}, {'months': '121'}, {'initial_balance': ''}, {'withdrawal_0': 'Infinity'}):
            with self.subTest(change=change):
                self.assertFalse(YieldSimulationForm({**defaults, **change}).is_valid())
