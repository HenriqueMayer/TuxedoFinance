"""Exchange rates coverage for banking."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from banking.models import ExchangeRate
from banking.services import MissingExchangeRate, convert, latest_exchange_rate


User = get_user_model()


class ExchangeRateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('rates')

    def rate(self, source, target, value, on):
        return ExchangeRate.objects.create(
            user=self.user,
            from_currency=source,
            to_currency=target,
            rate=Decimal(value),
            effective_date=on,
        )

    def test_latest_rate_is_as_of_and_direct_conversion_is_supported(self):
        old = self.rate('USD', 'BRL', '5.00', date(2026, 1, 1))
        self.rate('USD', 'BRL', '6.00', date(2026, 2, 1))
        self.assertEqual(latest_exchange_rate(self.user, 'USD', 'BRL', date(2026, 1, 15)), old)
        self.assertEqual(convert(self.user, 10, 'USD', 'BRL', date(2026, 1, 15)), Decimal('50.00000000'))

    def test_inverse_and_identity_conversion(self):
        self.rate('USD', 'BRL', '5.00', date(2026, 1, 1))
        self.assertEqual(convert(self.user, 50, 'BRL', 'USD', date(2026, 1, 1)), Decimal('10'))
        self.assertEqual(convert(self.user, '7.25', 'BRL', 'BRL'), Decimal('7.25'))

    def test_missing_rate_is_explicit(self):
        with self.assertRaises(MissingExchangeRate):
            convert(self.user, 1, 'EUR', 'BRL', date(2026, 1, 1))
