"""Calculation-only exchange-rate reuse preserves financial evidence."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import UserPreference
from banking.models import Bank, BankAccount, ExchangeRate
from banking.services import ConversionContext, MissingExchangeRate, account_balance, account_balances, convert


class ConversionContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('conversion-owner')
        self.preference = UserPreference.for_user(self.user)
        self.day = date(2026, 9, 30)

    def test_one_preference_read_and_one_rate_query_for_many_values(self):
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='5.12345678', effective_date=self.day)
        with CaptureQueriesContext(connection) as queries:
            context = ConversionContext(self.user)
            for index in range(100):
                self.assertEqual(context.convert(Decimal('1'), 'BRL', as_of=self.day), Decimal('1'))
                self.assertEqual(context.convert(Decimal(index), 'USD', as_of=self.day), Decimal(index)*Decimal('5.12345678'))
        self.assertEqual(len(queries), 2)
        self.assertTrue(all(query['sql'].startswith('SELECT') for query in queries))

    def test_inverse_conversion_keeps_original_decimal_division(self):
        ExchangeRate.objects.create(user=self.user, from_currency='BRL', to_currency='USD', rate='3', effective_date=self.day)
        context = ConversionContext(self.user, base_currency='BRL')
        with CaptureQueriesContext(connection) as queries:
            first = context.convert(Decimal('100'), 'USD', as_of=self.day)
            second = context.convert(Decimal('7'), 'USD', as_of=self.day)
        self.assertEqual(len(queries), 2)
        self.assertEqual(first, convert(self.user, Decimal('100'), 'USD', 'BRL', self.day))
        self.assertEqual(second, Decimal('7')/Decimal('3'))

    def test_date_pair_missing_and_next_request_invalidation(self):
        older = date(2026, 9, 1)
        rate = ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='5', effective_date=older)
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='6', effective_date=self.day)
        context = ConversionContext(self.user, base_currency='BRL')
        self.assertEqual(context.convert(Decimal('1'), 'USD', as_of=older), Decimal('5'))
        self.assertEqual(context.convert(Decimal('1'), 'USD', as_of=self.day), Decimal('6'))
        with CaptureQueriesContext(connection) as queries:
            for _ in range(5):
                with self.assertRaises(MissingExchangeRate):
                    context.convert(Decimal('1'), 'EUR', as_of=self.day)
        self.assertEqual(len(queries), 2)
        ExchangeRate.objects.filter(pk=rate.pk).update(rate=Decimal('7'))
        self.assertEqual(context.convert(Decimal('1'), 'USD', as_of=older), Decimal('5'))
        self.assertEqual(ConversionContext(self.user, base_currency='BRL').convert(Decimal('1'), 'USD', as_of=older), Decimal('7'))
        UserPreference.objects.filter(user=self.user).update(base_currency='USD')
        self.assertEqual(ConversionContext(self.user).base_currency, 'USD')

    def test_context_cannot_cross_user_ownership(self):
        other = get_user_model().objects.create_user('conversion-other')
        with self.assertRaises(ValueError):
            ConversionContext(self.user).check_user(other)


class DatedAccountOpeningTests(TestCase):
    def test_dated_and_legacy_baselines_match_individual_and_grouped_balances(self):
        user = get_user_model().objects.create_user('opening-owner')
        bank = Bank.objects.create(user=user, name='Opening bank')
        dated = BankAccount.objects.create(user=user, bank=bank, name='Dated', currency='BRL', opening_balance=Decimal('100'), opening_date=date(2026, 9, 10))
        legacy = BankAccount.objects.create(user=user, bank=bank, name='Legacy', currency='BRL', opening_balance=Decimal('30'))
        for day, expected in ((date(2026, 9, 9), Decimal('0')), (date(2026, 9, 10), Decimal('100'))):
            self.assertEqual(account_balance(dated, day), expected)
            self.assertEqual(account_balance(legacy, day), Decimal('30'))
            grouped = {row['account'].pk: row['balance'] for row in account_balances(user, day)}
            self.assertEqual(grouped, {dated.pk: expected, legacy.pk: Decimal('30')})
