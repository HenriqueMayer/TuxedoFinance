# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal

from django.urls import reverse

from accounts.models import UserPreference
from banking.models import Bank, BankAccount, BankMovement, ExchangeRate, LoyaltyEntry, LoyaltyProgram
from banking.services import create_reward_redemption
from dashboard.details import composition
from dashboard.tests import DashboardFixture
from investments.models import Asset, Investment, InvestmentProduct
from transactions.models import Transaction


class CompositionSourceTests(DashboardFixture):
    def expenses(self, **scope):
        return composition(self.user, {'scope': 'instruments', 'series': 'expenses', 'period': '2026-09', **scope})

    def test_only_contributing_transactions_are_linked_and_recurring_sources_are_unique(self):
        item = self.transaction(title='Recurring source', amount='12.34', date=date(2026, 8, 31), is_fixed=True)
        income = self.transaction(title='Income source', amount='99', date=date(2026, 9, 1), transaction_type='INCOME')
        self.transaction(title='Outside month', amount='9', date=date(2026, 11, 1))
        other_account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Other account', currency='BRL')
        self.transaction(title='Other instrument', amount='9', date=date(2026, 9, 1), bank_account=other_account)
        preference = UserPreference.for_user(self.user)
        preference.date_format = 'MDY'
        preference.save(update_fields=['date_format'])
        result = self.expenses(periods=['2026-09', '2026-10'], instrument=f'account:{self.account.pk}')
        row = result['rows'][0]
        self.assertEqual(row['cents'], '2468')
        self.assertEqual(len(row['sources']), 1)
        source = row['sources'][0]
        self.assertEqual(source['url'], reverse('transactions:update', args=[item.pk]))
        self.assertEqual(source['cents'], '2468')
        self.assertIn('08/31/2026', source['label'])
        self.assertNotIn(reverse('transactions:update', args=[income.pk]), str(result))
        self.assertEqual(self.expenses(cutoff='2026-09-15', instrument=f'account:{self.account.pk}')['rows'], [])

    def test_source_amounts_reconcile_after_fx_rounding(self):
        account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Dollar account', currency='USD')
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='1.5', effective_date=date(2026, 9, 1))
        for index in range(3):
            self.transaction(title=f'Converted {index}', amount='0.01', date=date(2026, 9, 1), bank_account=account)
        row = self.expenses()['rows'][0]
        self.assertEqual(row['cents'], '4')
        self.assertEqual(sum(int(source['cents']) for source in row['sources']), int(row['cents']))
        self.assertTrue(all(abs(Decimal(source['cents']) - Decimal('1.5')) <= 1 for source in row['sources']))

    def test_iof_source_opens_redemption_without_mutating_or_unlocking_the_expense(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Source rewards')
        LoyaltyEntry.objects.create(user=self.user, program=program, direction='CREDIT', kind='ADJUSTMENT', amount='100', date=date(2026, 9, 1))
        redemption = create_reward_redemption(user=self.user, program=program, points='10', target_account=self.account,
                                              target_amount='5', iof_account=self.account, iof_amount='2', date=date(2026, 9, 3))
        counts = (Transaction.objects.count(), BankMovement.objects.count(), LoyaltyEntry.objects.count())
        source = self.expenses()['rows'][0]['sources'][0]
        self.assertEqual(source['url'], reverse('banking:redemption_update', args=[redemption.pk]))
        self.assertEqual(source['cents'], '200')
        self.assertEqual(self.client.get(reverse('transactions:update', args=[redemption.iof_transaction.pk])).status_code, 404)
        self.assertEqual(counts, (Transaction.objects.count(), BankMovement.objects.count(), LoyaltyEntry.objects.count()))

    def test_bank_costs_link_to_the_owned_points_purchase_in_the_statement_month(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Purchased points')
        entry = LoyaltyEntry.objects.create(user=self.user, program=program, direction='CREDIT', kind='PURCHASE', amount='100',
                                            funding_account=self.account, cash_amount='3.25', date=date(2026, 9, 3))
        result = composition(self.user, {'scope': 'cashflow', 'series': 'expenses', 'period': '2026-09'})
        row = result['rows'][0]
        self.assertEqual((row['label'], row['cents']), ('Bank costs', '325'))
        self.assertEqual(row['sources'][0]['url'], reverse('banking:entry_update', args=[entry.pk]))
        self.assertIn('Purchased points', row['sources'][0]['label'])

    def test_balance_rows_link_to_the_matching_bank_account(self):
        row = composition(self.user, {'scope': 'ledger', 'series': 'balance', 'period': '2026-09'})['rows'][0]
        source = row['sources'][0]
        self.assertEqual(source['url'], reverse('banking:detail', args=[self.bank.pk]) + f'#account-row-{self.account.pk}')
        self.assertEqual(source['cents'], row['cents'])

    def test_large_source_identifiers_resolve_to_the_owned_record_in_both_languages(self):
        bank = Bank.objects.create(pk=12345, user=self.user, name='Large source bank')
        account = BankAccount.objects.create(pk=12345, user=self.user, bank=bank, name='Large source account',
                                            currency='BRL', opening_balance='10', opening_date=date(2020, 1, 1))
        item = self.transaction(pk=12345, bank_account=account, date=date(2026, 9, 1))
        source = self.expenses(instrument=f'account:{account.pk}')['rows'][0]['sources'][0]
        self.assertEqual(source['url'], '/transactions/12345/edit/')
        account_row = next(row for row in composition(self.user, {
            'scope': 'ledger', 'series': 'balance', 'period': '2026-09',
        })['rows'] if row['label'] == 'Large source bank > Large source account')
        self.assertEqual(account_row['sources'][0]['url'], '/banking/12345/#account-row-12345')
        for language in ('en', 'pt-br'):
            with self.subTest(language=language):
                self.client.cookies['django_language'] = language
                self.assertEqual(self.client.get(source['url']).context['form'].instance.pk, item.pk)
                self.assertContains(self.client.get('/banking/12345/'), 'id="account-row-12345"')

    def test_investment_sources_preserve_opening_position_and_exact_kind_date_scope(self):
        product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Source investment', purpose='INVESTMENT')
        asset = Asset.objects.create(user=self.user, name='Source asset', code='SOURCE', asset_class='LIQUIDITY', currency='BRL',
                                    valuation_mode='MONETARY', opening_balance='100', opening_product=product)
        deposit = Investment.objects.create(user=self.user, product=product, asset=asset, kind='DEPOSIT', amount='20', date=date(2026, 9, 3))
        yield_operation = Investment.objects.create(user=self.user, product=product, asset=asset, kind='YIELD', amount='5', date=date(2026, 9, 4))
        Investment.objects.create(user=self.user, product=product, asset=asset, kind='WITHDRAWAL', amount='10', date=date(2026, 10, 1))
        row = composition(self.user, {'scope': 'portfolio', 'series': 'total', 'period': '2026-09',
                                      'opening_date': '2026-09-01', 'purpose': 'INVESTMENT'})['rows'][0]
        self.assertEqual(row['cents'], '12500')
        self.assertEqual({source['url'] for source in row['sources']}, {
            reverse('investments:operations') + f'?section=portfolio&product={product.pk}&asset={asset.pk}&date_to=2026-09-30',
        })
        history = self.client.get(row['sources'][0]['url'])
        self.assertEqual({item.pk for item in history.context['investments']}, {deposit.pk, yield_operation.pk})
        self.assertEqual(history.context['operation_filter']['date_to'].value(), '2026-09-30')
        row = composition(self.user, {'scope': 'portfolio-flow', 'series': 'deposits', 'period': '2026-09'})['rows'][0]
        self.assertEqual(row['sources'][0]['url'], reverse('investments:update', args=[deposit.pk]))
        self.assertEqual(row['sources'][0]['cents'], '2000')
        row = composition(self.user, {'scope': 'portfolio', 'series': 'total', 'period': '2026-10', 'opening_date': '2026-09-01'})['rows'][0]
        self.assertEqual(row['cents'], '11500')
        self.assertEqual(sum(int(source['cents']) for source in row['sources']), 11500)
        self.assertIn('date_to=2026-10-31', row['sources'][0]['url'])
