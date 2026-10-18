from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from banking.models import Bank, BankAccount, CreditCard, InvoicePayment
from banking.services import create_transfer
from banking.settlements import save_invoice_payment
from categories.models import Category
from dashboard.wealth import wealth_snapshot
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation
from investments.services import sync_investment_ledger, refresh_fx_snapshot
from planning.models import FinancialGoal, GoalAllocation
from transactions.models import Transaction
from transactions.services import sync_user_ledger


class NetWorthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('worth')
        self.today = date.today()
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash', currency='BRL', opening_balance=Decimal('1000'), opening_date=date(2025, 1, 1))
        self.category = Category.objects.create(user=self.user, name='Expenses', transaction_type='EXPENSE')

    def test_bank_transfer_and_goal_reserve_do_not_change_wealth(self):
        other = BankAccount.objects.create(user=self.user, bank=self.bank, name='Other', currency='BRL')
        create_transfer(user=self.user, source_account=self.account, destination_account=other, source_amount=Decimal('200'), destination_amount=Decimal('200'), date=self.today)
        goal = FinancialGoal.objects.create(user=self.user, name='Reserve', target_amount=500, currency='BRL')
        GoalAllocation.objects.create(user=self.user, goal=goal, bank_account=self.account, amount=300)
        snapshot = wealth_snapshot(self.user, self.today)
        self.assertEqual(snapshot['net_worth'], 1000)
        self.assertTrue(snapshot['complete'])

    def test_full_installment_debt_and_partial_payment_preserve_net_worth(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Manual', closing_day=31, due_day=31, manual_settlement_from=self.today)
        Transaction.objects.create(user=self.user, title='Installments', amount=100, category=self.category, transaction_type='EXPENSE', payment_channel='CREDIT_CARD', credit_card=card, date=self.today, installments=3)
        Transaction.objects.create(user=self.user, title='Future template', amount=50, category=self.category, transaction_type='EXPENSE', payment_channel='CREDIT_CARD', credit_card=card, date=date(self.today.year + 1, 1, 1), is_fixed=True)
        sync_user_ledger(self.user)
        initial = wealth_snapshot(self.user, self.today)
        self.assertEqual(initial['debt_total'], 100)
        self.assertEqual(initial['net_worth'], 900)
        invoice = card.invoices.order_by('reference_month').first()
        save_invoice_payment(InvoicePayment(user=self.user, invoice=invoice, account=self.account, amount=Decimal('20'), date=self.today))
        after = wealth_snapshot(self.user, self.today)
        self.assertEqual(after['bank_total'], 980)
        self.assertEqual(after['debt_total'], 80)
        self.assertEqual(after['net_worth'], 900)

    def test_position_market_value_and_full_disposal_without_negative_cost(self):
        product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='Investment')
        asset = Asset.objects.create(user=self.user, name='Asset', currency='BRL', asset_class='EQUITY', valuation_mode='UNITS')
        purchase = Investment.objects.create(user=self.user, product=product, asset=asset, kind='DEPOSIT', quantity=Decimal(1), unit_price=Decimal(100), source_account=self.account, cash_amount=Decimal(100), date=self.today)
        refresh_fx_snapshot(purchase); sync_investment_ledger(purchase)
        PriceObservation.objects.create(user=self.user, asset=asset, unit_price=150, date=self.today, source='Local observation')
        first = wealth_snapshot(self.user, self.today)
        self.assertEqual(first['net_worth'], 1050)
        sale = Investment.objects.create(user=self.user, product=product, asset=asset, kind='WITHDRAWAL', quantity=Decimal(1), unit_price=Decimal(150), destination_account=self.account, cash_amount=Decimal(150), date=self.today)
        refresh_fx_snapshot(sale); sync_investment_ledger(sale)
        final = wealth_snapshot(self.user, self.today)
        self.assertEqual(final['portfolio']['total'], 0)
        self.assertEqual(final['net_worth'], 1050)

    def test_unknown_baseline_is_preserved_and_disclosed(self):
        self.account.opening_date = None; self.account.save()
        snapshot = wealth_snapshot(self.user, self.today)
        self.assertEqual(snapshot['net_worth'], 1000)
        self.assertFalse(snapshot['complete'])
        self.assertEqual(snapshot['unknown_banks'], [self.account])

    def test_automatic_advance_debit_is_card_credit_until_purchase_occurs(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Advance', closing_day=10, due_day=20)
        Transaction.objects.create(user=self.user, title='Later purchase', amount=100, category=self.category, transaction_type='EXPENSE', payment_channel='CREDIT_CARD', credit_card=card, date=date(2026, 9, 25), billing_override=0)
        sync_user_ledger(self.user, through_date=date(2026, 9, 23))
        before = wealth_snapshot(self.user, date(2026, 9, 23))
        self.assertEqual(before['bank_total'], 900)
        self.assertEqual(before['card_credits'], 100)
        self.assertEqual(before['net_worth'], 1000)
        after = wealth_snapshot(self.user, date(2026, 9, 25))
        self.assertEqual(after['net_worth'], 900)

    def test_zero_currency_and_missing_portfolio_currency_are_explained(self):
        BankAccount.objects.create(user=self.user, bank=self.bank, name='Empty USD', currency='USD')
        self.assertTrue(wealth_snapshot(self.user, self.today)['complete'])
        product = InvestmentProduct.objects.create(user=self.user, bank=self.bank, name='EUR investment')
        Asset.objects.create(user=self.user, name='EUR amount', asset_class='FIXED_INCOME', currency='EUR', valuation_mode='MONETARY', opening_balance=100, opening_product=product, opening_date=date(2025, 1, 1))
        snapshot = wealth_snapshot(self.user, self.today)
        self.assertFalse(snapshot['complete'])
        self.assertIn('EUR', snapshot['missing_currencies'])
