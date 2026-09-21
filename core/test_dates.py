# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from accounts.models import UserPreference
from banking.forms import BankTransferForm, ExchangeRateForm, LoyaltyEntryForm, RewardRedemptionForm
from core.dates import configure_date_fields, parse_preferred_date
from investments.forms import InvestmentForm
from transactions.forms import TransactionForm
from transactions.views import _requested_billed_month


class DateParsingTests(SimpleTestCase):
    def test_preference_is_not_guessed_and_iso_is_stable(self):
        self.assertEqual(parse_preferred_date('03/04/2026', 'DMY'), date(2026, 4, 3))
        self.assertEqual(parse_preferred_date('03/04/2026', 'MDY'), date(2026, 3, 4))
        for order in ('DMY', 'MDY'):
            self.assertEqual(parse_preferred_date('2024-02-29', order), date(2024, 2, 29))
            for invalid in ('2026-02-29', '2026-13-01', '0000-01-01', '2026-04-31', '29/02/26'):
                with self.subTest(invalid=invalid, order=order), self.assertRaises(ValidationError):
                    parse_preferred_date(invalid, order)

    def test_month_parser_rejects_out_of_range_year_without_crashing_exports(self):
        for invalid in ('0000-01', '10000-01', '2026-13', '2026-1', '2026-02-extra', '9' * 5000):
            self.assertIsNone(_requested_billed_month(invalid))
        self.assertEqual(_requested_billed_month('2026-02'), (2026, 2))

    def test_missing_user_uses_day_first(self):
        form = forms.Form()
        form.fields['date'] = forms.DateField()
        configure_date_fields(form)
        self.assertEqual(form.fields['date'].input_formats, ['%d/%m/%Y', '%Y-%m-%d'])


class PreferredDateFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dates', password='dates-test-password')
        self.client.force_login(self.user)

    def test_every_domain_form_uses_the_same_widget_and_parser(self):
        for order, expected in [('DMY', '14/08/2026'), ('MDY', '08/14/2026')]:
            UserPreference.objects.update_or_create(user=self.user, defaults={'date_format': order})
            for form_class in (TransactionForm, BankTransferForm, LoyaltyEntryForm, RewardRedemptionForm, ExchangeRateForm, InvestmentForm):
                form = form_class(user=self.user)
                fields = [field for field in form.fields.values() if isinstance(field, forms.DateField)]
                for field in fields:
                    with self.subTest(form=form_class.__name__, order=order):
                        rendered = field.widget.render('date', date(2026, 8, 14))
                        self.assertIn(f'value="{expected}"', rendered)
                        self.assertNotIn('type="date"', rendered)
                        self.assertTrue(field.widget.is_preferred_date)
                        self.assertEqual(field.clean(expected), date(2026, 8, 14))
                        self.assertEqual(field.clean('2026-08-14'), date(2026, 8, 14))

    def test_filter_canonicalizes_to_iso_and_retains_invalid_text(self):
        url = reverse('transactions:list')
        response = self.client.get(url, {'date': '14/08/2026', 'sort': 'oldest'})
        self.assertRedirects(response, url + '?date=2026-08-14&sort=oldest')
        canonical = self.client.get(url, {'date': '2026-08-14'})
        self.assertContains(canonical, 'value="14/08/2026"')
        self.assertContains(canonical, 'data-preferred-date-field')
        invalid = self.client.get(url, {'date': '31/02/2026'})
        self.assertContains(invalid, 'value="31/02/2026"')
        self.assertContains(invalid, 'Enter a valid date.')
        self.assertContains(invalid, 'aria-invalid="true"')

    def test_preference_change_reformats_existing_iso_filter_without_reinterpreting_it(self):
        UserPreference.objects.update_or_create(user=self.user, defaults={'date_format': 'MDY'})
        response = self.client.get(reverse('transactions:list'), {'date': '2026-04-03'})
        self.assertContains(response, 'value="04/03/2026"')
