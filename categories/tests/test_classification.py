"""Classification coverage for categories."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from categories.models import Category


User = get_user_model()


class CategoryClassificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('classification', password='test')
        Category.objects.filter(user=self.user).delete()

    def test_used_category_cannot_be_classified_against_existing_transactions(self):
        from banking.models import Bank, BankAccount
        from transactions.models import Transaction

        category = Category.objects.create(user=self.user, name='Shared')
        bank = Bank.objects.create(user=self.user, name='Bank')
        account = BankAccount.objects.create(user=self.user, bank=bank, name='Account', currency='BRL')
        Transaction.objects.create(
            user=self.user, title='Expense', amount='10.00', transaction_type='EXPENSE',
            category=category, payment_channel='ACCOUNT', bank_account=account, date='2026-01-01',
        )
        category.transaction_type = Category.TransactionType.INCOME

        with self.assertRaises(ValidationError):
            category.full_clean()

    def test_category_form_labels_the_unclassified_option(self):
        from categories.forms import CategoryForm

        form = CategoryForm(user=self.user)

        self.assertIn('Unclassified (income and expense)', str(form['transaction_type']))

    def test_new_category_form_renders_parent_category_search(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('categories:create'))

        self.assertContains(response, 'data-search-id="parent-category-search"')
        self.assertContains(response, 'id="id_parent_category"')
        self.assertContains(response, 'data-search-select')
