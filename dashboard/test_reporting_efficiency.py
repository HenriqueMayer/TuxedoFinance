"""Shared conversion, split compositions and manual forecasts stay consistent."""
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from django.db import connection
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import UserPreference
from banking.models import BankMovement, CardInvoice, CreditCard, ExchangeRate, InvoicePayment
from banking.services import ConversionContext
from banking.settlements import save_invoice_payment
from categories.models import Category
from dashboard.details import composition
from dashboard.services import (_expenses_by_category, _transactions, get_account_evolution,
                                get_dashboard_summary, get_expenses_by_recurrence,
                                get_instrument_activity, get_ledger_snapshot)
from dashboard.tests import DashboardFixture
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation
from transactions.models import Transaction, TransactionSplit
from transactions.services import sync_user_ledger
from transactions.test_projection_efficiency import writes


class ReportingEfficiencyTests(DashboardFixture):
    def test_shared_report_sources_reject_foreign_and_mixed_ownership(self):
        other = get_user_model().objects.create_user('foreign-reporting-owner')
        own = self.transaction()
        foreign = Transaction(user=other)
        for service in (get_account_evolution, get_instrument_activity, get_expenses_by_recurrence):
            for sources in ([foreign], [own, foreign]):
                with self.subTest(service=service.__name__, mixed=len(sources) > 1):
                    with self.assertRaisesRegex(ValueError, 'exactly one user'):
                        service(self.user, transactions=sources)

    def test_reports_share_one_owned_source_read_across_chart_islands(self):
        self.transaction()
        self.client.get(reverse('dashboard:reports'))
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse('dashboard:reports'))
        source_reads = [query for query in captured if 'FROM "transactions_transaction"' in query['sql']]
        # One read reconciles the ledger; one loads categorized sources for all
        # three report islands. Each island still applies its own date scope.
        self.assertEqual(len(source_reads), 2)
        self.assertEqual(response.context['instrument_activity']['expense_total'], Decimal('100'))
        self.assertEqual(writes(captured), [])

    def test_summary_preference_queries_do_not_grow_per_event(self):
        UserPreference.for_user(self.user)
        self.transaction(date=date(2026, 9, 1))
        with patch('dashboard.services.timezone.localdate', return_value=date(2026, 9, 15)):
            with CaptureQueriesContext(connection) as small:
                get_dashboard_summary(self.user, 2026, 9)
            for index in range(29):
                self.transaction(title=f'Expense {index}', date=date(2026, 9, 1))
            with CaptureQueriesContext(connection) as large:
                get_dashboard_summary(self.user, 2026, 9)
        preference = lambda rows: [row for row in rows if 'accounts_userpreference' in row['sql']]
        self.assertEqual(len(preference(small)), 1)
        self.assertEqual(len(preference(large)), 1)
        self.assertEqual(len(small), len(large))
        self.assertEqual(writes(large), [])

    def test_warm_dashboard_and_reports_gets_do_not_rewrite_ledger(self):
        UserPreference.for_user(self.user)
        self.transaction(is_fixed=True)
        for name in ('dashboard:index', 'dashboard:reports'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
            before = list(BankMovement.objects.order_by('pk').values())
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(writes(queries), [])
            self.assertEqual(before, list(BankMovement.objects.order_by('pk').values()))

    def test_split_categories_reconcile_fx_occurrence_and_source_amounts(self):
        other = Category.objects.create(user=self.user, name='Other split')
        self.account.currency = 'USD'
        self.account.save(update_fields=['currency'])
        ExchangeRate.objects.create(user=self.user, from_currency='BRL', to_currency='USD', rate='3', effective_date=date(2026, 9, 1))
        item = self.transaction(amount=Decimal('10.01'), date=date(2026, 9, 1))
        TransactionSplit.objects.create(transaction=item, category=self.category, amount=Decimal('3.33'))
        TransactionSplit.objects.create(transaction=item, category=other, amount=Decimal('6.68'))
        context = ConversionContext(self.user, base_currency='BRL')
        rows, missing = _expenses_by_category(self.user, _transactions(self.user), 2026, 9, 1, conversion=context)
        self.assertEqual(missing, [])
        self.assertEqual(sum((row['total'] for row in rows), Decimal('0')), Decimal('10.01')/Decimal('3'))
        counts = (Transaction.objects.count(), BankMovement.objects.count())
        result = composition(self.user, {'scope': 'instruments', 'series': 'expenses', 'period': '2026-09'}, conversion=context)
        self.assertEqual({row['label'] for row in result['rows']}, {self.category.name, other.name})
        for row in result['rows']:
            self.assertEqual(len(row['sources']), 1)
            self.assertEqual(row['sources'][0]['url'], reverse('transactions:update', args=[item.pk]))
            self.assertEqual(row['sources'][0]['cents'], row['cents'])
        filtered = composition(self.user, {'scope': 'instruments', 'series': 'expenses', 'period': '2026-09', 'category': other.pk}, conversion=context)
        self.assertEqual(len(filtered['rows']), 1)
        self.assertEqual(filtered['rows'][0]['label'], other.name)
        self.assertEqual(counts, (Transaction.objects.count(), BankMovement.objects.count()))

    def test_installment_category_cents_reconcile_native_allocations_over_time(self):
        other = Category.objects.create(user=self.user, name='Installment split')
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Split card', closing_day=31, due_day=28)
        item = self.transaction(amount=Decimal('10'), date=date(2026, 9, 1), payment_channel='CREDIT_CARD', bank_account=None, credit_card=card, installments=3)
        TransactionSplit.objects.create(transaction=item, category=self.category, amount=Decimal('3.33'))
        TransactionSplit.objects.create(transaction=item, category=other, amount=Decimal('6.67'))
        result = composition(self.user, {'scope': 'instruments', 'series': 'expenses', 'periods': ['2026-09', '2026-10', '2026-11']})
        self.assertEqual({row['label']: row['cents'] for row in result['rows']}, {self.category.name: '333', other.name: '667'})
        self.assertTrue(all(len(row['sources']) == 1 for row in result['rows']))

    def test_manual_obligation_forecast_preserves_real_cash_and_carries_overdue(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual card', closing_day=31, due_day=28, manual_settlement_from=date(2026, 9, 1))
        self.transaction(date=date(2026, 9, 1), payment_channel='CREDIT_CARD', bank_account=None, credit_card=card)
        sync_user_ledger(self.user, date(2026, 10, 12))
        invoice = CardInvoice.objects.get(card=card)
        save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=self.account, amount=Decimal('40'), date=date(2026, 10, 1)))
        context = ConversionContext(self.user, base_currency='BRL')
        actual = get_ledger_snapshot(self.user, date(2026, 10, 12), conversion=context)
        projected = get_ledger_snapshot(self.user, date(2026, 10, 31), conversion=context, projected=True, forecast_from=date(2026, 10, 12))
        past = get_ledger_snapshot(self.user, date(2026, 9, 30), conversion=context, projected=True, forecast_from=date(2026, 10, 12))
        self.assertEqual(actual['total'], Decimal('960'))
        self.assertEqual(projected['total'], Decimal('900'))
        self.assertEqual(past['total'], Decimal('1000'))
        result = composition(self.user, {'scope': 'ledger', 'series': 'balance', 'period': '2026-10', 'projected': True, 'forecast_from': '2026-10-12'}, conversion=context)
        row = result['rows'][0]
        self.assertEqual(row['cents'], '90000')
        invoice_source = next(source for source in row['sources'] if source['url'] == reverse('banking:invoice_detail', args=[invoice.pk]))
        self.assertEqual(invoice_source['cents'], '-6000')
        self.assertEqual(sum(int(source['cents']) for source in row['sources']), int(row['cents']))
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 1)

    def test_portfolio_composition_values_remaining_units_not_sale_proceeds(self):
        product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Position')
        asset = Asset.objects.create(user=self.user, name='Position asset', code='POS', asset_class='EQUITY', currency='BRL', valuation_mode='UNITS')
        Investment.objects.create(user=self.user, product=product, asset=asset, kind='DEPOSIT', quantity=Decimal('2'), unit_price=Decimal('100'), date=date(2026, 9, 1))
        Investment.objects.create(user=self.user, product=product, asset=asset, kind='WITHDRAWAL', quantity=Decimal('1'), unit_price=Decimal('150'), date=date(2026, 9, 2))
        PriceObservation.objects.create(user=self.user, asset=asset, date=date(2026, 9, 10), unit_price=Decimal('120'), source='Local statement')
        PriceObservation.objects.create(user=self.user, asset=asset, date=date(2026, 10, 10), unit_price=Decimal('900'), source='Future statement')
        row = composition(self.user, {'scope': 'portfolio', 'series': 'total', 'period': '2026-09', 'purpose': 'INVESTMENT'})['rows'][0]
        self.assertEqual(row['cents'], '12000')
        self.assertEqual(len(row['sources']), 1)
        source = row['sources'][0]
        self.assertEqual(source['cents'], row['cents'])
        parsed = urlparse(source['url'])
        self.assertEqual(parsed.path, reverse('investments:operations'))
        self.assertEqual(parse_qs(parsed.query), {'section': ['portfolio'], 'product': [str(product.pk)],
                                                'asset': [str(asset.pk)], 'date_to': ['2026-09-30']})
