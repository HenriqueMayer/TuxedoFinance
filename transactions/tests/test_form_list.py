"""Form list coverage for transactions."""

import csv
import io
from datetime import date
from decimal import Decimal
from django.urls import reverse
from accounts.models import UserPreference
from banking.models import BankMovement
from categories.models import Category
from transactions.forms import TransactionForm
from transactions.models import Transaction
from transactions.tests.fixtures import TransactionFixture


class TransactionFormAndListTests(TransactionFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_form_options_are_scoped_to_user(self):
        form = TransactionForm(user=self.user)
        self.assertQuerySetEqual(form.fields['bank_account'].queryset, [self.account])
        self.assertNotIn(self.other_credit, form.fields['credit_card'].queryset)
        self.assertIn('data-best-purchase-day="24"', str(form['credit_card']))

    def test_create_form_includes_category_search(self):
        response = self.client.get(reverse('transactions:create'))
        self.assertContains(response, 'data-search-id="category-search"', html=False)
        self.assertContains(response, 'Type to search')
        self.assertContains(response, 'data-search-select', html=False)
        self.assertContains(response, 'id="id_category"', html=False)
        self.assertContains(response, 'id="payment-channel-status"', html=False)
        self.assertNotContains(response, 'id="debit-card-fields" data-has-errors="false" hidden', html=False)
        self.assertNotContains(response, 'id="credit-card-fields" data-has-errors="false" hidden', html=False)
        self.assertContains(response, 'id="credit-card-best-purchase"', html=False)

    def test_transaction_dates_follow_user_date_format(self):
        preference = UserPreference.for_user(self.user)
        preference.date_format = 'MDY'
        preference.save(update_fields=['date_format'])

        form = TransactionForm(
            user=self.user,
            instance=Transaction(date=date(2026, 8, 14)),
        )
        rendered = str(form['date'])
        self.assertIn('value="08/14/2026"', rendered)
        self.assertIn('placeholder="MM/DD/YYYY"', rendered)
        self.assertNotIn('type="date"', rendered)

        bound = TransactionForm(
            user=self.user,
            data={
                'title': 'Formatted date', 'amount': '10.00',
                'transaction_type': 'EXPENSE', 'category': self.category.pk,
                'payment_channel': 'ACCOUNT', 'bank_account': self.account.pk,
                'installments': '1', 'date': '08/14/2026',
            },
        )
        self.assertTrue(bound.is_valid(), bound.errors)
        self.assertEqual(bound.cleaned_data['date'], date(2026, 8, 14))

    def test_account_query_parameter_is_user_scoped_initial_state(self):
        response = self.client.get(reverse('transactions:create'), {'account': self.account.pk})
        self.assertEqual(response.context['form'].initial['bank_account'], self.account)
        self.assertEqual(response.context['form'].initial['payment_channel'], 'ACCOUNT')

        other_response = self.client.get(
            reverse('transactions:create'), {'account': self.other_account.pk}
        )
        self.assertNotIn('bank_account', other_response.context['form'].initial)

    def test_list_labels_amount_with_its_native_currency(self):
        self.account.currency = 'USD'
        self.account.save(update_fields=['currency'])
        self.make_transaction(title='Dollar purchase')
        response = self.client.get(reverse('transactions:list'))
        self.assertContains(response, 'USD 120,00')
        self.assertNotContains(response, 'R$ 120,00')

    def test_category_choices_include_hierarchy_metadata_without_other_users(self):
        parent = Category.objects.create(user=self.user, name='Alimentação')
        Category.objects.create(user=self.user, name='Café', parent_category=parent)
        form = TransactionForm(user=self.user)

        rendered = str(form['category'])

        self.assertIn('Alimentação &gt; Café', rendered)
        self.assertIn('data-search="Alimentação Café"', rendered)
        self.assertNotIn('Private', rendered)

    def test_form_exposes_pix_capability_without_trusting_the_browser(self):
        self.account.pix_enabled = False
        self.account.save(update_fields=['pix_enabled'])
        form = TransactionForm(user=self.user)

        self.assertIn('data-pix-enabled="false"', str(form['bank_account']))
        self.assertIn('data-account-label="North Bank &gt; Daily (BRL)"', str(form['debit_card']))

    def test_form_filters_typed_categories_and_server_rejects_a_mismatch(self):
        income_category = Category.objects.create(
            user=self.user, name='Salary', transaction_type=Category.TransactionType.INCOME
        )
        form = TransactionForm(user=self.user)
        self.assertIn('data-transaction-type="INCOME"', str(form['category']))

        invalid = TransactionForm(
            user=self.user,
            data={
                'title': 'Bad category', 'amount': '10.00', 'transaction_type': 'EXPENSE',
                'category': income_category.pk, 'payment_channel': 'ACCOUNT',
                'bank_account': self.account.pk, 'installments': '1', 'date': '2026-01-01',
            },
        )
        self.assertFalse(invalid.is_valid())
        self.assertIn('category', invalid.errors)

    def test_form_rejects_mismatched_instrument_without_javascript(self):
        form = TransactionForm(
            user=self.user,
            data={
                'title': 'Bad channel', 'amount': '10.00',
                'transaction_type': 'EXPENSE', 'category': self.category.pk,
                'payment_channel': 'PIX', 'debit_card': self.debit.pk,
                'installments': '1', 'date': '2026-01-01',
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('payment_channel', form.errors)

    def test_list_searches_bank_account_and_card_and_isolates_users(self):
        self.make_transaction(title='Account row')
        self.make_transaction(
            title='Card row', payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None, credit_card=self.credit,
        )
        Transaction.objects.create(
            user=self.other, title='Leaked row', amount=Decimal('1'),
            transaction_type='EXPENSE', category=self.other_category,
            payment_channel='ACCOUNT', bank_account=self.other_account,
            date=date(2026, 1, 15),
        )
        bank_response = self.client.get(reverse('transactions:list'), {'q': 'North Bank'})
        card_response = self.client.get(reverse('transactions:list'), {'q': 'Blue Credit'})
        self.assertContains(bank_response, 'Account row')
        self.assertNotContains(bank_response, 'Leaked row')
        self.assertContains(card_response, 'Card row')

    def test_month_type_filters_and_pagination_are_preserved(self):
        for index in range(11):
            self.make_transaction(title=f'Paged {index}', amount=Decimal(index + 1))
        response = self.client.get(
            reverse('transactions:list'),
            {'q': 'Paged', 'month': '2026-01', 'type': 'EXPENSE', 'sort': 'highest'},
        )
        self.assertContains(response, 'Page 1 of 2')
        self.assertContains(response, 'page=2')
        self.assertContains(response, 'month=2026-01')

    def test_export_csv_includes_only_user_transactions(self):
        self.make_transaction(title='Own transaction')
        Transaction.objects.create(
            user=self.other, title='Private transaction', amount=Decimal('1.00'),
            transaction_type=Transaction.TransactionType.EXPENSE,
            category=self.other_category,
            payment_channel=Transaction.PaymentChannel.ACCOUNT,
            bank_account=self.other_account, date=date(2026, 1, 15),
        )

        response = self.client.get(reverse('transactions:export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="transactions.csv"')
        rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'Own transaction')
        self.assertEqual(rows[0]['amount'], '120.00')
        self.assertEqual(rows[0]['total_amount'], '120.00')

    def test_export_csv_for_month_uses_the_amount_charged_in_that_month(self):
        self.make_transaction(
            title='Installment purchase', amount=Decimal('100.00'),
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None, credit_card=self.credit, installments=2,
            date=date(2026, 1, 24),
        )

        response = self.client.get(reverse('transactions:export'), {'month': '2026-02'})

        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="transactions-2026-02.csv"',
        )
        rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['billed_month'], '2026-02-01')
        self.assertEqual(rows[0]['amount'], '50.00')
        self.assertEqual(rows[0]['total_amount'], '100.00')

    def test_create_update_delete_views_resync(self):
        create = self.client.post(
            reverse('transactions:create'),
            {
                'title': 'View item', 'amount': '10.00',
                'transaction_type': 'EXPENSE', 'category': self.category.pk,
                'payment_channel': 'ACCOUNT', 'bank_account': self.account.pk,
                'installments': '1', 'date': '2026-01-10',
            },
        )
        self.assertEqual(create.status_code, 302)
        item = Transaction.objects.get(title='View item')
        movement = BankMovement.objects.get(source_key=f'transaction:{item.pk}:2026-01')
        self.assertEqual(movement.amount, Decimal('10.00'))
        update = self.client.post(
            reverse('transactions:update', args=[item.pk]),
            {
                'title': 'View item', 'amount': '20.00',
                'transaction_type': 'EXPENSE', 'category': self.category.pk,
                'payment_channel': 'ACCOUNT', 'bank_account': self.account.pk,
                'installments': '1', 'date': '2026-01-10',
            },
        )
        self.assertEqual(update.status_code, 302)
        movement.refresh_from_db()
        self.assertEqual(movement.amount, Decimal('20.00'))
        self.client.post(reverse('transactions:delete', args=[item.pk]))
        self.assertFalse(BankMovement.objects.filter(source_key__startswith=f'transaction:{item.pk}:').exists())
