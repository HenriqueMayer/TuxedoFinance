from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, CreditCard, BankMovement
from categories.models import Category
from transactions.models import Transaction, TransactionSplit
from transactions.services import sync_user_ledger


class CategorySplitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('split')
        bank = Bank.objects.create(user=self.user, name='Bank')
        account = BankAccount.objects.create(user=self.user, bank=bank, name='Cash', currency='BRL')
        card = CreditCard.objects.create(user=self.user, account=account, name='Card', closing_day=31, due_day=30)
        self.a = Category.objects.create(user=self.user, name='A', transaction_type='EXPENSE')
        self.b = Category.objects.create(user=self.user, name='B', transaction_type='EXPENSE')
        self.item = Transaction.objects.create(user=self.user, title='Split', amount=Decimal('100.01'), transaction_type='EXPENSE', category=self.a, payment_channel='CREDIT_CARD', credit_card=card, installments=3, date=date(2026, 1, 1))

    def test_installment_cents_match_each_category_and_single_invoice(self):
        TransactionSplit.objects.create(transaction=self.item, category=self.a, amount=Decimal('25.00'))
        TransactionSplit.objects.create(transaction=self.item, category=self.b, amount=Decimal('75.01'))
        totals = {self.a.pk: Decimal('0'), self.b.pk: Decimal('0')}
        for month in (1, 2, 3):
            rows = self.item.category_allocations_for_month(2026, month)
            self.assertEqual(sum((amount for _, amount in rows), Decimal(0)), self.item.amount_for_month(2026, month))
            for category, amount in rows:
                totals[category.pk] += amount
        self.assertEqual(totals, {self.a.pk: Decimal('25.00'), self.b.pk: Decimal('75.01')})
        sync_user_ledger(self.user)
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 3)

    def test_tiny_categories_never_become_negative_across_many_installments(self):
        self.item.amount = Decimal('0.50'); self.item.installments = 48; self.item.save()
        third = Category.objects.create(user=self.user, name='Tiny', transaction_type='EXPENSE')
        for category, amount in [(self.a, '0.20'), (self.b, '0.20'), (third, '0.10')]:
            TransactionSplit.objects.create(transaction=self.item, category=category, amount=Decimal(amount))
        totals = {self.a.pk: Decimal(0), self.b.pk: Decimal(0), third.pk: Decimal(0)}
        for offset in range(48):
            year, month = divmod(2026 * 12 + offset, 12)
            rows = self.item.category_allocations_for_month(year, month + 1)
            self.assertEqual(sum((amount for _, amount in rows), Decimal(0)), self.item.amount_for_month(year, month + 1))
            for category, amount in rows:
                self.assertGreaterEqual(amount, 0)
                totals[category.pk] += amount
        self.assertEqual(totals, {self.a.pk: Decimal('0.20'), self.b.pk: Decimal('0.20'), third.pk: Decimal('0.10')})

    def post_rows(self, **extra):
        return {'splits-TOTAL_FORMS': '2', 'splits-INITIAL_FORMS': '0', 'splits-MIN_NUM_FORMS': '0', 'splits-MAX_NUM_FORMS': '20', 'splits-0-category': str(self.a.pk), 'splits-0-amount': '25', 'splits-1-category': str(self.b.pk), 'splits-1-amount': '75.01', **extra}

    def test_no_javascript_review_total_and_owned_categories(self):
        self.client.force_login(self.user)
        url = reverse('transactions:split', args=[self.item.pk])
        response = self.client.post(url, self.post_rows(**{'splits-1-amount': '70'}))
        self.assertContains(response, 'Category amounts must add up')
        self.assertFalse(self.item.splits.exists())
        other = get_user_model().objects.create_user('another')
        category = Category.objects.create(user=other, name='Private')
        response = self.client.post(url, self.post_rows(**{'splits-1-category': str(category.pk)}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.item.splits.exists())
        self.assertEqual(self.client.post(url, self.post_rows()).status_code, 302)
        self.assertEqual(self.item.splits.count(), 2)
        self.assertEqual(self.client.post(url, {'clear_split': '1'}).status_code, 302)
        self.assertFalse(self.item.splits.exists())

    def test_invalid_decimal_and_excessive_category_keep_native_recovery_fields(self):
        self.client.force_login(self.user)
        url = reverse('transactions:split', args=[self.item.pk])
        response = self.client.post(url, self.post_rows(**{'splits-0-amount': 'invalid'}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['formset'].forms[0]['amount'].value(), 'invalid')
        self.assertEqual(response.context['formset'].forms[0].fields['amount'].widget.input_type, 'text')
        self.assertContains(response, 'value="invalid"')
        response = self.client.post(url, self.post_rows(**{'splits-0-amount': '100.02'}))
        self.assertFormError(response.context['formset'].forms[0], 'amount', 'Category amount cannot exceed the transaction total.')
        self.assertEqual(response.context['formset'].forms[0]['amount'].value(), '100.02')
        self.assertFalse(self.item.splits.exists())
