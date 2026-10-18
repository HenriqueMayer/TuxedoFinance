# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Demo command coverage for accounts."""

from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.demo_data import _month, seed_demo_profile
from accounts.models import UserPreference
from banking.models import Bank, BankAccount, BankMovement, BankTransfer, CardInvoice, CreditCard, DebitCard, ExchangeRate, InvoicePayment, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from banking.services import get_planning_availability
from categories.models import Category
from categories.signals import DEFAULT_CATEGORY_NAMES
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalDecision, SignalSettings
from planning.services import reserved_by_source
from sandbox.models import ScenarioDraft
from transactions.models import Transaction
from accounts.tests.snapshots import record_snapshot


User = get_user_model()


AS_OF = date(2026, 9, 28)


OWNED_MODELS = (
    UserPreference, Bank, BankAccount, DebitCard, CreditCard, CardInvoice,
    BankTransfer, BankMovement, LoyaltyProgram, LoyaltyEntry, RewardRedemption,
    ExchangeRate, Category, Transaction, InvestmentProduct, Asset, Investment,
    ScenarioDraft, InvoicePayment, PriceObservation, CategoryBudget, FinancialGoal,
    GoalAllocation, SignalSettings, SignalDecision,
)


class InsertDemoCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('private_owner', password='Private-test-password-29')
        UserPreference.objects.create(user=cls.owner, base_currency='EUR', date_format='MDY')
        bank = Bank.objects.create(user=cls.owner, name='Private institution')
        account = BankAccount.objects.create(
            user=cls.owner, bank=bank, name='Private account', currency='EUR',
            opening_balance='1234.56',
        )
        category = Category.objects.create(user=cls.owner, name='Private category')
        Transaction.objects.create(
            user=cls.owner, title='Private expense', amount='81.23', category=category,
            transaction_type=Transaction.TransactionType.EXPENSE,
            payment_channel=Transaction.PaymentChannel.ACCOUNT,
            bank_account=account, date=date(2024, 3, 12), notes='Never copy this private note',
        )

    def insert(self, language, **options):
        output = StringIO()
        call_command('insert_demo', language, '--as-of', AS_OF.isoformat(), stdout=output, **options)
        return output.getvalue()

    def test_both_commands_create_regular_accounts_without_touching_existing_data(self):
        before = record_snapshot(self.owner)
        passwords = []
        for language in ('pt', 'en'):
            with self.subTest(language=language):
                output = self.insert(language)
                user = User.objects.get(username=f'demo_{language}')
                self.assertTrue(user.is_active)
                self.assertFalse(user.is_staff)
                self.assertFalse(user.is_superuser)
                self.assertFalse(user.groups.exists())
                self.assertFalse(user.user_permissions.exists())
                self.assertIn(user.username, output)
                # Verify the printed credential by authentication, without depending
                # on a localized label or fixing a reusable demonstration password.
                candidates = [line.partition(':')[2].strip() for line in output.splitlines()]
                valid_passwords = [value for value in candidates if value and user.check_password(value)]
                self.assertEqual(len(valid_passwords), 1, output)
                passwords.extend(valid_passwords)
                self.assertNotIn('Private expense', output)
                self.assertFalse(user.transactions.filter(notes__contains='private note').exists())
        self.assertNotEqual(*passwords)
        self.assertEqual(record_snapshot(self.owner), before)

    def test_custom_username_is_supported(self):
        self.insert('en', username='conference_demo')
        self.assertTrue(User.objects.filter(username='conference_demo').exists())
        self.assertFalse(User.objects.filter(username='demo_en').exists())

    def test_existing_username_is_refused_without_any_changes(self):
        before = record_snapshot()
        for username in (self.owner.username, self.owner.username.upper()):
            with self.subTest(username=username):
                with self.assertRaises(CommandError):
                    self.insert('pt', username=username)
                self.assertEqual(record_snapshot(), before)

    def test_repeated_demo_insert_is_refused_without_any_changes(self):
        self.insert('pt')
        before = record_snapshot()
        with self.assertRaises(CommandError):
            self.insert('pt')
        self.assertEqual(record_snapshot(), before)

    def test_late_failure_rolls_back_the_entire_profile(self):
        before = record_snapshot()
        with patch(
            'accounts.demo_data.seed_investments_and_drafts',
            side_effect=RuntimeError('forced late failure'),
        ):
            with self.assertRaisesRegex((RuntimeError, CommandError), 'forced late failure'):
                self.insert('en')
        self.assertEqual(record_snapshot(), before)

    def test_invalid_locale_and_date_do_not_create_records(self):
        before = record_snapshot()
        for arguments in (
            ('de',),
            ('pt', '--as-of', 'not-a-date'),
            ('en', '--as-of', '2026-02-30'),
            ('pt', '--as-of', '1900-12-31'),
            ('en', '--as-of', '9989-01-01'),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(CommandError):
                    call_command('insert_demo', *arguments, stdout=StringIO())
                self.assertEqual(record_snapshot(), before)

    def test_distant_future_demo_keeps_unfunded_targets_without_future_confirmation(self):
        anchor = _month(date.today(), 24, 15)
        user = seed_demo_profile(language='en', username='future_demo',
                                 password='Future-demo-isolated-29', as_of=anchor)
        self.assertEqual(FinancialGoal.objects.filter(user=user).count(), 3)
        self.assertFalse(GoalAllocation.objects.filter(user=user).exists())
        self.assertFalse(InvoicePayment.objects.filter(user=user).exists())
        self.assertFalse(user.bank_movements.filter(source_key__startswith='invoice-payment:').exists())
        self.assertEqual(reserved_by_source(user), {'accounts': {}, 'cash_pots': {}})
        self.assertEqual(get_planning_availability(user)['bank_total'], Decimal('0'))

    @override_settings(ALLOW_SIGNUPS=True)
    def test_normal_signup_does_not_populate_demonstration_data(self):
        response = self.client.post(reverse('accounts:signup'), {
            'username': 'ordinary_signup',
            'email': 'ordinary@example.invalid',
            'password1': 'Independent-signup-48-password',
            'password2': 'Independent-signup-48-password',
        })
        self.assertRedirects(response, reverse('dashboard:index'), fetch_redirect_response=False)
        user = User.objects.get(username='ordinary_signup')
        for model in OWNED_MODELS:
            if model not in (UserPreference, Category):
                with self.subTest(model=model._meta.label):
                    self.assertFalse(model.objects.filter(user=user).exists())
        self.assertEqual(user.categories.count(), len(DEFAULT_CATEGORY_NAMES))
        self.assertFalse(user.categories.filter(parent_category__isnull=False).exists())
        self.assertFalse(User.objects.filter(username__in=['demo_pt', 'demo_en']).exists())
