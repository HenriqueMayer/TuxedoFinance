"""Instruments coverage for dashboard."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from dashboard.charts import build_donut_chart, build_instrument_chart
from banking.models import Bank, BankAccount, CreditCard
from categories.models import Category
from dashboard.services import get_expenses_by_instrument, get_expenses_by_recurrence, get_instrument_activity
from transactions.models import Transaction
from dashboard.tests.fixtures import DashboardFixture


User = get_user_model()


class InstrumentReportTests(DashboardFixture):
    def test_donut_tooltip_has_reserved_space_below_the_ring(self):
        chart = build_donut_chart(
            [
                {
                    'name': 'Installments',
                    'tone': 'installment',
                    'value': 100,
                    'share': 100,
                }
            ]
        )

        self.assertGreaterEqual(chart['tooltip_y'], chart['width'])
        self.assertGreaterEqual(
            chart['height'], chart['tooltip_y'] + chart['tooltip_height']
        )

    def test_instrument_chart_adds_visual_gaps_between_banks(self):
        labels = [
            {'short_label': 'One', 'bank_label': 'Bank A'},
            {'short_label': 'Two', 'bank_label': 'Bank A'},
            {'short_label': 'Three', 'bank_label': 'Bank B'},
        ]
        chart = build_instrument_chart(
            labels,
            [
                {'name': 'Expenses', 'tone': 'expense', 'values': [3, 2, 1]},
                {'name': 'Income', 'tone': 'income', 'values': [0, 0, 0]},
            ],
        )

        same_bank_gap = chart['groups'][1]['center'] - chart['groups'][0]['center']
        next_bank_gap = chart['groups'][2]['center'] - chart['groups'][1]['center']
        self.assertGreater(next_bank_gap, same_bank_gap)
        self.assertEqual(
            [group['label'] for group in chart['bank_groups']],
            ['Bank A', 'Bank B'],
        )

    def test_combined_activity_ranks_accounts_and_cards_by_total_moved(self):
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Combined Card',
            closing_day=31,
            due_day=28,
        )
        self.transaction(amount='20.00')
        self.transaction(
            amount='80.00',
            transaction_type=Transaction.TransactionType.INCOME,
        )
        self.transaction(
            amount='50.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )

        activity = get_instrument_activity(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual(
            [row['key'] for row in activity['instruments']],
            [f'account:{self.account.pk}', f'cc:{card.pk}'],
        )
        account = activity['instruments'][0]
        self.assertEqual(account['short_label'], 'Main Account')
        self.assertEqual(account['bank_label'], 'Bank With Spaces')
        self.assertEqual(account['expense_total'], Decimal('20.00'))
        self.assertEqual(account['income_total'], Decimal('80.00'))
        self.assertEqual(activity['expense_total'], Decimal('70.00'))
        self.assertEqual(activity['income_total'], Decimal('80.00'))

    def test_combined_activity_keeps_instruments_from_the_same_bank_together(self):
        other_bank = Bank.objects.create(user=self.user, name='Other Bank')
        other_account = BankAccount.objects.create(
            user=self.user,
            bank=other_bank,
            name='Other Account',
            currency='BRL',
        )
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Same Bank Card',
            closing_day=31,
            due_day=28,
        )
        self.transaction(amount='100.00')
        self.transaction(
            amount='90.00',
            payment_channel=Transaction.PaymentChannel.PIX,
            bank_account=other_account,
        )
        self.transaction(
            amount='80.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )

        activity = get_instrument_activity(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual(
            [row['bank_label'] for row in activity['instruments']],
            ['Bank With Spaces', 'Bank With Spaces', 'Other Bank'],
        )

    def test_account_card_grouping_uses_stable_ids_and_isolated_users(self):
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Blue Card With Spaces',
            closing_day=31,
            due_day=28,
        )
        self.transaction(amount='20.00')
        self.transaction(
            amount='30.00',
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=card,
        )
        other = User.objects.create_user('other')
        other_bank = Bank.objects.create(user=other, name='Other')
        other_account = BankAccount.objects.create(
            user=other,
            bank=other_bank,
            name='Hidden',
            currency='BRL',
        )
        other_category = Category.objects.create(user=other, name='Private')
        Transaction.objects.create(
            user=other,
            title='Hidden',
            amount='999.00',
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=other_category,
            payment_channel=Transaction.PaymentChannel.PIX,
            bank_account=other_account,
            date=timezone.localdate(),
        )

        breakdown = get_expenses_by_instrument(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual({row['key'] for row in breakdown['instruments']}, {
            f'account:{self.account.pk}', f'cc:{card.pk}'
        })
        self.assertEqual(breakdown['total'], Decimal('50.00'))
        self.assertTrue(all('Bank With Spaces >' in row['label'] for row in breakdown['instruments']))

    def test_instrument_composition_uses_signed_scope_without_click_navigation(self):
        self.transaction(amount='25.00')
        response = self.client.get(reverse('dashboard:reports'))
        self.assertNotContains(response, 'data-scroll-target="instrument-categories-expense"')
        endpoint = response.context['instrument_selection']['points'][0]['details'][0]
        composition = self.client.get(endpoint).json()
        self.assertEqual([{key: row[key] for key in ('label', 'cents')} for row in composition['rows']], [{'label': 'Groceries', 'cents': '2500'}])

    def test_income_composition_is_separate_from_expenses(self):
        self.transaction(amount='125.00', transaction_type=Transaction.TransactionType.INCOME)
        response = self.client.get(reverse('dashboard:reports'))
        endpoint = response.context['instrument_selection']['points'][0]['details'][1]
        self.assertEqual([{key: row[key] for key in ('label', 'cents')} for row in self.client.get(endpoint).json()['rows']], [{'label': 'Groceries', 'cents': '12500'}])

    def test_installment_shares_are_rounded_to_one_decimal(self):
        self.transaction(amount='542.00')
        self.transaction(amount='458.00', is_fixed=True)

        breakdown = get_expenses_by_recurrence(
            self.user, timezone.localdate().year, timezone.localdate().month
        )

        self.assertEqual(sum(row['share'] for row in breakdown['slices']), 100.0)
        self.assertTrue(
            all(row['share'] == round(row['share'], 1) for row in breakdown['slices'])
        )
