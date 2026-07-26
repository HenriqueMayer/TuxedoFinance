from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from categories.forms import CategoryForm
from categories.models import Category
from categories.signals import DEFAULT_CATEGORY_NAMES
from payments.models import PaymentMethod
from transactions.models import Transaction


class CategoryModelTests(TestCase):
    """PRD 9.1 — validations, `__str__`, defaults, timestamps, uniqueness, PROTECT."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')

    def test_default_categories_seeded_on_signup(self):
        names = set(Category.objects.filter(user=self.user).values_list('name', flat=True))
        self.assertEqual(names, set(DEFAULT_CATEGORY_NAMES))

    def test_str_returns_name_for_top_level_category(self):
        category = Category.objects.create(user=self.user, name='Freelance')
        self.assertEqual(str(category), 'Freelance')

    def test_str_includes_parent_for_subcategory(self):
        parent = Category.objects.create(user=self.user, name='Transport Parent')
        child = Category.objects.create(user=self.user, name='Uber', parent_category=parent)
        self.assertEqual(str(child), 'Transport Parent > Uber')

    def test_created_and_updated_at_auto_populated(self):
        category = Category.objects.create(user=self.user, name='Freelance')
        self.assertIsNotNone(category.created_at)
        self.assertIsNotNone(category.updated_at)

    def test_created_at_is_immutable_across_updates(self):
        category = Category.objects.create(user=self.user, name='Freelance')
        original_created_at = category.created_at
        original_updated_at = category.updated_at

        category.name = 'Freelance Work'
        category.save()
        category.refresh_from_db()

        self.assertEqual(category.created_at, original_created_at)
        self.assertGreater(category.updated_at, original_updated_at)

    def test_unique_category_name_per_user_is_enforced(self):
        Category.objects.create(user=self.user, name='Custom Category')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(user=self.user, name='Custom Category')

    def test_same_name_is_allowed_for_different_users(self):
        other_user = User.objects.create_user('bob', password='pass12345')
        # Both users already share seeded default names (e.g. 'Groceries').
        self.assertEqual(Category.objects.filter(name='Groceries').count(), 2)

        Category.objects.create(user=self.user, name='Freelance')
        Category.objects.create(user=other_user, name='Freelance')
        self.assertEqual(Category.objects.filter(name='Freelance').count(), 2)

    def test_delete_protected_when_referenced_by_transaction(self):
        category = Category.objects.create(user=self.user, name='Referenced')
        payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        Transaction.objects.create(
            user=self.user,
            title='Coffee',
            amount=Decimal('10.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=category,
            payment_method=payment_method,
            transaction_date='2026-07-01',
        )
        with self.assertRaises(ProtectedError):
            category.delete()


class CategoryViewTests(TestCase):
    """PRD 9.2 — auth enforcement, per-user isolation (R3), full CRUD round-trip."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')
        self.category = Category.objects.create(user=self.user, name='Freelance')
        self.other_category = Category.objects.create(user=self.other_user, name='Side Gig')

    def test_list_requires_login(self):
        response = self.client.get(reverse('categories:list'))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('categories:list')}"
        )

    def test_create_requires_login(self):
        response = self.client.get(reverse('categories:create'))
        self.assertEqual(response.status_code, 302)

    def test_update_requires_login(self):
        response = self.client.get(reverse('categories:update', args=[self.category.pk]))
        self.assertEqual(response.status_code, 302)

    def test_delete_requires_login(self):
        response = self.client.get(reverse('categories:delete', args=[self.category.pk]))
        self.assertEqual(response.status_code, 302)

    def test_list_only_shows_own_categories(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('categories:list'))
        categories = list(response.context['categories'])
        self.assertIn(self.category, categories)
        self.assertNotIn(self.other_category, categories)

    def test_cannot_open_update_form_for_other_users_category(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('categories:update', args=[self.other_category.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_other_users_category(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('categories:delete', args=[self.other_category.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Category.objects.filter(pk=self.other_category.pk).exists())

    def test_create_category(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('categories:create'), {'name': 'New Category'})
        self.assertRedirects(response, reverse('categories:list'))
        self.assertTrue(Category.objects.filter(user=self.user, name='New Category').exists())

    def test_update_category(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('categories:update', args=[self.category.pk]), {'name': 'Renamed'}
        )
        self.assertRedirects(response, reverse('categories:list'))
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, 'Renamed')

    def test_delete_shows_confirmation_on_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('categories:delete', args=[self.category.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'categories/confirm_delete.html')

    def test_delete_removes_category_on_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('categories:delete', args=[self.category.pk]))
        self.assertRedirects(response, reverse('categories:list'))
        self.assertFalse(Category.objects.filter(pk=self.category.pk).exists())

    def test_delete_category_in_use_shows_friendly_message_instead_of_500(self):
        self.client.force_login(self.user)
        payment_method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        Transaction.objects.create(
            user=self.user,
            title='Lunch',
            amount=Decimal('20.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.category,
            payment_method=payment_method,
            transaction_date='2026-07-01',
        )
        response = self.client.post(
            reverse('categories:delete', args=[self.category.pk]), follow=True
        )
        self.assertRedirects(response, reverse('categories:list'))
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        messages = [str(message) for message in response.context['messages']]
        self.assertTrue(any('cannot be deleted' in message for message in messages))


class CategoryFormTests(TestCase):
    """PRD 9.4 — required fields, user-scoped FK queryset, no self-parenting."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')

    def test_name_is_required(self):
        form = CategoryForm(data={}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_parent_category_queryset_is_scoped_to_user(self):
        own_category = Category.objects.create(user=self.user, name='Own Top Level')
        other_category = Category.objects.create(user=self.other_user, name='Other Top Level')

        form = CategoryForm(user=self.user)
        choices = list(form.fields['parent_category'].queryset)

        self.assertIn(own_category, choices)
        self.assertNotIn(other_category, choices)

    def test_category_cannot_be_set_as_its_own_parent_on_edit(self):
        category = Category.objects.create(user=self.user, name='Self Ref')
        form = CategoryForm(
            data={'name': category.name, 'parent_category': category.pk},
            user=self.user,
            instance=category,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('parent_category', form.errors)

    def test_valid_form_creates_subcategory(self):
        parent = Category.objects.create(user=self.user, name='Parent Cat')
        form = CategoryForm(
            data={'name': 'Child Cat', 'parent_category': parent.pk}, user=self.user
        )
        self.assertTrue(form.is_valid())
