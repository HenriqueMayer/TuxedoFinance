# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Opt-in demonstration profiles stay isolated from real financial records."""

from datetime import date
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.demo_data import seed_demo_profile
from accounts.models import UserPreference
from banking.models import (
    Bank, BankAccount, BankMovement, BankTransfer, CardInvoice, CreditCard,
    DebitCard, ExchangeRate, LoyaltyEntry, LoyaltyProgram, RewardRedemption,
)
from categories.models import Category
from categories.signals import DEFAULT_CATEGORY_NAMES
from investments.models import Asset, Investment, InvestmentProduct
from sandbox.models import ScenarioDraft
from transactions.models import Transaction


User = get_user_model()
AS_OF = date(2026, 9, 28)
OWNED_MODELS = (
    UserPreference, Bank, BankAccount, DebitCard, CreditCard, CardInvoice,
    BankTransfer, BankMovement, LoyaltyProgram, LoyaltyEntry, RewardRedemption,
    ExchangeRate, Category, Transaction, InvestmentProduct, Asset, Investment,
    ScenarioDraft,
)


def record_snapshot(user=None):
    """Capture values, timestamps and card memberships to detect unwanted edits."""
    snapshot = {}
    for model in (User, *OWNED_MODELS):
        rows = model.objects.all()
        if user is not None:
            rows = rows.filter(pk=user.pk) if model is User else rows.filter(user=user)
        snapshot[model._meta.label] = list(rows.order_by('pk').values())
    memberships = LoyaltyProgram.cards.through.objects.all()
    if user is not None:
        memberships = memberships.filter(loyaltyprogram__user=user)
    snapshot['loyalty_cards'] = list(memberships.order_by('pk').values())
    return snapshot


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


class DemoProfileContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profiles = {
            language: seed_demo_profile(
                language=language, username=f'demo_{language}',
                password=f'Isolated-{language}-test-password-29', as_of=AS_OF,
            )
            for language in ('pt', 'en')
        }

    def test_localized_content_and_date_preferences_are_distinct(self):
        self.assertEqual(self.profiles['pt'].preferences.date_format, 'DMY')
        self.assertEqual(self.profiles['en'].preferences.date_format, 'MDY')
        pt_titles = set(self.profiles['pt'].transactions.values_list('title', flat=True))
        en_titles = set(self.profiles['en'].transactions.values_list('title', flat=True))
        self.assertTrue(pt_titles - en_titles)
        self.assertTrue(en_titles - pt_titles)
        self.assertIn('Salário mensal', pt_titles)
        self.assertIn('Monthly salary', en_titles)

    def test_history_covers_twelve_past_months_and_the_reference_month(self):
        for user in self.profiles.values():
            with self.subTest(user=user.username):
                months = set(user.transactions.dates('date', 'month'))
                expected = {date(2025, month, 1) for month in range(9, 13)}
                expected.update(date(2026, month, 1) for month in range(1, 10))
                self.assertTrue(expected.issubset(months))
                self.assertEqual(
                    set(user.transactions.values_list('payment_channel', flat=True)),
                    set(Transaction.PaymentChannel.values),
                )
                self.assertEqual(
                    set(user.transactions.values_list('transaction_type', flat=True)),
                    set(Transaction.TransactionType.values),
                )
                self.assertTrue(user.transactions.filter(installments__gt=1).exists())
                self.assertTrue(user.transactions.filter(is_fixed=True, fixed_until__isnull=True).exists())
                self.assertTrue(user.transactions.filter(is_fixed=True, fixed_until__isnull=False).exists())

    def test_financial_features_have_connected_examples(self):
        for user in self.profiles.values():
            with self.subTest(user=user.username):
                for model in OWNED_MODELS:
                    self.assertTrue(model.objects.filter(user=user).exists(), model._meta.label)
                self.assertEqual(
                    set(user.credit_cards.values_list('card_type', flat=True)),
                    set(CreditCard.CardType.values),
                )
                self.assertTrue({'BRL', 'USD', 'EUR'}.issubset(
                    set(user.bank_accounts.values_list('currency', flat=True)),
                ))
                self.assertEqual(
                    set(user.investments.values_list('kind', flat=True)),
                    set(Investment.Kind.values),
                )
                self.assertEqual(
                    set(user.investment_assets.values_list('valuation_mode', flat=True)),
                    set(Asset.ValuationMode.values),
                )
                self.assertEqual(
                    set(user.investment_assets.values_list('asset_class', flat=True)),
                    set(Asset.AssetClass.values),
                )
                self.assertEqual(
                    set(user.investment_products.values_list('purpose', flat=True)),
                    set(InvestmentProduct.Purpose.values),
                )
                self.assertTrue(user.investments.filter(source_program__isnull=False).exists())
                self.assertTrue(user.investments.filter(source_account__isnull=False).exists())
                self.assertEqual(
                    set(user.loyalty_entries.values_list('kind', flat=True)),
                    set(LoyaltyEntry.Kind.values),
                )
                self.assertEqual(
                    set(user.card_invoices.values_list('status', flat=True)),
                    set(CardInvoice.Status.values),
                )
                self.assertEqual(
                    set(user.scenario_drafts.values_list('kind', flat=True)),
                    set(ScenarioDraft.Kind.values),
                )
                for redemption in user.reward_redemptions.all():
                    self.assertIsNotNone(redemption.loyalty_entry_id)
                    self.assertIsNotNone(redemption.reward_movement_id)
                for transfer in user.bank_transfers.all():
                    self.assertEqual(transfer.movements.count(), 2)
                for invoice in user.card_invoices.filter(status=CardInvoice.Status.PAID):
                    self.assertEqual(invoice.settlement_movement.amount, invoice.amount)
                    self.assertEqual(invoice.settlement_movement.account_id, invoice.card.account_id)

    def test_every_record_validates_and_every_related_owner_is_the_demo_user(self):
        for user in self.profiles.values():
            for model in OWNED_MODELS:
                for record in model.objects.filter(user=user):
                    with self.subTest(user=user.username, model=model._meta.label, pk=record.pk):
                        if model is BankMovement and record.invoice_id:
                            # CardInvoice exposes account through its card; the legacy
                            # movement clean() expects an absent invoice.account_id.
                            # Validate persisted settlement fields and links directly.
                            record.clean_fields()
                            record.validate_unique()
                            record.validate_constraints()
                            self.assertEqual(record.account_id, record.invoice.card.account_id)
                            self.assertEqual(record.kind, BankMovement.Kind.INVOICE)
                            self.assertEqual(record.direction, BankMovement.Direction.DEBIT)
                        else:
                            record.full_clean()
                        for field in model._meta.fields:
                            if field.is_relation and field.name != 'user':
                                related = getattr(record, field.name)
                                if related is not None and hasattr(related, 'user_id'):
                                    self.assertEqual(related.user_id, user.pk)
                if model is LoyaltyProgram:
                    for program in model.objects.filter(user=user):
                        self.assertFalse(program.cards.exclude(user=user).exists())

    def test_populated_pages_render_in_both_interface_languages(self):
        routes = (
            'dashboard:index', 'dashboard:reports', 'transactions:list',
            'categories:list', 'banking:list', 'banking:exchange_rates',
            'investments:list', 'investments:charts', 'investments:operations',
            'investments:settings', 'sandbox:index', 'sandbox:simulation',
            'sandbox:drafts', 'accounts:settings',
        )
        for language, user in self.profiles.items():
            self.client.force_login(user)
            locale = 'pt-br' if language == 'pt' else 'en'
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            pages = [reverse(route) for route in routes]
            pages.extend(reverse('banking:detail', args=[bank.pk]) for bank in user.banks.all())
            pages.extend(reverse('sandbox:draft_detail', args=[draft.pk]) for draft in user.scenario_drafts.all())
            for url in pages:
                with self.subTest(language=locale, url=url):
                    response = self.client.get(url, {'month': AS_OF.strftime('%Y-%m')})
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, f'<html lang="{locale}"', html=False)
            response = self.client.get(reverse('sandbox:compare'), {
                'draft': list(user.scenario_drafts.values_list('pk', flat=True)[:3]),
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['scenarios']), 3)
            for scenario in response.context['scenarios']:
                self.assertIsNotNone(scenario['result'])
