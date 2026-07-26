from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils.formats import number_format

from core.currencies import get_currency

from categories.models import Category
from payments.models import PaymentMethod
from transactions.forms import TransactionForm
from transactions.models import Transaction


class TransactionModelTests(TestCase):
    """PRD 9.1 — validations (`amount` stays positive), `__str__`, defaults, timestamps."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='Freelance')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )

    def _build_transaction(self, **overrides):
        defaults = {
            'user': self.user,
            'title': 'Coffee',
            'amount': Decimal('10.00'),
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category,
            'payment_method': self.payment_method,
            'transaction_date': date(2026, 7, 1),
        }
        defaults.update(overrides)
        return Transaction(**defaults)

    def test_str_includes_title_and_type_display(self):
        txn = self._build_transaction(
            title='Salary', transaction_type=Transaction.TransactionType.INCOME,
        )
        txn.save()
        self.assertEqual(str(txn), 'Salary (Income)')

    def test_is_fixed_defaults_to_false(self):
        txn = self._build_transaction()
        txn.save()
        self.assertFalse(txn.is_fixed)

    def test_created_and_updated_at_auto_populated(self):
        txn = self._build_transaction()
        txn.save()
        self.assertIsNotNone(txn.created_at)
        self.assertIsNotNone(txn.updated_at)

    def test_created_at_is_immutable_across_updates(self):
        txn = self._build_transaction()
        txn.save()
        original_created_at = txn.created_at
        original_updated_at = txn.updated_at

        txn.title = 'Coffee and pastry'
        txn.save()
        txn.refresh_from_db()

        self.assertEqual(txn.created_at, original_created_at)
        self.assertGreater(txn.updated_at, original_updated_at)

    def test_amount_must_be_positive_rejects_zero(self):
        txn = self._build_transaction(amount=Decimal('0.00'))
        with self.assertRaises(ValidationError):
            txn.full_clean()

    def test_amount_must_be_positive_rejects_negative(self):
        txn = self._build_transaction(amount=Decimal('-5.00'))
        with self.assertRaises(ValidationError):
            txn.full_clean()

    def test_amount_accepts_smallest_positive_value(self):
        txn = self._build_transaction(amount=Decimal('0.01'))
        txn.full_clean()  # should not raise

    def test_installments_defaults_to_one(self):
        txn = self._build_transaction()
        txn.save()
        self.assertEqual(txn.installments, 1)
        self.assertFalse(txn.is_installment_plan)

    def test_installment_amount_equals_amount_for_a_single_payment(self):
        txn = self._build_transaction(amount=Decimal('99.90'))
        self.assertEqual(txn.installment_amount, Decimal('99.90'))

    def test_installment_amount_splits_the_total(self):
        txn = self._build_transaction(amount=Decimal('300.00'), installments=3)
        self.assertTrue(txn.is_installment_plan)
        self.assertEqual(txn.installment_amount, Decimal('100.00'))

    def test_installment_amount_rounds_to_two_decimal_places(self):
        txn = self._build_transaction(amount=Decimal('100.00'), installments=3)
        self.assertEqual(txn.installment_amount, Decimal('33.33'))

    def test_amount_stays_the_full_total_regardless_of_installments(self):
        txn = self._build_transaction(amount=Decimal('300.00'), installments=3)
        txn.save()
        txn.refresh_from_db()
        self.assertEqual(txn.amount, Decimal('300.00'))

    def test_installments_below_one_is_rejected(self):
        txn = self._build_transaction(installments=0)
        with self.assertRaises(ValidationError):
            txn.full_clean()

    def test_installments_above_the_maximum_is_rejected(self):
        txn = self._build_transaction(installments=Transaction.MAX_INSTALLMENTS + 1)
        with self.assertRaises(ValidationError):
            txn.full_clean()


class TransactionRecurrenceTests(TestCase):
    """PRD §8.5 / FR15 — how a transaction contributes to each month."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='Freelance')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )

    def _build_transaction(self, **overrides):
        defaults = {
            'user': self.user,
            'title': 'Fixture',
            'amount': Decimal('300.00'),
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category,
            'payment_method': self.payment_method,
            'transaction_date': date(2026, 1, 15),
        }
        defaults.update(overrides)
        return Transaction(**defaults)

    def test_months_from_start_counts_whole_months(self):
        txn = self._build_transaction()
        self.assertEqual(txn.months_from_start(2026, 1), 0)
        self.assertEqual(txn.months_from_start(2026, 4), 3)
        self.assertEqual(txn.months_from_start(2027, 1), 12)
        self.assertEqual(txn.months_from_start(2025, 12), -1)

    def test_one_off_lands_only_in_its_own_month(self):
        txn = self._build_transaction()
        self.assertEqual(txn.amount_for_month(2026, 1), Decimal('300.00'))
        self.assertEqual(txn.amount_for_month(2026, 2), Decimal('0.00'))
        self.assertEqual(txn.amount_for_month(2025, 12), Decimal('0.00'))

    def test_fixed_repeats_every_month_from_its_start(self):
        txn = self._build_transaction(is_fixed=True)
        for month in range(1, 13):
            self.assertEqual(txn.amount_for_month(2026, month), Decimal('300.00'))
        self.assertEqual(txn.amount_for_month(2027, 6), Decimal('300.00'))
        self.assertEqual(txn.amount_for_month(2025, 12), Decimal('0.00'))

    def test_installments_spread_one_per_month_then_stop(self):
        txn = self._build_transaction(installments=3)
        self.assertEqual(txn.amount_for_month(2026, 1), Decimal('100.00'))
        self.assertEqual(txn.amount_for_month(2026, 2), Decimal('100.00'))
        self.assertEqual(txn.amount_for_month(2026, 3), Decimal('100.00'))
        self.assertEqual(txn.amount_for_month(2026, 4), Decimal('0.00'))

    def test_installments_cross_the_year_boundary(self):
        txn = self._build_transaction(transaction_date=date(2026, 11, 5), installments=4)
        self.assertEqual(txn.amount_for_month(2026, 12), Decimal('75.00'))
        self.assertEqual(txn.amount_for_month(2027, 1), Decimal('75.00'))
        self.assertEqual(txn.amount_for_month(2027, 2), Decimal('75.00'))
        self.assertEqual(txn.amount_for_month(2027, 3), Decimal('0.00'))

    def test_last_installment_absorbs_the_rounding_remainder(self):
        txn = self._build_transaction(amount=Decimal('100.00'), installments=3)
        self.assertEqual(txn.installment_amount, Decimal('33.33'))
        monthly = [txn.amount_for_month(2026, month) for month in (1, 2, 3)]
        self.assertEqual(monthly, [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')])
        self.assertEqual(sum(monthly), txn.amount)

    def test_amount_through_month_accumulates(self):
        txn = self._build_transaction(installments=3)
        self.assertEqual(txn.amount_through_month(2025, 12), Decimal('0.00'))
        self.assertEqual(txn.amount_through_month(2026, 1), Decimal('100.00'))
        self.assertEqual(txn.amount_through_month(2026, 2), Decimal('200.00'))
        self.assertEqual(txn.amount_through_month(2026, 3), Decimal('300.00'))
        self.assertEqual(txn.amount_through_month(2026, 9), Decimal('300.00'))

    def test_amount_through_month_for_fixed_multiplies_by_occurrences(self):
        txn = self._build_transaction(is_fixed=True)
        self.assertEqual(txn.amount_through_month(2026, 1), Decimal('300.00'))
        self.assertEqual(txn.amount_through_month(2026, 3), Decimal('900.00'))

    def test_amount_through_month_matches_the_sum_of_each_month(self):
        txn = self._build_transaction(amount=Decimal('100.00'), installments=3)
        running = Decimal('0.00')
        for month in range(1, 7):
            running += txn.amount_for_month(2026, month)
            self.assertEqual(txn.amount_through_month(2026, month), running)


    # --- fixed_until: ending a recurrence without losing history (FR18) ---

    def test_fixed_until_stops_the_recurrence_after_that_month(self):
        txn = self._build_transaction(
            transaction_type=Transaction.TransactionType.INCOME,
            amount=Decimal('2000.00'),
            is_fixed=True,
            fixed_until=date(2026, 5, 20),
        )
        for month in range(1, 6):
            self.assertEqual(txn.amount_for_month(2026, month), Decimal('2000.00'))
        for month in range(6, 13):
            self.assertEqual(txn.amount_for_month(2026, month), Decimal('0.00'))

    def test_fixed_until_includes_its_own_month(self):
        txn = self._build_transaction(is_fixed=True, fixed_until=date(2026, 1, 31))
        # Starts and ends in January: exactly one payment, not zero.
        self.assertEqual(txn.amount_for_month(2026, 1), Decimal('300.00'))
        self.assertEqual(txn.amount_for_month(2026, 2), Decimal('0.00'))

    def test_fixed_until_is_compared_by_month_not_by_day(self):
        # The 1st of the month still pays that whole month: recurrence is
        # monthly, so the day component carries no meaning.
        txn = self._build_transaction(is_fixed=True, fixed_until=date(2026, 3, 1))
        self.assertEqual(txn.amount_for_month(2026, 3), Decimal('300.00'))
        self.assertEqual(txn.amount_for_month(2026, 4), Decimal('0.00'))

    def test_fixed_without_an_end_date_still_repeats_indefinitely(self):
        txn = self._build_transaction(is_fixed=True)
        self.assertIsNone(txn.last_fixed_offset)
        self.assertEqual(txn.amount_for_month(2099, 12), Decimal('300.00'))

    def test_fixed_until_crossing_a_year_boundary(self):
        txn = self._build_transaction(
            transaction_date=date(2026, 11, 10),
            is_fixed=True,
            fixed_until=date(2027, 2, 5),
        )
        for year, month in ((2026, 11), (2026, 12), (2027, 1), (2027, 2)):
            self.assertEqual(txn.amount_for_month(year, month), Decimal('300.00'))
        self.assertEqual(txn.amount_for_month(2027, 3), Decimal('0.00'))

    def test_amount_through_month_stops_accumulating_after_the_end_date(self):
        txn = self._build_transaction(is_fixed=True, fixed_until=date(2026, 3, 31))
        # Three payments (Jan, Feb, Mar), then the total stays put forever.
        self.assertEqual(txn.amount_through_month(2026, 3), Decimal('900.00'))
        self.assertEqual(txn.amount_through_month(2026, 12), Decimal('900.00'))
        self.assertEqual(txn.amount_through_month(2030, 1), Decimal('900.00'))

    def test_amount_through_month_still_equals_the_sum_of_each_month(self):
        txn = self._build_transaction(is_fixed=True, fixed_until=date(2026, 4, 30))
        running = Decimal('0.00')
        for month in range(1, 13):
            running += txn.amount_for_month(2026, month)
            self.assertEqual(txn.amount_through_month(2026, month), running)

    def test_an_end_date_before_the_start_pays_once_instead_of_going_negative(self):
        # The form rejects this; a fixture or data migration could still
        # produce it, and one payment beats a negative number of payments.
        txn = self._build_transaction(is_fixed=True, fixed_until=date(2025, 6, 1))
        self.assertEqual(txn.last_fixed_offset, 0)
        self.assertEqual(txn.amount_for_month(2026, 1), Decimal('300.00'))
        self.assertEqual(txn.amount_for_month(2026, 2), Decimal('0.00'))
        self.assertEqual(txn.amount_through_month(2026, 12), Decimal('300.00'))

    def test_a_raise_is_two_rows_and_history_survives(self):
        """The scenario the field exists for: salary 2000, raised to 3000."""
        old_salary = self._build_transaction(
            title='Salary',
            transaction_type=Transaction.TransactionType.INCOME,
            amount=Decimal('2000.00'),
            is_fixed=True,
            fixed_until=date(2026, 5, 31),
        )
        new_salary = self._build_transaction(
            title='Salary',
            transaction_type=Transaction.TransactionType.INCOME,
            amount=Decimal('3000.00'),
            transaction_date=date(2026, 6, 1),
            is_fixed=True,
        )

        monthly = [
            old_salary.amount_for_month(2026, month)
            + new_salary.amount_for_month(2026, month)
            for month in range(1, 13)
        ]
        self.assertEqual(monthly[:5], [Decimal('2000.00')] * 5)
        self.assertEqual(monthly[5:], [Decimal('3000.00')] * 7)
        # No month is ever double-counted at the handover.
        self.assertEqual(monthly[4], Decimal('2000.00'))
        self.assertEqual(monthly[5], Decimal('3000.00'))


class TransactionViewTests(TestCase):
    """PRD 9.2 — auth enforcement, per-user isolation (R3), full CRUD, filtering."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')

        self.category = Category.objects.create(user=self.user, name='Freelance')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.credit_card = PaymentMethod.objects.create(
            user=self.user, name='Nubank Credit', method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        self.other_category = Category.objects.create(user=self.other_user, name='Side Gig')
        self.other_payment_method = PaymentMethod.objects.create(
            user=self.other_user, name='Other Wallet', method_type=PaymentMethod.MethodType.PIX,
        )

        self.transaction = Transaction.objects.create(
            user=self.user,
            title='Coffee',
            amount=Decimal('10.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=date(2026, 7, 1),
        )
        self.other_transaction = Transaction.objects.create(
            user=self.other_user,
            title='Other Coffee',
            amount=Decimal('15.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.other_category,
            payment_method=self.other_payment_method,
            transaction_date=date(2026, 7, 1),
        )

    def _valid_payload(self, **overrides):
        payload = {
            'title': 'New Transaction',
            'amount': '25.50',
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category.pk,
            'payment_method': self.payment_method.pk,
            'transaction_date': '2026-07-10',
            'notes': '',
        }
        payload.update(overrides)
        return payload

    def test_list_requires_login(self):
        response = self.client.get(reverse('transactions:list'))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('transactions:list')}"
        )

    def test_create_requires_login(self):
        response = self.client.get(reverse('transactions:create'))
        self.assertEqual(response.status_code, 302)

    def test_update_requires_login(self):
        response = self.client.get(reverse('transactions:update', args=[self.transaction.pk]))
        self.assertEqual(response.status_code, 302)

    def test_delete_requires_login(self):
        response = self.client.get(reverse('transactions:delete', args=[self.transaction.pk]))
        self.assertEqual(response.status_code, 302)

    def test_list_only_shows_own_transactions(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('transactions:list'))
        transactions = list(response.context['transactions'])
        self.assertIn(self.transaction, transactions)
        self.assertNotIn(self.other_transaction, transactions)

    def test_cannot_open_update_form_for_other_users_transaction(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('transactions:update', args=[self.other_transaction.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_other_users_transaction(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('transactions:delete', args=[self.other_transaction.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Transaction.objects.filter(pk=self.other_transaction.pk).exists())

    def test_create_transaction(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('transactions:create'), self._valid_payload())
        self.assertRedirects(response, reverse('transactions:list'))
        self.assertTrue(
            Transaction.objects.filter(user=self.user, title='New Transaction').exists()
        )

    def test_update_transaction(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('transactions:update', args=[self.transaction.pk]),
            self._valid_payload(title='Coffee Renamed', amount='12.34'),
        )
        self.assertRedirects(response, reverse('transactions:list'))
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.title, 'Coffee Renamed')
        self.assertEqual(self.transaction.amount, Decimal('12.34'))

    def test_delete_shows_confirmation_on_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('transactions:delete', args=[self.transaction.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'transactions/confirm_delete.html')

    def test_delete_removes_transaction_on_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('transactions:delete', args=[self.transaction.pk]))
        self.assertRedirects(response, reverse('transactions:list'))
        self.assertFalse(Transaction.objects.filter(pk=self.transaction.pk).exists())

    def test_create_credit_card_transaction_with_installments(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('transactions:create'),
            self._valid_payload(
                title='Laptop',
                amount='3000.00',
                payment_method=self.credit_card.pk,
                installments=6,
            ),
        )
        self.assertRedirects(response, reverse('transactions:list'))
        txn = Transaction.objects.get(user=self.user, title='Laptop')
        self.assertEqual(txn.installments, 6)
        self.assertEqual(txn.amount, Decimal('3000.00'))
        self.assertEqual(txn.installment_amount, Decimal('500.00'))

    def test_create_rejects_installments_on_a_non_credit_card_method(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('transactions:create'),
            self._valid_payload(title='Laptop', payment_method=self.payment_method.pk, installments=6),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('installments', response.context['form'].errors)
        self.assertFalse(Transaction.objects.filter(user=self.user, title='Laptop').exists())

    def test_list_shows_the_installment_breakdown(self):
        self.client.force_login(self.user)
        Transaction.objects.create(
            user=self.user,
            title='Laptop',
            amount=Decimal('3000.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.category,
            payment_method=self.credit_card,
            installments=6,
            transaction_date=date(2026, 7, 3),
        )
        response = self.client.get(reverse('transactions:list'))
        self.assertContains(response, '6x')
        # Formatted per the configured currency (PRD §8.5, FR20).
        self.assertContains(response, number_format(Decimal('500.00'), 2, force_grouping=True))

    def test_list_filtered_by_month(self):
        self.client.force_login(self.user)
        Transaction.objects.create(
            user=self.user,
            title='August Expense',
            amount=Decimal('5.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=date(2026, 8, 1),
        )
        response = self.client.get(reverse('transactions:list'), {'month': '2026-07'})
        transactions = list(response.context['transactions'])
        self.assertIn(self.transaction, transactions)
        self.assertEqual(len(transactions), 1)

    def test_list_filtered_by_type(self):
        self.client.force_login(self.user)
        income = Transaction.objects.create(
            user=self.user,
            title='Salary',
            amount=Decimal('1000.00'),
            transaction_type=Transaction.TransactionType.INCOME,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=date(2026, 7, 5),
        )
        response = self.client.get(reverse('transactions:list'), {'type': 'INCOME'})
        transactions = list(response.context['transactions'])
        self.assertIn(income, transactions)
        self.assertNotIn(self.transaction, transactions)

    def _search(self, term):
        response = self.client.get(reverse('transactions:list'), {'q': term})
        return list(response.context['transactions'])

    def _create_salary(self, **overrides):
        fields = {
            'user': self.user,
            'title': 'Monthly Salary',
            'amount': Decimal('5000.00'),
            'transaction_type': Transaction.TransactionType.INCOME,
            'category': self.category,
            'payment_method': self.payment_method,
            'transaction_date': date(2026, 7, 5),
        }
        fields.update(overrides)
        return Transaction.objects.create(**fields)

    def test_search_matches_the_title(self):
        salary = self._create_salary()
        self.client.force_login(self.user)
        results = self._search('salary')
        self.assertIn(salary, results)
        self.assertNotIn(self.transaction, results)

    def test_search_is_case_insensitive_and_matches_partial_words(self):
        salary = self._create_salary()
        self.client.force_login(self.user)
        self.assertIn(salary, self._search('SALARY'))
        self.assertIn(salary, self._search('sala'))

    def test_search_matches_notes(self):
        salary = self._create_salary(title='Payslip', notes='April salary from work')
        self.client.force_login(self.user)
        self.assertIn(salary, self._search('salary'))

    def test_search_matches_category_and_payment_method_names(self):
        self.client.force_login(self.user)
        self.assertIn(self.transaction, self._search('Freelance'))
        self.assertIn(self.transaction, self._search('Wallet'))

    def test_search_returns_nothing_when_no_row_matches(self):
        self.client.force_login(self.user)
        self.assertEqual(self._search('nothing matches this'), [])

    def test_blank_search_does_not_filter(self):
        self.client.force_login(self.user)
        self.assertIn(self.transaction, self._search(''))
        # Whitespace is stripped, so a stray space is not a search for " ".
        self.assertIn(self.transaction, self._search('   '))

    def test_search_never_reaches_another_users_transactions(self):
        self.client.force_login(self.user)
        # 'Coffee' matches both users' rows by title; only the owner's may show.
        results = self._search('Coffee')
        self.assertIn(self.transaction, results)
        self.assertNotIn(self.other_transaction, results)

    def test_search_combines_with_the_type_filter(self):
        salary = self._create_salary()
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('transactions:list'), {'q': 'salary', 'type': 'EXPENSE'}
        )
        # AND, not OR: an income row cannot survive a type=EXPENSE filter.
        self.assertNotIn(salary, list(response.context['transactions']))

    def test_search_term_is_kept_in_the_form(self):
        self._create_salary()
        self.client.force_login(self.user)
        response = self.client.get(reverse('transactions:list'), {'q': 'salary'})
        self.assertEqual(response.context['search_query'], 'salary')
        self.assertContains(response, 'value="salary"')

    def test_search_with_no_results_offers_a_way_back(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('transactions:list'), {'q': 'zzz'})
        self.assertContains(response, 'No matching transactions')
        self.assertContains(response, 'Clear filters')


class TransactionFormTests(TestCase):
    """PRD 9.4 — required fields, user-scoped FK querysets, invalid input rejection."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='Freelance')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.credit_card = PaymentMethod.objects.create(
            user=self.user, name='Nubank Credit', method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        self.other_category = Category.objects.create(user=self.other_user, name='Side Gig')
        self.other_payment_method = PaymentMethod.objects.create(
            user=self.other_user, name='Other Wallet', method_type=PaymentMethod.MethodType.PIX,
        )

    def _valid_data(self, **overrides):
        data = {
            'title': 'Coffee',
            'amount': '10.00',
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category.pk,
            'payment_method': self.payment_method.pk,
            'transaction_date': '2026-07-01',
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_required_fields_are_enforced(self):
        form = TransactionForm(data={}, user=self.user)
        self.assertFalse(form.is_valid())
        for field in ('title', 'amount', 'transaction_type', 'category', 'payment_method', 'transaction_date'):
            self.assertIn(field, form.errors)

    def test_category_queryset_is_scoped_to_user(self):
        form = TransactionForm(user=self.user)
        choices = list(form.fields['category'].queryset)
        self.assertIn(self.category, choices)
        self.assertNotIn(self.other_category, choices)

    def test_payment_method_queryset_is_scoped_to_user(self):
        form = TransactionForm(user=self.user)
        choices = list(form.fields['payment_method'].queryset)
        self.assertIn(self.payment_method, choices)
        self.assertNotIn(self.other_payment_method, choices)

    def test_other_users_category_is_rejected_even_if_pk_is_guessed(self):
        form = TransactionForm(
            data=self._valid_data(category=self.other_category.pk), user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)

    def test_amount_zero_is_rejected(self):
        form = TransactionForm(data=self._valid_data(amount='0'), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)

    def test_amount_negative_is_rejected(self):
        form = TransactionForm(data=self._valid_data(amount='-5.00'), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)

    def test_valid_form_is_accepted(self):
        form = TransactionForm(data=self._valid_data(), user=self.user)
        self.assertTrue(form.is_valid())

    def test_installments_are_optional_and_default_to_one(self):
        form = TransactionForm(data=self._valid_data(), user=self.user)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['installments'], 1)

    def test_blank_installments_is_treated_as_a_single_payment(self):
        form = TransactionForm(data=self._valid_data(installments=''), user=self.user)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['installments'], 1)

    def test_credit_card_accepts_multiple_installments(self):
        form = TransactionForm(
            data=self._valid_data(payment_method=self.credit_card.pk, installments=6),
            user=self.user,
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['installments'], 6)

    def test_non_credit_card_rejects_multiple_installments(self):
        form = TransactionForm(
            data=self._valid_data(payment_method=self.payment_method.pk, installments=6),
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('installments', form.errors)

    def test_non_credit_card_accepts_a_single_installment(self):
        form = TransactionForm(
            data=self._valid_data(payment_method=self.payment_method.pk, installments=1),
            user=self.user,
        )
        self.assertTrue(form.is_valid())

    def test_installments_above_the_maximum_are_rejected(self):
        form = TransactionForm(
            data=self._valid_data(
                payment_method=self.credit_card.pk,
                installments=Transaction.MAX_INSTALLMENTS + 1,
            ),
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('installments', form.errors)

    def test_installments_below_one_are_rejected(self):
        form = TransactionForm(
            data=self._valid_data(payment_method=self.credit_card.pk, installments=0),
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('installments', form.errors)

    def test_fixed_and_installments_together_are_rejected(self):
        form = TransactionForm(
            data=self._valid_data(
                payment_method=self.credit_card.pk, installments=6, is_fixed=True,
            ),
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('installments', form.errors)

    def test_fixed_with_a_single_installment_is_accepted(self):
        form = TransactionForm(
            data=self._valid_data(installments=1, is_fixed=True), user=self.user,
        )
        self.assertTrue(form.is_valid())

    # --- fixed_until validation (FR18) ---

    def test_fixed_until_is_optional(self):
        form = TransactionForm(
            data=self._valid_data(is_fixed=True), user=self.user
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['fixed_until'])

    def test_fixed_until_is_accepted_on_a_fixed_transaction(self):
        form = TransactionForm(
            data=self._valid_data(is_fixed=True, fixed_until='2026-12-31'),
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['fixed_until'], date(2026, 12, 31))

    def test_fixed_until_without_is_fixed_is_rejected(self):
        form = TransactionForm(
            data=self._valid_data(fixed_until='2026-12-31'), user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('fixed_until', form.errors)

    def test_fixed_until_before_the_start_month_is_rejected(self):
        form = TransactionForm(
            data=self._valid_data(
                is_fixed=True, transaction_date='2026-07-01', fixed_until='2026-06-30'
            ),
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('fixed_until', form.errors)

    def test_fixed_until_in_the_same_month_as_the_start_is_accepted(self):
        # Same month means exactly one payment — legitimate, not an error.
        form = TransactionForm(
            data=self._valid_data(
                is_fixed=True, transaction_date='2026-07-20', fixed_until='2026-07-01'
            ),
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_fixed_until_survives_alongside_an_installments_error(self):
        # Both rules must report; the installments check must not swallow the
        # fixed_until one by returning early.
        form = TransactionForm(
            data=self._valid_data(
                payment_method=self.payment_method.pk,
                installments=6,
                fixed_until='2026-12-31',
            ),
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('installments', form.errors)
        self.assertIn('fixed_until', form.errors)


class NumberFormatTests(TestCase):
    """PRD §8.5 / FR20 — amounts render in the configured currency format.

    Assertions derive from `settings.CURRENCY` rather than hardcoding `R$
    1.000,00`, so the suite passes under any currency and
    `CURRENCY=USD manage.py test` exercises the switch for real.
    """

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='Freelance')
        self.payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.transaction = Transaction.objects.create(
            user=self.user,
            title='Salary',
            amount=Decimal('12345.67'),
            transaction_type=Transaction.TransactionType.INCOME,
            category=self.category,
            payment_method=self.payment_method,
            transaction_date=date(2026, 7, 1),
        )
        self.client.force_login(self.user)

    def test_amounts_render_in_the_configured_currency_format(self):
        response = self.client.get(reverse('transactions:list'))
        self.assertContains(response, number_format(Decimal('12345.67'), 2, force_grouping=True))
        # The unformatted value must not leak through anywhere.
        self.assertNotContains(response, '>12345.67<')

    def test_grouping_is_applied_above_one_thousand(self):
        currency = get_currency(settings.CURRENCY)
        response = self.client.get(reverse('transactions:list'))
        self.assertContains(response, f'12{currency.thousand_separator}345')

    def test_amounts_below_one_thousand_still_use_the_decimal_separator(self):
        self.transaction.amount = Decimal('99.90')
        self.transaction.save()
        currency = get_currency(settings.CURRENCY)
        response = self.client.get(reverse('transactions:list'))
        self.assertContains(response, f'99{currency.decimal_separator}90')

    def test_the_amount_input_keeps_a_dot_so_the_browser_accepts_it(self):
        """`<input type="number">` only accepts a dot-decimal `value`.

        Localizing the widget would render `value="12345,67"`, which browsers
        silently reject — the field would come up **empty** on every edit.
        Form fields keep `localize=False` precisely to avoid that.
        """
        response = self.client.get(
            reverse('transactions:update', args=[self.transaction.pk])
        )
        self.assertContains(response, 'value="12345.67"')
        self.assertNotContains(response, 'value="12345,67"')

    def test_a_dot_decimal_amount_is_still_accepted_on_submit(self):
        response = self.client.post(
            reverse('transactions:update', args=[self.transaction.pk]),
            {
                'title': 'Salary',
                'amount': '2500.55',
                'transaction_type': Transaction.TransactionType.INCOME,
                'category': self.category.pk,
                'payment_method': self.payment_method.pk,
                'transaction_date': '2026-07-01',
                'notes': '',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.transaction.refresh_from_db()
        # Not 250055 — the dot must not be eaten as a thousands separator.
        self.assertEqual(self.transaction.amount, Decimal('2500.55'))

