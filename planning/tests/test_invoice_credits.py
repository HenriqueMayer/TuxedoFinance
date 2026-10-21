"""Category budgets retain posting cutoffs for statement credit reductions."""
from datetime import date
from decimal import Decimal

from banking.models import CardInvoiceCredit, CreditCard
from planning.models import CategoryBudget
from planning.services import budget_progress
from planning.tests.fixtures import PlanningFixture


class BudgetInvoiceCreditTests(PlanningFixture):
    def test_reference_month_forecast_and_posted_actual_reduce_category_once(self):
        month = date(2026, 10, 1)
        CategoryBudget.objects.create(user=self.user, category=self.category,
            month=month, currency='BRL', amount='200')
        card = CreditCard.objects.create(user=self.user, account=self.account,
            name='Budget card', closing_day=24, due_day=1)
        self.expense(date=date(2026, 10, 5), amount='100', category=self.child,
            payment_channel='CREDIT_CARD', bank_account=None, credit_card=card)
        CardInvoiceCredit.objects.create(user=self.user, card=card, category=self.child,
            title='Budget refund', amount='8.95', date=date(2026, 11, 3), reference_month=month)
        row = budget_progress(self.user, month, as_of=date(2026, 10, 20))[0]
        self.assertEqual((row['actual'], row['forecast']), (Decimal('100'), Decimal('91.05')))
        row = budget_progress(self.user, month, as_of=date(2026, 11, 5))[0]
        self.assertEqual((row['actual'], row['forecast']), (Decimal('91.05'), Decimal('91.05')))
        self.assertEqual(row['remaining'], Decimal('108.95'))
