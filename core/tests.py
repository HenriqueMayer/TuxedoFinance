import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.utils.formats import get_format, number_format

from core.currencies import CURRENCIES, DEFAULT_CURRENCY, get_currency


class CurrencyRegistryTests(SimpleTestCase):
    """PRD FR20 — the supported currencies and their number formats."""

    def test_every_currency_is_keyed_by_its_own_code(self):
        for code, currency in CURRENCIES.items():
            self.assertEqual(code, currency.code)

    def test_every_currency_is_fully_populated(self):
        for currency in CURRENCIES.values():
            self.assertTrue(currency.symbol)
            self.assertTrue(currency.name)
            self.assertTrue(currency.decimal_separator)
            self.assertTrue(currency.thousand_separator)

    def test_separators_are_never_the_same_character(self):
        # `1.000.00` would be unreadable and unparseable.
        for currency in CURRENCIES.values():
            self.assertNotEqual(
                currency.decimal_separator,
                currency.thousand_separator,
                f'{currency.code} uses the same character for both separators',
            )

    def test_known_currencies_use_their_conventional_format(self):
        expected = {
            'BRL': ('R$', ',', '.'),
            'USD': ('$', '.', ','),
            'EUR': ('€', ',', '.'),
            'GBP': ('£', '.', ','),
        }
        for code, (symbol, decimal, thousand) in expected.items():
            currency = get_currency(code)
            self.assertEqual(currency.symbol, symbol)
            self.assertEqual(currency.decimal_separator, decimal)
            self.assertEqual(currency.thousand_separator, thousand)

    def test_example_renders_a_sample_amount(self):
        self.assertEqual(get_currency('BRL').example(), 'R$ 1.000,00')
        self.assertEqual(get_currency('USD').example(), '$ 1,000.00')

    def test_default_currency_is_supported(self):
        self.assertIn(DEFAULT_CURRENCY, CURRENCIES)

    def test_unknown_currency_raises_rather_than_falling_back(self):
        # Silently defaulting would label every amount in the app with the
        # wrong symbol — a correctness bug, not a cosmetic one.
        with self.assertRaises(ImproperlyConfigured) as ctx:
            get_currency('BRl')
        message = str(ctx.exception)
        self.assertIn('BRl', message)
        # The error has to say what *is* allowed, or it is a dead end.
        for code in CURRENCIES:
            self.assertIn(code, message)


class ActiveCurrencyTests(SimpleTestCase):
    """The configured currency, its symbol, and its separators must agree.

    These pass under **any** `CURRENCY`, so running the suite with
    `CURRENCY=USD uv run python manage.py test` verifies the whole switch
    end-to-end rather than just the default.
    """

    def setUp(self):
        self.currency = get_currency(settings.CURRENCY)

    def test_currency_setting_is_supported(self):
        self.assertIn(settings.CURRENCY, CURRENCIES)

    def test_currency_symbol_is_derived_from_the_registry(self):
        # Not hardcoded in settings.py — otherwise symbol and separators
        # could drift apart and produce e.g. "$ 1.000,00".
        self.assertEqual(settings.CURRENCY_SYMBOL, self.currency.symbol)

    def test_active_number_format_matches_the_active_currency(self):
        # This is the link that `core/formats/en/formats.py` provides; if it
        # were hardcoded, this fails the moment CURRENCY changes.
        self.assertEqual(get_format('DECIMAL_SEPARATOR'), self.currency.decimal_separator)
        self.assertEqual(
            get_format('THOUSAND_SEPARATOR'), self.currency.thousand_separator
        )

    def test_thousands_grouping_is_enabled(self):
        self.assertTrue(settings.USE_THOUSAND_SEPARATOR)
        self.assertEqual(get_format('NUMBER_GROUPING'), 3)

    def test_amounts_render_in_the_configured_format(self):
        formatted = number_format(Decimal('1234567.89'), 2, force_grouping=True)
        self.assertEqual(
            formatted,
            f'1{self.currency.thousand_separator}234'
            f'{self.currency.thousand_separator}567'
            f'{self.currency.decimal_separator}89',
        )

    def test_language_stays_english(self):
        # Switching LANGUAGE_CODE would have produced the same numbers while
        # also translating Django's own UI strings — see core/formats/en/.
        self.assertTrue(settings.LANGUAGE_CODE.startswith('en'))


class SecretKeyGuardTests(SimpleTestCase):
    """`SECRET_KEY` must never be the published fallback in production.

    The fallback is committed to a public template repository, so anyone can
    read it and forge session cookies or password-reset tokens against a fork
    still using it. `check --deploy` only warns; `core/settings.py` refuses to
    boot instead.

    These run `manage.py` in a subprocess because the guard fires at settings
    *import* time — there is no way to exercise it with `override_settings`.
    """

    def _check(self, **environment):
        """Run `manage.py check` in a fresh process. `None` unsets a variable."""
        child_environment = {**os.environ, **environment}
        for name, value in environment.items():
            if value is None:
                child_environment.pop(name, None)
        return subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            cwd=Path(settings.BASE_DIR),
            env=child_environment,
            capture_output=True,
            text=True,
        )

    def test_the_fallback_key_is_the_one_actually_in_use_when_unset(self):
        # Guards against the comparison in settings.py going stale: if the
        # fallback were edited without updating the constant, the check below
        # would silently never fire again.
        self.assertTrue(settings.INSECURE_SECRET_KEY.startswith('django-insecure-'))

    def test_production_without_a_real_secret_key_refuses_to_start(self):
        result = self._check(
            DEBUG='False', ALLOWED_HOSTS='example.com', SECRET_KEY=None
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY', result.stderr)
        # The error has to say how to fix it, not just that it is wrong.
        self.assertIn('get_random_secret_key', result.stderr)

    def test_production_with_a_blank_secret_key_refuses_to_start(self):
        # `SECRET_KEY=` left empty in .env is the likeliest way to get this
        # wrong, and Django boots happily on an empty key — so blank has to
        # count as unset rather than slipping past the guard.
        result = self._check(DEBUG='False', ALLOWED_HOSTS='example.com', SECRET_KEY='  ')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY', result.stderr)

    def test_production_with_a_real_secret_key_starts(self):
        result = self._check(
            DEBUG='False',
            ALLOWED_HOSTS='example.com',
            SECRET_KEY='a-real-key-that-is-long-and-unique-enough-for-this-test',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_development_still_runs_on_the_fallback(self):
        # The whole point of the fallback: `manage.py runserver` works on a
        # fresh clone with no .env at all.
        result = self._check(DEBUG='True', SECRET_KEY=None)
        self.assertEqual(result.returncode, 0, result.stderr)


class HttpsSettingsTests(SimpleTestCase):
    """PRD §10.5 — the TLS hardening switch flips every related setting.

    Kept on its own `HTTPS` flag rather than on `DEBUG`: the shipped
    docker-compose.yml serves plain HTTP, where a `Secure` cookie is never
    sent and `SECURE_SSL_REDIRECT` would loop.
    """

    HTTPS_SETTINGS = (
        'SESSION_COOKIE_SECURE',
        'CSRF_COOKIE_SECURE',
        'SECURE_SSL_REDIRECT',
        'SECURE_HSTS_INCLUDE_SUBDOMAINS',
        'SECURE_HSTS_PRELOAD',
    )

    def test_every_https_setting_tracks_the_single_flag(self):
        for name in self.HTTPS_SETTINGS:
            self.assertEqual(
                getattr(settings, name),
                settings.HTTPS,
                f'{name} disagrees with HTTPS={settings.HTTPS}',
            )

    def test_hsts_is_only_sent_over_tls(self):
        # A stray HSTS header pins browsers to HTTPS for a year and is
        # painful to undo, so it must be exactly zero without TLS.
        if settings.HTTPS:
            self.assertGreater(settings.SECURE_HSTS_SECONDS, 0)
        else:
            self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_the_forwarded_proto_header_is_only_trusted_over_tls(self):
        # Clients can forge X-Forwarded-Proto when no proxy strips it, so it
        # must not be trusted unless TLS termination is actually declared.
        if settings.HTTPS:
            self.assertEqual(
                settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https')
            )
        else:
            self.assertIsNone(settings.SECURE_PROXY_SSL_HEADER)
