# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Credit-only category usage remains protected and recoverable."""
from datetime import date

from django.core.exceptions import ValidationError
from django.urls import reverse

from banking.models import CardInvoiceCredit
from categories.models import Category
from transactions.tests.fixtures import TransactionFixture


class InvoiceCreditCategoryTests(TransactionFixture):
    def setUp(self):
        CardInvoiceCredit.objects.create(user=self.user, card=self.credit, category=self.category,
                                        title='Refund', amount='5', date=date(2026, 10, 2),
                                        reference_month=date(2026, 10, 1))
        self.client.force_login(self.user)

    def test_income_reclassification_is_rejected(self):
        self.category.transaction_type = 'INCOME'
        with self.assertRaises(ValidationError):
            self.category.full_clean()

    def test_single_deletion_has_explicit_credit_explanation(self):
        response = self.client.post(reverse('categories:delete', args=[self.category.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This category cannot be deleted while it is used by invoice credits.')
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_delete_all_returns_feedback_instead_of_protected_error(self):
        before = list(Category.objects.filter(user=self.user).values())
        response = self.client.post(reverse('categories:delete_all'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Categories cannot be deleted while they are used by invoice credits.')
        self.assertEqual(before, list(Category.objects.filter(user=self.user).values()))
