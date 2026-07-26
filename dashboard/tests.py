import re
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format

from categories.models import Category
from dashboard.charts import PLOT_BOTTOM, PLOT_TOP, build_bar_chart, build_line_chart
from dashboard.services import (
    EVOLUTION_MONTHS,
    EVOLUTION_PAST_MONTHS,
    OUTLOOK_MONTHS,
    TOP_CATEGORIES,
    add_months,
    get_account_evolution,
    get_dashboard_summary,
)
from payments.models import PaymentMethod
from transactions.models import Transaction

TODAY = timezone.localdate()
PRIOR_MONTH_DATE = TODAY.replace(day=1) - timedelta(days=1)


def add_months_date(start, offset):
    """`start` shifted by `offset` whole months, as a first-of-month date."""
    return date(*add_months(start.year, start.month, offset), 1)


class DashboardAggregationTests(TestCase):
    """PRD 9.3 — indicators match §8.5 formulas against known fixtures.

    Current Balance = Sigma Income - Sigma Expenses - Sigma Investments (full history).
    Balance (month)  = month Income - month Expenses - month Investments.
    Investment reduces both balances but is never merged into Expenses.
    """

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='General')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )

    def _create_transaction(self, transaction_type, amount, transaction_date, **extra):
        Transaction.objects.create(
            user=self.user,
            title='Fixture',
            amount=Decimal(amount),
            transaction_type=transaction_type,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=transaction_date,
            **extra,
        )

    def test_zero_transaction_user_gets_all_zeros(self):
        summary = get_dashboard_summary(self.user)
        self.assertEqual(summary['current_balance'], Decimal('0.00'))
        self.assertEqual(summary['income_month'], Decimal('0.00'))
        self.assertEqual(summary['expense_month'], Decimal('0.00'))
        self.assertEqual(summary['investment_month'], Decimal('0.00'))
        self.assertEqual(summary['balance_month'], Decimal('0.00'))

    def test_indicators_match_prd_formulas_across_current_and_prior_month(self):
        types = Transaction.TransactionType

        # Current month fixtures.
        self._create_transaction(types.INCOME, '1000.00', TODAY)
        self._create_transaction(types.EXPENSE, '300.00', TODAY)
        self._create_transaction(types.INVESTMENT, '200.00', TODAY)

        # Prior month fixtures — must count in Current Balance, not in month cards.
        self._create_transaction(types.INCOME, '500.00', PRIOR_MONTH_DATE)
        self._create_transaction(types.EXPENSE, '100.00', PRIOR_MONTH_DATE)
        self._create_transaction(types.INVESTMENT, '50.00', PRIOR_MONTH_DATE)

        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['income_month'], Decimal('1000.00'))
        self.assertEqual(summary['expense_month'], Decimal('300.00'))
        self.assertEqual(summary['investment_month'], Decimal('200.00'))
        # Balance (month) subtracts Investment as an outflow.
        self.assertEqual(summary['balance_month'], Decimal('500.00'))
        # Current Balance aggregates full history, including the prior month.
        self.assertEqual(summary['current_balance'], Decimal('850.00'))

    def test_investment_is_never_merged_into_expenses_indicator(self):
        types = Transaction.TransactionType
        self._create_transaction(types.EXPENSE, '100.00', TODAY)
        self._create_transaction(types.INVESTMENT, '400.00', TODAY)

        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary['expense_month'], Decimal('100.00'))
        self.assertEqual(summary['investment_month'], Decimal('400.00'))
        # Both are subtracted from the balance, but never combined into Expenses.
        self.assertEqual(summary['balance_month'], Decimal('-500.00'))

    def test_other_users_transactions_never_leak_into_aggregates(self):
        other_user = User.objects.create_user('bob', password='pass12345')
        other_category = Category.objects.create(user=other_user, name='Other')
        other_payment_method = PaymentMethod.objects.create(
            user=other_user, name='Other Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        Transaction.objects.create(
            user=other_user,
            title='Not mine',
            amount=Decimal('9999.00'),
            transaction_type=Transaction.TransactionType.INCOME,
            category=other_category,
            payment_method=other_payment_method,
            transaction_date=TODAY,
        )

        self._create_transaction(Transaction.TransactionType.INCOME, '100.00', TODAY)

        summary = get_dashboard_summary(self.user)
        self.assertEqual(summary['income_month'], Decimal('100.00'))
        self.assertEqual(summary['current_balance'], Decimal('100.00'))


class DashboardProjectionTests(TestCase):
    """PRD FR15 — future-month projection from fixed rows and installment plans."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='General')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.credit_card = PaymentMethod.objects.create(
            user=self.user, name='Nubank Credit', method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )

    def _create_transaction(self, transaction_type, amount, transaction_date, **extra):
        return Transaction.objects.create(
            user=self.user,
            title='Fixture',
            amount=Decimal(amount),
            transaction_type=transaction_type,
            category=self.category,
            payment_method=extra.pop('payment_method', self.payment_method),
            transaction_date=transaction_date,
            **extra,
        )

    def test_the_whole_summary_costs_a_single_query(self):
        # NFR10 / `dashboard.services` module docstring: the outlook folds an
        # in-memory list, so the round-trip count must not grow with the
        # transaction count *or* with the recurrence columns each row reads.
        for _ in range(5):
            self._create_transaction(
                Transaction.TransactionType.INCOME,
                '5000.00',
                TODAY,
                is_fixed=True,
                fixed_until=add_months_date(TODAY, 6),
            )
        with self.assertNumQueries(1):
            summary = get_dashboard_summary(self.user)
            self.assertEqual(len(summary['outlook']), OUTLOOK_MONTHS)

    def test_fixed_income_repeats_in_every_future_month(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME, '5000.00', TODAY, is_fixed=True,
        )
        for offset in range(4):
            year, month = add_months(TODAY.year, TODAY.month, offset)
            summary = get_dashboard_summary(self.user, year, month)
            self.assertEqual(summary['income_month'], Decimal('5000.00'))

    def test_fixed_transaction_does_not_apply_before_its_start_month(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME, '5000.00', TODAY, is_fixed=True,
        )
        year, month = add_months(TODAY.year, TODAY.month, -1)
        summary = get_dashboard_summary(self.user, year, month)
        self.assertEqual(summary['income_month'], Decimal('0.00'))

    def test_one_off_transaction_does_not_repeat(self):
        self._create_transaction(Transaction.TransactionType.EXPENSE, '80.00', TODAY)
        year, month = add_months(TODAY.year, TODAY.month, 1)
        summary = get_dashboard_summary(self.user, year, month)
        self.assertEqual(summary['expense_month'], Decimal('0.00'))

    def test_installments_are_spread_one_per_month(self):
        self._create_transaction(
            Transaction.TransactionType.EXPENSE, '300.00', TODAY,
            payment_method=self.credit_card, installments=3,
        )
        for offset in range(3):
            year, month = add_months(TODAY.year, TODAY.month, offset)
            summary = get_dashboard_summary(self.user, year, month)
            self.assertEqual(summary['expense_month'], Decimal('100.00'))

    def test_installment_plan_stops_after_the_last_installment(self):
        self._create_transaction(
            Transaction.TransactionType.EXPENSE, '300.00', TODAY,
            payment_method=self.credit_card, installments=3,
        )
        year, month = add_months(TODAY.year, TODAY.month, 3)
        summary = get_dashboard_summary(self.user, year, month)
        self.assertEqual(summary['expense_month'], Decimal('0.00'))

    def test_installments_sum_back_to_the_full_total(self):
        # 100.00 in 3x does not divide evenly — the last installment absorbs
        # the remainder so the plan still costs exactly 100.00 overall.
        self._create_transaction(
            Transaction.TransactionType.EXPENSE, '100.00', TODAY,
            payment_method=self.credit_card, installments=3,
        )
        monthly = []
        for offset in range(3):
            year, month = add_months(TODAY.year, TODAY.month, offset)
            monthly.append(get_dashboard_summary(self.user, year, month)['expense_month'])

        self.assertEqual(monthly, [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')])
        self.assertEqual(sum(monthly), Decimal('100.00'))

    def test_current_balance_only_counts_realized_months(self):
        # A 3x plan starting this month has only its first installment realized.
        self._create_transaction(
            Transaction.TransactionType.EXPENSE, '300.00', TODAY,
            payment_method=self.credit_card, installments=3,
        )
        summary = get_dashboard_summary(self.user)
        self.assertEqual(summary['current_balance'], Decimal('-100.00'))

    def test_projected_balance_rolls_forward_to_the_selected_month(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME, '1000.00', TODAY, is_fixed=True,
        )
        year, month = add_months(TODAY.year, TODAY.month, 2)
        summary = get_dashboard_summary(self.user, year, month)
        # Three occurrences realized by then: this month + the next two.
        self.assertEqual(summary['projected_balance'], Decimal('3000.00'))
        self.assertEqual(summary['current_balance'], Decimal('1000.00'))

    def test_outlook_covers_the_next_months_with_a_running_balance(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME, '1000.00', TODAY, is_fixed=True,
        )
        summary = get_dashboard_summary(self.user)
        outlook = summary['outlook']

        self.assertEqual(len(outlook), OUTLOOK_MONTHS)
        self.assertTrue(outlook[0]['is_selected_month'])
        self.assertTrue(outlook[0]['is_current_month'])
        for index, row in enumerate(outlook):
            self.assertEqual(row['income'], Decimal('1000.00'))
            self.assertEqual(row['projected_balance'], Decimal('1000.00') * (index + 1))

    def test_outlook_starts_at_the_selected_month(self):
        year, month = add_months(TODAY.year, TODAY.month, 3)
        summary = get_dashboard_summary(self.user, year, month)
        first = summary['outlook'][0]
        self.assertEqual((first['year'], first['month']), (year, month))
        self.assertFalse(first['is_current_month'])

    def test_fixed_and_installments_combine_across_months(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME, '5000.00', TODAY, is_fixed=True,
        )
        self._create_transaction(
            Transaction.TransactionType.EXPENSE, '1200.00', TODAY,
            payment_method=self.credit_card, installments=2,
        )
        this_month = get_dashboard_summary(self.user)
        self.assertEqual(this_month['balance_month'], Decimal('4400.00'))

        year, month = add_months(TODAY.year, TODAY.month, 1)
        next_month = get_dashboard_summary(self.user, year, month)
        self.assertEqual(next_month['balance_month'], Decimal('4400.00'))

        year, month = add_months(TODAY.year, TODAY.month, 2)
        after_plan = get_dashboard_summary(self.user, year, month)
        # The installment plan is over; only the fixed salary remains.
        self.assertEqual(after_plan['balance_month'], Decimal('5000.00'))

    def test_editing_a_fixed_transaction_changes_every_future_month(self):
        salary = self._create_transaction(
            Transaction.TransactionType.INCOME, '5000.00', TODAY, is_fixed=True,
        )
        year, month = add_months(TODAY.year, TODAY.month, 2)
        self.assertEqual(
            get_dashboard_summary(self.user, year, month)['income_month'],
            Decimal('5000.00'),
        )

        salary.amount = Decimal('6000.00')
        salary.save()

        self.assertEqual(
            get_dashboard_summary(self.user, year, month)['income_month'],
            Decimal('6000.00'),
        )


    def test_ending_a_fixed_salary_preserves_past_months(self):
        """FR18 — a raise is two rows, and history keeps the old value.

        Salary of 2000 from month 0, ended at month 4; 3000 from month 5.
        Every month must show exactly one salary, at the right amount.
        """
        end_year, end_month = add_months(TODAY.year, TODAY.month, 4)
        raise_year, raise_month = add_months(TODAY.year, TODAY.month, 5)

        self._create_transaction(
            Transaction.TransactionType.INCOME,
            '2000.00',
            TODAY,
            is_fixed=True,
            fixed_until=date(end_year, end_month, 28),
        )
        self._create_transaction(
            Transaction.TransactionType.INCOME,
            '3000.00',
            date(raise_year, raise_month, 1),
            is_fixed=True,
        )

        for offset in range(5):
            year, month = add_months(TODAY.year, TODAY.month, offset)
            summary = get_dashboard_summary(self.user, year, month)
            self.assertEqual(summary['income_month'], Decimal('2000.00'))

        for offset in range(5, 10):
            year, month = add_months(TODAY.year, TODAY.month, offset)
            summary = get_dashboard_summary(self.user, year, month)
            self.assertEqual(summary['income_month'], Decimal('3000.00'))

    def test_projected_balance_accounts_for_an_ended_fixed_transaction(self):
        end_year, end_month = add_months(TODAY.year, TODAY.month, 2)
        self._create_transaction(
            Transaction.TransactionType.INCOME,
            '1000.00',
            TODAY,
            is_fixed=True,
            fixed_until=date(end_year, end_month, 15),
        )
        # Three payments total, then the balance stops growing.
        year, month = add_months(TODAY.year, TODAY.month, 2)
        self.assertEqual(
            get_dashboard_summary(self.user, year, month)['projected_balance'],
            Decimal('3000.00'),
        )
        year, month = add_months(TODAY.year, TODAY.month, 8)
        self.assertEqual(
            get_dashboard_summary(self.user, year, month)['projected_balance'],
            Decimal('3000.00'),
        )

    def test_an_ended_fixed_transaction_drops_out_of_the_outlook(self):
        end_year, end_month = add_months(TODAY.year, TODAY.month, 1)
        self._create_transaction(
            Transaction.TransactionType.EXPENSE,
            '500.00',
            TODAY,
            is_fixed=True,
            fixed_until=date(end_year, end_month, 10),
        )
        outlook = get_dashboard_summary(self.user)['outlook']
        self.assertEqual(outlook[0]['expenses'], Decimal('500.00'))
        self.assertEqual(outlook[1]['expenses'], Decimal('500.00'))
        for row in outlook[2:]:
            self.assertEqual(row['expenses'], Decimal('0.00'))


class DashboardViewTests(TestCase):
    """PRD 9.2/9.3 — auth enforcement and per-user scoped context on the dashboard view."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='General')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.other_category = Category.objects.create(user=self.other_user, name='Other')
        self.other_payment_method = PaymentMethod.objects.create(
            user=self.other_user, name='Other Wallet', method_type=PaymentMethod.MethodType.PIX,
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('dashboard:index')}"
        )

    def test_dashboard_context_matches_service_summary(self):
        Transaction.objects.create(
            user=self.user,
            title='Salary',
            amount=Decimal('1500.00'),
            transaction_type=Transaction.TransactionType.INCOME,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=TODAY,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard:index'))
        expected = get_dashboard_summary(self.user)
        self.assertEqual(response.context['income_month'], expected['income_month'])
        self.assertEqual(response.context['current_balance'], expected['current_balance'])
        self.assertEqual(response.context['balance_month'], expected['balance_month'])

    def test_defaults_to_the_current_month(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.context['selected_year'], TODAY.year)
        self.assertEqual(response.context['selected_month'], TODAY.month)
        self.assertTrue(response.context['is_current_month'])

    def test_month_param_selects_a_future_month(self):
        year, month = add_months(TODAY.year, TODAY.month, 4)
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('dashboard:index'), {'month': f'{year:04d}-{month:02d}'}
        )
        self.assertEqual(response.context['selected_year'], year)
        self.assertEqual(response.context['selected_month'], month)
        self.assertTrue(response.context['is_future_month'])
        self.assertFalse(response.context['is_current_month'])

    def test_malformed_month_param_falls_back_to_the_current_month(self):
        self.client.force_login(self.user)
        for bad in ('nonsense', '2026-13', '2026-', '-07', ''):
            response = self.client.get(reverse('dashboard:index'), {'month': bad})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['selected_year'], TODAY.year)
            self.assertEqual(response.context['selected_month'], TODAY.month)

    def test_navigation_params_point_at_the_neighbouring_months(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard:index'), {'month': '2026-01'})
        self.assertEqual(response.context['previous_month_param'], '2025-12')
        self.assertEqual(response.context['next_month_param'], '2026-02')

    def test_outlook_is_rendered_for_a_fixed_transaction(self):
        Transaction.objects.create(
            user=self.user,
            title='Salary',
            amount=Decimal('4200.00'),
            transaction_type=Transaction.TransactionType.INCOME,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=TODAY,
            is_fixed=True,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(len(response.context['outlook']), OUTLOOK_MONTHS)
        self.assertContains(response, 'Outlook')
        # Formatted per the configured currency (PRD §8.5, FR20).
        self.assertContains(response, number_format(Decimal('4200.00'), 2, force_grouping=True))
        # The fixed salary must recur: 6 outlook months of 4200 each.
        self.assertContains(response, number_format(Decimal('25200.00'), 2, force_grouping=True))

    def test_recent_transactions_only_include_own_user(self):
        own_transaction = Transaction.objects.create(
            user=self.user,
            title='Mine',
            amount=Decimal('10.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=TODAY,
        )
        other_transaction = Transaction.objects.create(
            user=self.other_user,
            title='Not mine',
            amount=Decimal('10.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.other_category,
            payment_method=self.other_payment_method,
            transaction_date=TODAY,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard:index'))
        recent = list(response.context['recent_transactions'])
        self.assertIn(own_transaction, recent)
        self.assertNotIn(other_transaction, recent)


class AccountEvolutionTests(TestCase):
    """PRD FR16 — the 12-month series the report charts are drawn from."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='General')
        self.rent_category = Category.objects.create(user=self.user, name='Rent')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.other_category = Category.objects.create(user=self.other_user, name='Theirs')
        self.other_payment_method = PaymentMethod.objects.create(
            user=self.other_user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )

    def _create_transaction(self, transaction_type, amount, transaction_date, **extra):
        return Transaction.objects.create(
            user=extra.pop('user', self.user),
            title=extra.pop('title', 'Fixture'),
            amount=Decimal(amount),
            transaction_type=transaction_type,
            category=extra.pop('category', self.category),
            payment_method=extra.pop('payment_method', self.payment_method),
            transaction_date=transaction_date,
            **extra,
        )

    def test_window_spans_a_full_year_around_today(self):
        evolution = get_account_evolution(self.user)
        months = evolution['months']
        self.assertEqual(len(months), EVOLUTION_MONTHS)

        expected_start = add_months(TODAY.year, TODAY.month, -EVOLUTION_PAST_MONTHS)
        self.assertEqual((months[0]['year'], months[0]['month']), expected_start)
        self.assertEqual(
            (months[-1]['year'], months[-1]['month']),
            add_months(*expected_start, EVOLUTION_MONTHS - 1),
        )

    def test_exactly_one_month_is_flagged_as_current(self):
        evolution = get_account_evolution(self.user)
        current = [row for row in evolution['months'] if row['is_current_month']]
        self.assertEqual(len(current), 1)
        self.assertEqual((current[0]['year'], current[0]['month']), (TODAY.year, TODAY.month))
        self.assertIs(evolution['current_month'], current[0])

    def test_only_months_after_the_current_one_are_flagged_future(self):
        evolution = get_account_evolution(self.user)
        months = evolution['months']
        self.assertEqual(
            [row['is_future'] for row in months],
            [False] * (EVOLUTION_PAST_MONTHS + 1)
            + [True] * (EVOLUTION_MONTHS - EVOLUTION_PAST_MONTHS - 1),
        )

    def test_empty_account_is_all_zeros(self):
        evolution = get_account_evolution(self.user)
        self.assertEqual(evolution['opening_balance'], Decimal('0.00'))
        self.assertEqual(evolution['closing_balance'], Decimal('0.00'))
        self.assertEqual(evolution['net_change'], Decimal('0.00'))
        self.assertEqual(evolution['expenses_by_category'], [])
        for row in evolution['months']:
            self.assertEqual(row['closing_balance'], Decimal('0.00'))

    def test_closing_balance_accumulates_a_fixed_income(self):
        start_year, start_month = add_months(TODAY.year, TODAY.month, -EVOLUTION_PAST_MONTHS)
        self._create_transaction(
            Transaction.TransactionType.INCOME,
            '1000.00',
            date(start_year, start_month, 1),
            is_fixed=True,
        )
        months = get_account_evolution(self.user)['months']
        self.assertEqual(
            [row['closing_balance'] for row in months],
            [Decimal('1000.00') * (index + 1) for index in range(EVOLUTION_MONTHS)],
        )

    def test_opening_balance_carries_history_from_before_the_window(self):
        before_year, before_month = add_months(
            TODAY.year, TODAY.month, -(EVOLUTION_PAST_MONTHS + 2)
        )
        self._create_transaction(
            Transaction.TransactionType.INCOME, '750.00', date(before_year, before_month, 1),
        )
        evolution = get_account_evolution(self.user)
        # The income predates the window, so it shows up as the opening
        # balance rather than as movement inside any rendered month.
        self.assertEqual(evolution['opening_balance'], Decimal('750.00'))
        self.assertEqual(evolution['net_change'], Decimal('0.00'))
        self.assertEqual(evolution['months'][0]['closing_balance'], Decimal('750.00'))

    def test_net_change_is_the_movement_across_the_window(self):
        self._create_transaction(Transaction.TransactionType.INCOME, '400.00', TODAY)
        self._create_transaction(Transaction.TransactionType.EXPENSE, '150.00', TODAY)
        evolution = get_account_evolution(self.user)
        self.assertEqual(evolution['net_change'], Decimal('250.00'))
        self.assertEqual(
            evolution['closing_balance'] - evolution['opening_balance'],
            evolution['net_change'],
        )

    def test_best_and_worst_months_are_picked_by_net_balance(self):
        self._create_transaction(Transaction.TransactionType.INCOME, '900.00', TODAY)
        next_year, next_month = add_months(TODAY.year, TODAY.month, 1)
        self._create_transaction(
            Transaction.TransactionType.EXPENSE, '600.00', date(next_year, next_month, 1),
        )
        evolution = get_account_evolution(self.user)
        self.assertEqual(evolution['best_month']['balance'], Decimal('900.00'))
        self.assertEqual(evolution['worst_month']['balance'], Decimal('-600.00'))

    def test_future_months_project_installments_and_fixed_rows(self):
        credit_card = PaymentMethod.objects.create(
            user=self.user,
            name='Nubank Credit',
            method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        self._create_transaction(
            Transaction.TransactionType.EXPENSE,
            '300.00',
            TODAY,
            installments=3,
            payment_method=credit_card,
        )
        months = {
            (row['year'], row['month']): row for row in get_account_evolution(self.user)['months']
        }
        for offset in range(3):
            year, month = add_months(TODAY.year, TODAY.month, offset)
            self.assertEqual(months[(year, month)]['expenses'], Decimal('100.00'))

        year, month = add_months(TODAY.year, TODAY.month, 3)
        self.assertEqual(months[(year, month)]['expenses'], Decimal('0.00'))

    def test_expenses_by_category_ranks_and_shares(self):
        self._create_transaction(Transaction.TransactionType.EXPENSE, '100.00', TODAY)
        self._create_transaction(
            Transaction.TransactionType.EXPENSE, '300.00', TODAY, category=self.rent_category,
        )
        breakdown = get_account_evolution(self.user)['expenses_by_category']
        self.assertEqual([row['name'] for row in breakdown], ['Rent', 'General'])
        self.assertEqual(breakdown[0]['total'], Decimal('300.00'))
        # Bar width is relative to the largest bar, the share is of all spending.
        self.assertEqual(breakdown[0]['bar_width'], 100.0)
        self.assertEqual(breakdown[1]['bar_width'], round(100 / 3, 2))
        self.assertEqual(breakdown[0]['share'], 75.0)
        self.assertEqual(breakdown[1]['share'], 25.0)

    def test_expenses_by_category_counts_every_month_of_a_recurrence(self):
        start_year, start_month = add_months(TODAY.year, TODAY.month, -EVOLUTION_PAST_MONTHS)
        self._create_transaction(
            Transaction.TransactionType.EXPENSE,
            '50.00',
            date(start_year, start_month, 1),
            category=self.rent_category,
            is_fixed=True,
        )
        breakdown = get_account_evolution(self.user)['expenses_by_category']
        self.assertEqual(breakdown[0]['name'], 'Rent')
        self.assertEqual(breakdown[0]['total'], Decimal('50.00') * EVOLUTION_MONTHS)

    def test_expenses_by_category_is_capped(self):
        for index in range(TOP_CATEGORIES + 3):
            category = Category.objects.create(user=self.user, name=f'Cat {index}')
            self._create_transaction(
                Transaction.TransactionType.EXPENSE, f'{index + 1}.00', TODAY, category=category,
            )
        breakdown = get_account_evolution(self.user)['expenses_by_category']
        self.assertEqual(len(breakdown), TOP_CATEGORIES)

    def test_expenses_by_category_excludes_income_and_investment(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME, '5000.00', TODAY, category=self.rent_category,
        )
        self._create_transaction(
            Transaction.TransactionType.INVESTMENT, '900.00', TODAY, category=self.rent_category,
        )
        self._create_transaction(Transaction.TransactionType.EXPENSE, '10.00', TODAY)
        breakdown = get_account_evolution(self.user)['expenses_by_category']
        self.assertEqual([row['name'] for row in breakdown], ['General'])
        self.assertEqual(breakdown[0]['total'], Decimal('10.00'))

    def test_the_whole_evolution_costs_a_single_query(self):
        for index in range(5):
            self._create_transaction(
                Transaction.TransactionType.EXPENSE,
                f'{index + 1}0.00',
                TODAY,
                category=Category.objects.create(user=self.user, name=f'Cat {index}'),
                # Fixed rows are the ones that read `fixed_until`. Any column
                # the projection touches but `_projection_queryset` forgets to
                # list is deferred, and loads lazily one query per row — so
                # the fixture has to include them or this test passes while
                # the real dashboard N+1s (NFR10).
                is_fixed=True,
                fixed_until=add_months_date(TODAY, 3),
            )
        # NFR10: the category join is part of that one query — reading
        # `category.name` per row in the breakdown must not lazy-load.
        with self.assertNumQueries(1):
            evolution = get_account_evolution(self.user)
            self.assertEqual(len(evolution['expenses_by_category']), 5)
            self.assertEqual(len(evolution['months']), EVOLUTION_MONTHS)

    def test_other_users_transactions_never_leak_into_the_evolution(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME,
            '9999.00',
            TODAY,
            user=self.other_user,
            category=self.other_category,
            payment_method=self.other_payment_method,
        )
        evolution = get_account_evolution(self.user)
        self.assertEqual(evolution['closing_balance'], Decimal('0.00'))
        self.assertEqual(evolution['expenses_by_category'], [])


class ChartGeometryTests(TestCase):
    """PRD FR16 — the server-side SVG maths behind the report charts."""

    def _labels(self, count):
        return [f'M{index}' for index in range(count)]

    def test_line_chart_produces_one_point_per_value(self):
        chart = build_line_chart(self._labels(3), [0.0, 50.0, 100.0])
        self.assertEqual(len(chart['points']), 3)
        self.assertEqual([point['label'] for point in chart['points']], ['M0', 'M1', 'M2'])

    def test_line_chart_x_positions_increase_left_to_right(self):
        chart = build_line_chart(self._labels(4), [1.0, 2.0, 3.0, 4.0])
        xs = [point['x'] for point in chart['points']]
        self.assertEqual(xs, sorted(xs))

    def test_higher_values_sit_higher_on_the_canvas(self):
        # SVG y grows downward, so a bigger value must have a *smaller* y.
        chart = build_line_chart(self._labels(2), [10.0, 90.0])
        self.assertLess(chart['points'][1]['y'], chart['points'][0]['y'])

    def test_every_point_stays_inside_the_plot_area(self):
        chart = build_line_chart(self._labels(3), [-500.0, 0.0, 1200.0])
        for point in chart['points']:
            self.assertGreaterEqual(point['y'], PLOT_TOP)
            self.assertLessEqual(point['y'], PLOT_BOTTOM)

    def test_axis_always_includes_zero(self):
        # An all-positive series must still show the zero line, so the slope
        # is read against zero rather than against the smallest value.
        chart = build_line_chart(self._labels(3), [400.0, 450.0, 500.0])
        self.assertGreaterEqual(chart['zero_y'], PLOT_TOP)
        self.assertLessEqual(chart['zero_y'], PLOT_BOTTOM)

    def test_flat_zero_series_does_not_divide_by_zero(self):
        chart = build_line_chart(self._labels(3), [0.0, 0.0, 0.0])
        ys = {point['y'] for point in chart['points']}
        self.assertEqual(len(ys), 1)
        self.assertEqual(ys.pop(), chart['zero_y'])

    def test_area_polygon_is_closed_along_the_baseline(self):
        chart = build_line_chart(self._labels(2), [10.0, 20.0])
        coordinates = chart['area'].split()
        self.assertTrue(coordinates[0].endswith(f',{PLOT_BOTTOM}'))
        self.assertTrue(coordinates[-1].endswith(f',{PLOT_BOTTOM}'))
        # The line itself sits untouched between the two baseline anchors.
        self.assertEqual(' '.join(coordinates[1:-1]), chart['line'])

    def test_bar_chart_builds_one_bar_per_series_per_label(self):
        chart = build_bar_chart(
            self._labels(2),
            [
                {'name': 'Income', 'tone': 'income', 'values': [10.0, 20.0]},
                {'name': 'Expenses', 'tone': 'expense', 'values': [5.0, 8.0]},
            ],
        )
        self.assertEqual(len(chart['groups']), 2)
        for group in chart['groups']:
            self.assertEqual([bar['tone'] for bar in group['bars']], ['income', 'expense'])

    def test_bars_grow_upward_from_the_baseline(self):
        chart = build_bar_chart(
            self._labels(1), [{'name': 'Income', 'tone': 'income', 'values': [100.0]}]
        )
        bar = chart['groups'][0]['bars'][0]
        self.assertAlmostEqual(bar['y'] + bar['height'], PLOT_BOTTOM, places=1)
        self.assertGreater(bar['height'], 0)

    def test_bars_within_a_group_do_not_overlap(self):
        chart = build_bar_chart(
            self._labels(3),
            [
                {'name': 'Income', 'tone': 'income', 'values': [10.0, 10.0, 10.0]},
                {'name': 'Expenses', 'tone': 'expense', 'values': [5.0, 5.0, 5.0]},
                {'name': 'Investments', 'tone': 'investment', 'values': [1.0, 1.0, 1.0]},
            ],
        )
        for group in chart['groups']:
            for left, right in zip(group['bars'], group['bars'][1:]):
                self.assertLessEqual(left['x'] + left['width'], right['x'])

    def test_zero_valued_bar_has_no_height(self):
        chart = build_bar_chart(
            self._labels(2),
            [{'name': 'Income', 'tone': 'income', 'values': [0.0, 100.0]}],
        )
        self.assertEqual(chart['groups'][0]['bars'][0]['height'], 0.0)

    def test_all_zero_bar_chart_does_not_divide_by_zero(self):
        chart = build_bar_chart(
            self._labels(2), [{'name': 'Income', 'tone': 'income', 'values': [0.0, 0.0]}]
        )
        for group in chart['groups']:
            self.assertEqual(group['bars'][0]['height'], 0.0)


class DashboardReportsViewTests(TestCase):
    """PRD FR16 — the reports screen itself."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='Market Runs')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.other_category = Category.objects.create(user=self.other_user, name='Theirs')
        self.other_payment_method = PaymentMethod.objects.create(
            user=self.other_user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.url = reverse('dashboard:reports')

    def _create_transaction(self, transaction_type, amount, transaction_date, **extra):
        return Transaction.objects.create(
            user=extra.pop('user', self.user),
            title=extra.pop('title', 'Fixture'),
            amount=Decimal(amount),
            transaction_type=transaction_type,
            category=extra.pop('category', self.category),
            payment_method=extra.pop('payment_method', self.payment_method),
            transaction_date=transaction_date,
            **extra,
        )

    def test_reports_requires_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={self.url}')

    def test_reports_renders_both_charts(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Balance evolution')
        self.assertContains(response, 'Monthly cash flow')
        # Chart 1 is an SVG polyline, chart 2 is SVG rects — rendered
        # server-side, with no <script> anywhere on the page (zero-JS).
        self.assertContains(response, '<polyline')
        self.assertContains(response, '<rect')
        self.assertNotContains(response, '<script')

    def test_context_matches_the_service_for_the_logged_in_user(self):
        self._create_transaction(Transaction.TransactionType.INCOME, '1000.00', TODAY)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(
            response.context['evolution']['closing_balance'],
            get_account_evolution(self.user)['closing_balance'],
        )
        self.assertEqual(len(response.context['balance_chart']['points']), EVOLUTION_MONTHS)
        self.assertEqual(len(response.context['cashflow_chart']['groups']), EVOLUTION_MONTHS)

    def test_cashflow_chart_has_the_three_transaction_types(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(
            [entry['name'] for entry in response.context['cashflow_chart']['legend']],
            ['Income', 'Expenses', 'Investments'],
        )

    def test_a_fixed_salary_shows_up_in_every_projected_month(self):
        self._create_transaction(
            Transaction.TransactionType.INCOME, '3000.00', TODAY, is_fixed=True,
        )
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        months = response.context['evolution']['months']
        future = [row for row in months if row['is_future']]
        self.assertTrue(future)
        for row in future:
            self.assertEqual(row['income'], Decimal('3000.00'))

    def test_category_breakdown_is_rendered(self):
        self._create_transaction(Transaction.TransactionType.EXPENSE, '250.00', TODAY)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, 'Market Runs')
        self.assertContains(response, number_format(Decimal('250.00'), 2, force_grouping=True))

    def test_empty_account_renders_without_charts_breaking(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No expenses recorded yet')
        self.assertNotContains(response, 'NaN')

    def test_another_users_data_never_appears(self):
        self._create_transaction(
            Transaction.TransactionType.EXPENSE,
            '9999.00',
            TODAY,
            user=self.other_user,
            title='Not mine',
            category=self.other_category,
            payment_method=self.other_payment_method,
        )
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Theirs')
        self.assertNotContains(response, '9999.00')

    def test_chart_coordinates_are_never_localized(self):
        """Coordinates are markup, not money (PRD §8.5 formatting).

        Money renders as `1.234,56`, but an SVG attribute of `x="90,83"` is
        invalid and would break the whole chart. The template wraps the SVG
        in `{% localize off %}` for exactly this reason.
        """
        self._create_transaction(Transaction.TransactionType.INCOME, '12345.67', TODAY)
        self.client.force_login(self.user)
        body = self.client.get(self.url).content.decode()

        broken = re.findall(
            r'(?:cx|cy|x1|y1|x2|y2)="-?\d+,\d+"', body
        )
        self.assertEqual(broken, [], f'localized SVG coordinates: {broken[:5]}')

        # The polyline/polygon point lists must stay dot-decimal too.
        for points in re.findall(r'points="([^"]+)"', body):
            self.assertNotIn(',,', points)
            for pair in points.split():
                x, _, y = pair.partition(',')
                float(x)
                float(y)

    def test_category_bar_width_is_valid_css(self):
        self._create_transaction(Transaction.TransactionType.EXPENSE, '1234.56', TODAY)
        self.client.force_login(self.user)
        body = self.client.get(self.url).content.decode()
        for width in re.findall(r'style="width: ([^%]+)%"', body):
            float(width)  # `33,33` would raise — and silently break the bar

    def test_money_on_the_reports_page_uses_the_configured_currency_format(self):
        self._create_transaction(Transaction.TransactionType.EXPENSE, '1234.56', TODAY)
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(
            response, number_format(Decimal('1234.56'), 2, force_grouping=True)
        )

