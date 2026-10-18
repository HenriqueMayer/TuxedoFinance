# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CreditCard
from categories.models import Category
from transactions.models import Transaction, TransactionSplit


class ContextualTransactionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('contextual-transactions')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Local bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Cash', currency='BRL')
        self.a = Category.objects.create(user=self.user, name='Food', transaction_type='EXPENSE')
        self.b = Category.objects.create(user=self.user, name='Books', transaction_type='EXPENSE')
        self.income = Category.objects.create(user=self.user, name='Salary', transaction_type='INCOME')
        self.origin = '/transactions/?q=coffee&month=2026-01&page=2'
        self.data = {'title': 'Shared purchase', 'amount': '100.01', 'transaction_type': 'EXPENSE',
                     'category': str(self.a.pk), 'payment_channel': 'ACCOUNT', 'bank_account': str(self.account.pk),
                     'date': '2026-01-10', 'installments': '1', 'next': self.origin}
        self.split_data = {'split_categories': 'on', 'splits-TOTAL_FORMS': '2', 'splits-INITIAL_FORMS': '0',
                           'splits-MIN_NUM_FORMS': '0', 'splits-MAX_NUM_FORMS': '20',
                           'splits-0-category': str(self.a.pk), 'splits-0-amount': '25',
                           'splits-1-category': str(self.b.pk), 'splits-1-amount': '75.01'}

    def create_split(self):
        response = self.client.post(reverse('transactions:create'), {**self.data, **self.split_data, 'category': ''})
        self.assertRedirects(response, self.origin, fetch_redirect_response=False)
        return Transaction.objects.get(user=self.user)

    def test_create_split_is_one_source_and_one_cash_movement(self):
        item = self.create_split()
        self.assertEqual(item.category, self.a)
        self.assertEqual(item.splits.count(), 2)
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 1)
        self.assertEqual(BankMovement.objects.get(user=self.user).signed_amount, Decimal('-100.01'))

    def test_invalid_total_or_owned_category_never_saves_parent(self):
        response = self.client.post(reverse('transactions:create'), {**self.data, **self.split_data, 'splits-1-amount': '70'})
        self.assertContains(response, 'Category amounts must add up')
        self.assertNotContains(response, 'Transaction &quot;Shared purchase&quot; created.')
        self.assertContains(response, f'name="next" value="{self.origin.replace("&", "&amp;")}"', html=False)
        self.assertFalse(Transaction.objects.filter(user=self.user).exists())
        other = get_user_model().objects.create_user('private-category-owner')
        private = Category.objects.create(user=other, name='Private category')
        response = self.client.post(reverse('transactions:create'), {**self.data, **self.split_data, 'splits-1-category': str(private.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.filter(user=self.user).exists())
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_add_category_preserves_unsaved_parent_and_return_context(self):
        response = self.client.post(reverse('transactions:create'), {**self.data, **self.split_data, 'add_split': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id_splits-2-category')
        self.assertEqual(response.context['form']['title'].value(), 'Shared purchase')
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertFalse(Transaction.objects.filter(user=self.user).exists())

    def test_save_precedes_auxiliary_native_submit_in_new_split_and_error_forms(self):
        responses = [self.client.get(reverse('transactions:create')),
                     self.client.get(reverse('transactions:create'), {'split': '1'}),
                     self.client.post(reverse('transactions:create'),
                                      {**self.data, **self.split_data, 'splits-1-amount': '70'})]
        for response in responses:
            with self.subTest(split=response.context['form']['split_categories'].value()):
                main_html = response.content.decode().split('<main', 1)[1].split('</main>', 1)[0]
                form_html = re.search(r'<form\b[^>]*hx-boost="false"[^>]*>(.*?)</form>',
                                      main_html, re.S).group(1)
                buttons = re.findall(r'<button\b[^>]*type="submit"[^>]*>.*?</button>', form_html, re.S)
                self.assertEqual(len(buttons), 2)
                self.assertRegex(buttons[0], r'>\s*Save\s*</button>')
                self.assertIn('name="add_split"', buttons[1])
                self.assertContains(response, 'id="category-split-actions"')

    def edit_data(self, item):
        rows = list(item.splits.all())
        return {**self.data, **self.split_data, 'splits-INITIAL_FORMS': '2',
                'splits-0-id': str(rows[0].pk), 'splits-1-id': str(rows[1].pk)}

    def test_edit_total_and_split_together_then_clear_without_another_payment(self):
        item = self.create_split()
        movement_pk = BankMovement.objects.get(user=self.user).pk
        payload = {**self.edit_data(item), 'amount': '110.01', 'splits-1-amount': '85.01'}
        response = self.client.post(reverse('transactions:update', args=[item.pk]), payload)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.amount, Decimal('110.01'))
        self.assertEqual(sum(item.splits.values_list('amount', flat=True)), item.amount)
        movement = BankMovement.objects.get(user=self.user)
        self.assertEqual(movement.pk, movement_pk)
        self.assertEqual(movement.signed_amount, Decimal('-110.01'))
        payload.pop('split_categories')
        payload['category'] = str(self.b.pk)
        response = self.client.post(reverse('transactions:update', args=[item.pk]), payload)
        self.assertEqual(response.status_code, 302, (
            response.context['form'].errors, response.context['split_formset'].errors,
            response.context['split_formset'].non_form_errors()) if response.status_code == 200 else '')
        self.assertFalse(item.splits.exists())
        self.assertEqual(BankMovement.objects.filter(user=self.user).count(), 1)

    def test_swapping_categories_preserves_ids_and_unchanged_amounts(self):
        item = self.create_split()
        old_ids = dict(item.splits.values_list('category_id', 'pk'))
        payload = {**self.edit_data(item), 'splits-0-category': str(self.b.pk), 'splits-0-amount': '75.01',
                   'splits-1-category': str(self.a.pk), 'splits-1-amount': '25'}
        response = self.client.post(reverse('transactions:update', args=[item.pk]), payload)
        self.assertEqual(response.status_code, 302, (
            response.context['form'].errors, response.context['split_formset'].errors,
            response.context['split_formset'].non_form_errors()) if response.status_code == 200 else '')
        self.assertEqual(dict(item.splits.values_list('category_id', 'pk')), old_ids)

    def test_type_and_split_can_be_corrected_together_without_javascript(self):
        item = self.create_split()
        other_income = Category.objects.create(user=self.user, name='Other income', transaction_type='INCOME')
        payload = {**self.edit_data(item), 'transaction_type': 'INCOME',
                   'splits-0-category': str(self.income.pk), 'splits-1-category': str(other_income.pk)}
        self.assertEqual(self.client.post(reverse('transactions:update', args=[item.pk]), payload).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.category, self.income)
        self.assertEqual(BankMovement.objects.get(user=self.user).amount, Decimal('100.01'))

    def test_incompatible_categories_and_forged_initial_ids_are_rejected(self):
        response = self.client.post(reverse('transactions:create'), {**self.data, **self.split_data, 'splits-1-category': str(self.income.pk)})
        self.assertContains(response, 'Choose categories compatible')
        item = self.create_split()
        other = Transaction.objects.create(user=self.user, title='Other', amount='10', category=self.a,
            transaction_type='EXPENSE', payment_channel='ACCOUNT', bank_account=self.account, date=date(2026, 1, 1))
        foreign_split = TransactionSplit.objects.create(transaction=other, category=self.b, amount='10')
        payload = {**self.edit_data(item), 'splits-0-id': str(foreign_split.pk)}
        self.assertEqual(self.client.post(reverse('transactions:update', args=[item.pk]), payload).status_code, 200)
        foreign_split.refresh_from_db()
        self.assertEqual(foreign_split.amount, Decimal('10'))

    def test_return_url_is_explicit_and_safe_after_save_cancel_and_error(self):
        url = reverse('transactions:create') + '?' + urlencode({'next': self.origin})
        response = self.client.get(url)
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertContains(response, f'href="{self.origin.replace("&", "&amp;")}"', html=False)
        response = self.client.post(url, {**self.data, 'amount': ''})
        self.assertEqual(response.context['return_url'], self.origin)
        self.assertRedirects(self.client.post(url, {**self.data, 'next': '//external.test/'}),
                             reverse('transactions:list'), fetch_redirect_response=False)

    def test_owned_card_shortcut_and_settlement_copy(self):
        card = CreditCard.objects.create(user=self.user, account=self.account, name='Confirmed card',
            closing_day=20, due_day=25, manual_settlement_from=date(2026, 1, 1))
        response = self.client.get(reverse('transactions:create'), {'credit_card': card.pk})
        self.assertEqual(response.context['form']['transaction_type'].value(), 'EXPENSE')
        self.assertEqual(response.context['form']['credit_card'].value(), card.pk)
        self.assertContains(response, 'New invoices due on or after 01/01/2026 require confirmed payments.')
        self.assertContains(response, 'The app does not pay the bank.')
        response = self.client.get(reverse('transactions:create'), {'credit_card': card.pk, 'transaction_type': 'INCOME'})
        self.assertFalse(response.context['form']['credit_card'].value())
