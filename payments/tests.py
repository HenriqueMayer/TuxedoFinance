from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from categories.models import Category
from payments.forms import PaymentMethodForm
from payments.models import PaymentMethod
from payments.signals import DEFAULT_PAYMENT_METHODS
from transactions.models import Transaction


class PaymentMethodModelTests(TestCase):
    """PRD 9.1 — validations, `__str__`, defaults, timestamps, uniqueness, PROTECT."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')

    def test_default_payment_methods_seeded_on_signup(self):
        names = set(PaymentMethod.objects.filter(user=self.user).values_list('name', flat=True))
        expected = {name for _, name in DEFAULT_PAYMENT_METHODS}
        self.assertEqual(names, expected)

    def test_str_includes_name_and_method_type_display(self):
        method = PaymentMethod.objects.create(
            user=self.user, name='Nubank Credit', method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        self.assertEqual(str(method), 'Nubank Credit (Credit Card)')

    def test_str_does_not_repeat_the_type_when_the_name_already_is_it(self):
        method = PaymentMethod.objects.get(
            user=self.user, method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        self.assertEqual(method.name, 'Credit Card')
        self.assertEqual(str(method), 'Credit Card')

    def test_str_deduplication_ignores_case_and_surrounding_space(self):
        method = PaymentMethod.objects.create(
            user=self.user, name=' pix ', method_type=PaymentMethod.MethodType.PIX,
        )
        self.assertEqual(str(method), ' pix ')

    def test_created_and_updated_at_auto_populated(self):
        method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        self.assertIsNotNone(method.created_at)
        self.assertIsNotNone(method.updated_at)

    def test_created_at_is_immutable_across_updates(self):
        method = PaymentMethod.objects.create(
            user=self.user, name='Wallet', method_type=PaymentMethod.MethodType.PIX,
        )
        original_created_at = method.created_at
        original_updated_at = method.updated_at

        method.name = 'Wallet PIX'
        method.save()
        method.refresh_from_db()

        self.assertEqual(method.created_at, original_created_at)
        self.assertGreater(method.updated_at, original_updated_at)

    def test_unique_payment_method_name_per_user_is_enforced(self):
        PaymentMethod.objects.create(
            user=self.user, name='Custom Method', method_type=PaymentMethod.MethodType.PIX,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentMethod.objects.create(
                    user=self.user,
                    name='Custom Method',
                    method_type=PaymentMethod.MethodType.DEBIT_CARD,
                )

    def test_same_name_is_allowed_for_different_users(self):
        other_user = User.objects.create_user('bob', password='pass12345')
        # Both users already share seeded default names (e.g. 'PIX').
        self.assertEqual(PaymentMethod.objects.filter(name='PIX').count(), 2)

        PaymentMethod.objects.create(
            user=self.user, name='Emergency Fund', method_type=PaymentMethod.MethodType.CHECKING_ACCOUNT,
        )
        PaymentMethod.objects.create(
            user=other_user, name='Emergency Fund', method_type=PaymentMethod.MethodType.CHECKING_ACCOUNT,
        )
        self.assertEqual(PaymentMethod.objects.filter(name='Emergency Fund').count(), 2)

    def test_delete_protected_when_referenced_by_transaction(self):
        method = PaymentMethod.objects.create(
            user=self.user, name='Referenced Method', method_type=PaymentMethod.MethodType.PIX,
        )
        category = Category.objects.create(user=self.user, name='Referenced Category')
        Transaction.objects.create(
            user=self.user,
            title='Coffee',
            amount=Decimal('10.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=category,
            payment_method=method,
            transaction_date='2026-07-01',
        )
        with self.assertRaises(ProtectedError):
            method.delete()


class PaymentMethodViewTests(TestCase):
    """PRD 9.2 — auth enforcement, per-user isolation (R3), full CRUD round-trip."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass12345')
        self.other_user = User.objects.create_user('bob', password='pass12345')
        self.method = PaymentMethod.objects.create(
            user=self.user, name='Nubank Credit', method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )
        self.other_method = PaymentMethod.objects.create(
            user=self.other_user, name='Other Credit', method_type=PaymentMethod.MethodType.CREDIT_CARD,
        )

    def test_list_requires_login(self):
        response = self.client.get(reverse('payments:list'))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('payments:list')}"
        )

    def test_create_requires_login(self):
        response = self.client.get(reverse('payments:create'))
        self.assertEqual(response.status_code, 302)

    def test_update_requires_login(self):
        response = self.client.get(reverse('payments:update', args=[self.method.pk]))
        self.assertEqual(response.status_code, 302)

    def test_delete_requires_login(self):
        response = self.client.get(reverse('payments:delete', args=[self.method.pk]))
        self.assertEqual(response.status_code, 302)

    def test_list_only_shows_own_payment_methods(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('payments:list'))
        methods = list(response.context['payment_methods'])
        self.assertIn(self.method, methods)
        self.assertNotIn(self.other_method, methods)

    def test_cannot_open_update_form_for_other_users_method(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('payments:update', args=[self.other_method.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_other_users_method(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('payments:delete', args=[self.other_method.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PaymentMethod.objects.filter(pk=self.other_method.pk).exists())

    def test_create_payment_method(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('payments:create'), {
            'name': 'New Method',
            'method_type': PaymentMethod.MethodType.DEBIT_CARD,
        })
        self.assertRedirects(response, reverse('payments:list'))
        self.assertTrue(PaymentMethod.objects.filter(user=self.user, name='New Method').exists())

    def test_update_payment_method(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('payments:update', args=[self.method.pk]),
            {'name': 'Renamed Method', 'method_type': PaymentMethod.MethodType.CREDIT_CARD},
        )
        self.assertRedirects(response, reverse('payments:list'))
        self.method.refresh_from_db()
        self.assertEqual(self.method.name, 'Renamed Method')

    def test_delete_shows_confirmation_on_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('payments:delete', args=[self.method.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/confirm_delete.html')

    def test_delete_removes_payment_method_on_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('payments:delete', args=[self.method.pk]))
        self.assertRedirects(response, reverse('payments:list'))
        self.assertFalse(PaymentMethod.objects.filter(pk=self.method.pk).exists())

    def test_delete_payment_method_in_use_shows_friendly_message_instead_of_500(self):
        self.client.force_login(self.user)
        category = Category.objects.create(user=self.user, name='Referenced Category')
        Transaction.objects.create(
            user=self.user,
            title='Lunch',
            amount=Decimal('20.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=category,
            payment_method=self.method,
            transaction_date='2026-07-01',
        )
        response = self.client.post(
            reverse('payments:delete', args=[self.method.pk]), follow=True
        )
        self.assertRedirects(response, reverse('payments:list'))
        self.assertTrue(PaymentMethod.objects.filter(pk=self.method.pk).exists())
        messages = [str(message) for message in response.context['messages']]
        self.assertTrue(any('cannot be deleted' in message for message in messages))


class PaymentMethodFormTests(TestCase):
    """PRD 9.4 — required fields and invalid input rejection."""

    def test_required_fields_are_enforced(self):
        form = PaymentMethodForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
        self.assertIn('method_type', form.errors)

    def test_invalid_method_type_is_rejected(self):
        form = PaymentMethodForm(data={'name': 'Bad Method', 'method_type': 'CRYPTO'})
        self.assertFalse(form.is_valid())
        self.assertIn('method_type', form.errors)

    def test_valid_form_is_accepted(self):
        form = PaymentMethodForm(data={
            'name': 'Good Method', 'method_type': PaymentMethod.MethodType.PIX,
        })
        self.assertTrue(form.is_valid())
