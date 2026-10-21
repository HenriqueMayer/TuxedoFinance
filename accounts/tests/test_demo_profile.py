# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Demo profile coverage for accounts."""

from datetime import date, timedelta
from decimal import Decimal
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from accounts.demo_data import seed_demo_profile
from accounts.models import UserPreference
from banking.models import Bank, BankAccount, BankMovement, BankTransfer, CardInvoice, CreditCard, DebitCard, ExchangeRate, InvoicePayment, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from banking.services import account_balance, get_planning_availability
from categories.models import Category
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation
from investments.positions import get_portfolio_valuation
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalDecision, SignalSettings
from planning.services import budget_progress, goal_progress, local_signals, reserved_by_source
from sandbox.models import ScenarioDraft
from transactions.models import Transaction


AS_OF = date(2026, 9, 28)


OWNED_MODELS = (
    UserPreference, Bank, BankAccount, DebitCard, CreditCard, CardInvoice,
    BankTransfer, BankMovement, LoyaltyProgram, LoyaltyEntry, RewardRedemption,
    ExchangeRate, Category, Transaction, InvestmentProduct, Asset, Investment,
    ScenarioDraft, InvoicePayment, PriceObservation, CategoryBudget, FinancialGoal,
    GoalAllocation, SignalSettings, SignalDecision,
)


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
                    if invoice.manual_settlement:
                        self.assertEqual(invoice.confirmed_amount, invoice.amount)
                        self.assertFalse(BankMovement.objects.filter(user=user, source_key=f'invoice:{invoice.pk}').exists())
                    else:
                        self.assertEqual(invoice.settlement_movement.amount, invoice.amount)
                        self.assertEqual(invoice.settlement_movement.account_id, invoice.card.account_id)

    def test_manual_demo_invoices_post_only_the_confirmed_partial_payment(self):
        for user in self.profiles.values():
            with self.subTest(user=user.username):
                invoices = user.card_invoices.filter(manual_settlement=True)
                self.assertEqual(invoices.count(), 2)
                overdue = invoices.get(status=CardInvoice.Status.OVERDUE)
                partial = invoices.get(status=CardInvoice.Status.PARTIAL)
                self.assertEqual(overdue.amount, Decimal('420'))
                self.assertEqual(overdue.confirmed_amount, Decimal('0'))
                self.assertEqual(partial.amount, Decimal('360'))
                self.assertEqual(partial.remaining_amount, Decimal('180'))
                self.assertLess(overdue.due_date, AS_OF)
                payment = partial.payments.get()
                self.assertEqual(payment.amount, Decimal('180'))
                self.assertLessEqual(payment.date, AS_OF)
                self.assertEqual(payment.movement.amount, payment.amount)
                self.assertEqual(payment.movement.source_key, f'invoice-payment:{payment.pk}')
                self.assertEqual(payment.movement.effective_date, payment.date)
                self.assertFalse(user.bank_movements.filter(source_key__in=[f'invoice:{item.pk}' for item in invoices]).exists())

    def test_category_budgets_real_goals_and_explained_signals_are_connected(self):
        for user in self.profiles.values():
            with self.subTest(user=user.username):
                rows = budget_progress(user, AS_OF.replace(day=1), as_of=AS_OF)
                self.assertEqual(len(rows), 3)
                self.assertTrue(all(row['complete'] for row in rows))
                self.assertTrue(any(row['over_budget'] for row in rows))
                goals = goal_progress(user, as_of=AS_OF)
                self.assertEqual(len(goals), 3)
                self.assertTrue(all(row['complete'] and row['progress'] > 0 and not row['has_shortfall'] for row in goals))
                self.assertEqual({row['goal'].currency for row in goals}, {'BRL', 'USD'})
                sources = reserved_by_source(user, AS_OF)
                self.assertEqual(len(sources['accounts']), 2)
                self.assertEqual(len(sources['cash_pots']), 1)
                availability = get_planning_availability(user, AS_OF)
                for row in availability['account_rows']:
                    named = sources['accounts'].get(row['account'].pk, Decimal('0'))
                    expected = min(max(row['account'].reserved_amount, named), max(row['balance'], Decimal('0')))
                    if not row['account'].planning_enabled:
                        expected = max(row['balance'], Decimal('0'))
                    self.assertEqual(row['reserved'], expected)
                cash = availability['cash_pots'][0]
                self.assertEqual(cash['reserved'], Decimal('1200'))
                self.assertEqual(cash['available'], cash['balance'] - Decimal('1200'))
                signals = local_signals(user, as_of=AS_OF)['signals']
                self.assertTrue({'duplicates', 'subscriptionincrease', 'budgetoverspend', 'futurecashshortage'}.issubset({item['kind'] for item in signals}))
                self.assertTrue(any(item['decision'] is not None for item in signals))
                self.assertTrue(any(item['kind'] == 'duplicates' and item['decision'] is None for item in signals))
                self.assertTrue(all(item['explanation'] and item['sources'] for item in signals))
                forecast = user.bank_accounts.get(opening_balance=Decimal('100'))
                self.assertEqual(account_balance(forecast, AS_OF), Decimal('100'))
                self.assertEqual(account_balance(forecast, AS_OF + timedelta(days=10)), Decimal('-100'))

    def test_unit_valuations_have_dated_fictional_local_sources_and_known_openings(self):
        for user in self.profiles.values():
            with self.subTest(user=user.username):
                self.assertFalse(user.bank_accounts.filter(opening_date__isnull=True).exists())
                self.assertFalse(user.investment_assets.filter(opening_date__isnull=True).exists())
                observations = user.investment_prices.all()
                self.assertEqual(observations.count(), 39)
                self.assertTrue(all('sintética' in item.source or 'Synthetic' in item.source for item in observations))
                valuation = get_portfolio_valuation(user, AS_OF)
                unit_rows = [row for row in valuation['positions'] if row['asset'].valuation_mode == Asset.ValuationMode.UNITS]
                self.assertEqual(len(unit_rows), 3)
                for row in unit_rows:
                    observation = row['asset'].price_observations.filter(date__lte=AS_OF).order_by('-date').first()
                    self.assertEqual(row['valuation'], row['quantity'] * observation.unit_price)
                    self.assertEqual(row['price_observation'].pk, observation.pk)
                    self.assertFalse(row['baseline_unknown'])
                self.assertTrue(valuation['complete'])
                self.assertTrue(valuation['performance_complete'])

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
            'dashboard:index', 'analytics:index', 'transactions:list',
            'categories:list', 'banking:list', 'banking:exchange_rates',
            'investments:list', 'analytics:investments', 'investments:operations',
            'investments:settings', 'sandbox:index', 'sandbox:simulation',
            'sandbox:drafts', 'accounts:settings', 'planning:index', 'planning:tools',
            'planning:goals', 'planning:signals', 'banking:invoices', 'investments:prices',
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
                    legacy_tools = url == reverse('planning:tools')
                    response = self.client.get(url, {'month': AS_OF.strftime('%Y-%m')}, follow=legacy_tools)
                    if legacy_tools:
                        self.assertEqual(response.redirect_chain, [(
                            reverse('sandbox:index') + f'?month={AS_OF:%Y-%m}', 302)])
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, f'<html lang="{locale}"', html=False)
            response = self.client.get(reverse('sandbox:compare'), {
                'draft': list(user.scenario_drafts.values_list('pk', flat=True)[:3]),
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['scenarios']), 3)
            for scenario in response.context['scenarios']:
                self.assertIsNotNone(scenario['result'])
