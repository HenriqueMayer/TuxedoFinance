"""Delete all coverage for categories."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from categories.models import Category


User = get_user_model()


class CategoryDeleteAllTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('delete-categories', password='test')
        self.other_user = User.objects.create_user('keep-categories', password='test')
        Category.objects.filter(user__in=(self.user, self.other_user)).delete()
        self.first = Category.objects.create(user=self.user, name='First')
        self.second = Category.objects.create(user=self.user, name='Second')
        self.other_category = Category.objects.create(user=self.other_user, name='Private')
        self.client.force_login(self.user)

    def test_confirmation_page_does_not_delete_categories(self):
        response = self.client.get(reverse('categories:delete_all'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delete all categories')
        self.assertContains(response, 'all 2 categories')
        self.assertEqual(Category.objects.filter(user=self.user).count(), 2)

    def test_confirmation_deletes_only_the_current_users_categories(self):
        response = self.client.post(reverse('categories:delete_all'))

        self.assertRedirects(response, reverse('categories:list'))
        self.assertFalse(Category.objects.filter(user=self.user).exists())
        self.assertTrue(Category.objects.filter(pk=self.other_category.pk).exists())

    def test_used_category_blocks_the_entire_deletion(self):
        from banking.models import Bank, BankAccount
        from transactions.models import Transaction

        bank = Bank.objects.create(user=self.user, name='Bank')
        account = BankAccount.objects.create(
            user=self.user, bank=bank, name='Account', currency='BRL'
        )
        Transaction.objects.create(
            user=self.user, title='Used category', amount='10.00',
            transaction_type='EXPENSE', category=self.first,
            payment_channel='ACCOUNT', bank_account=account, date='2026-01-01',
        )

        response = self.client.post(reverse('categories:delete_all'), follow=True)

        self.assertContains(
            response,
            'Categories cannot be deleted while they are used by existing transactions or budgets.',
        )
        self.assertEqual(Category.objects.filter(user=self.user).count(), 2)

    def test_budget_blocks_category_deletion_without_transactions(self):
        from datetime import date
        from planning.models import CategoryBudget
        CategoryBudget.objects.create(user=self.user, category=self.first, month=date(2026, 10, 1), currency='BRL', amount=100)
        response = self.client.post(reverse('categories:delete_all'), follow=True)
        self.assertContains(response, 'existing transactions or budgets')
        self.assertEqual(Category.objects.filter(user=self.user).count(), 2)
        self.assertTrue(CategoryBudget.objects.filter(user=self.user).exists())
