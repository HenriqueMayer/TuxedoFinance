from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from categories.models import Category
from payments.models import PaymentMethod
from transactions.models import Transaction

User = get_user_model()


class TransactionListFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('transactions', password='test')
        cls.category = Category.objects.create(
            user=cls.user,
            name='Test category',
        )
        cls.debit = PaymentMethod.objects.create(
            user=cls.user,
            name='Daily account',
            method_type=PaymentMethod.MethodType.DEBIT_CARD,
        )
        cls.card = PaymentMethod.objects.create(
            user=cls.user,
            name='Cycle card',
            method_type=PaymentMethod.MethodType.CREDIT_CARD,
            best_purchase_day=24,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def create_transaction(self, title, amount, transaction_date, **kwargs):
        defaults = {
            'user': self.user,
            'category': self.category,
            'payment_method': self.debit,
            'transaction_type': Transaction.TransactionType.EXPENSE,
        }
        defaults.update(kwargs)
        return Transaction.objects.create(
            title=title,
            amount=Decimal(amount),
            transaction_date=transaction_date,
            **defaults,
        )

    def response_titles(self, response):
        return [
            transaction.title for transaction in response.context['transactions']
        ]

    def test_exact_date_filters_transaction_date_and_isolates_user(self):
        self.create_transaction('Selected', '10.00', date(2026, 8, 10))
        self.create_transaction('Different day', '20.00', date(2026, 8, 11))
        other = User.objects.create_user('other-transactions', password='test')
        other_category = Category.objects.create(user=other, name='Other category')
        other_method = PaymentMethod.objects.create(
            user=other,
            name='Other account',
            method_type=PaymentMethod.MethodType.PIX,
        )
        Transaction.objects.create(
            user=other,
            title='Other user row',
            amount=Decimal('30.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=other_category,
            payment_method=other_method,
            transaction_date=date(2026, 8, 10),
        )

        response = self.client.get(
            reverse('transactions:list'), {'date': '2026-08-10'}
        )

        self.assertEqual(self.response_titles(response), ['Selected'])
        self.assertEqual(response.context['selected_date'], '2026-08-10')

    def test_exact_date_does_not_synthesize_fixed_occurrences(self):
        self.create_transaction(
            'Fixed from January',
            '50.00',
            date(2026, 1, 5),
            is_fixed=True,
        )

        billed_response = self.client.get(
            reverse('transactions:list'), {'month': '2026-08'}
        )
        exact_response = self.client.get(
            reverse('transactions:list'), {'date': '2026-08-05'}
        )

        self.assertEqual(
            self.response_titles(billed_response),
            ['Fixed from January'],
        )
        self.assertEqual(self.response_titles(exact_response), [])

    def test_billed_month_keeps_card_shift_and_combines_with_exact_date(self):
        self.create_transaction(
            'Shifted purchase',
            '120.00',
            date(2026, 7, 25),
            payment_method=self.card,
        )
        self.create_transaction('July debit', '30.00', date(2026, 7, 25))

        response = self.client.get(
            reverse('transactions:list'),
            {'month': '2026-08', 'date': '2026-07-25'},
        )

        self.assertEqual(self.response_titles(response), ['Shifted purchase'])

    def test_search_remains_general_and_combines_with_type(self):
        self.create_transaction(
            'Ordinary title',
            '10.00',
            date(2026, 8, 1),
            notes='Annual insurance renewal',
        )
        self.create_transaction(
            'Salary',
            '100.00',
            date(2026, 8, 1),
            transaction_type=Transaction.TransactionType.INCOME,
        )

        response = self.client.get(
            reverse('transactions:list'),
            {'q': 'insurance', 'type': Transaction.TransactionType.EXPENSE},
        )

        self.assertEqual(self.response_titles(response), ['Ordinary title'])

    def test_highest_and_lowest_sort_by_full_stored_amount(self):
        self.create_transaction('Small', '50.00', date(2026, 8, 1))
        self.create_transaction(
            'Installment total',
            '1000.00',
            date(2026, 8, 1),
            payment_method=self.card,
            installments=10,
        )
        self.create_transaction(
            'Income',
            '200.00',
            date(2026, 8, 1),
            transaction_type=Transaction.TransactionType.INCOME,
        )

        highest = self.client.get(
            reverse('transactions:list'), {'sort': 'highest'}
        )
        lowest = self.client.get(
            reverse('transactions:list'),
            {'sort': 'lowest'},
        )

        self.assertEqual(
            self.response_titles(highest), ['Installment total', 'Income', 'Small']
        )
        self.assertEqual(
            self.response_titles(lowest), ['Small', 'Income', 'Installment total']
        )

    def test_invalid_exact_date_is_ignored_and_not_restored(self):
        self.create_transaction('Still visible', '10.00', date(2026, 8, 1))

        response = self.client.get(
            reverse('transactions:list'), {'date': '2026-02-30'}
        )

        self.assertEqual(self.response_titles(response), ['Still visible'])
        self.assertEqual(response.context['selected_date'], '')

    def test_filter_controls_explain_date_semantics_and_show_clear_link(self):
        response = self.client.get(
            reverse('transactions:list'),
            {'date': '2026-08-10', 'sort': 'updated'},
        )

        self.assertContains(response, 'name="month"')
        self.assertNotContains(response, 'Includes card billing shifts')
        self.assertContains(response, 'name="date"')
        self.assertNotContains(response, 'Matches the exact purchase or start date')
        self.assertContains(response, 'value="2026-08-10"')
        self.assertContains(response, 'Highest amount')
        self.assertContains(response, 'Lowest amount')
        self.assertContains(response, 'Clear filters')

    def test_pagination_preserves_all_filters_and_sort(self):
        for index in range(11):
            self.create_transaction(
                f'Paged {index}',
                f'{index + 1}.00',
                date(2026, 8, 10),
            )

        response = self.client.get(
            reverse('transactions:list'),
            {
                'q': 'Paged',
                'month': '2026-08',
                'date': '2026-08-10',
                'type': Transaction.TransactionType.EXPENSE,
                'sort': 'highest',
            },
        )
        content = response.content.decode()

        self.assertContains(response, 'Page 1 of 2')
        self.assertIn('q=Paged', content)
        self.assertIn('month=2026-08', content)
        self.assertIn('date=2026-08-10', content)
        self.assertIn('type=EXPENSE', content)
        self.assertIn('sort=highest', content)
        self.assertIn('page=2', content)
