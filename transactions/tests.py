from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserPreference
from banking.models import (
    Bank, BankAccount, BankMovement, CardInvoice, CreditCard, DebitCard,
    LoyaltyProgram, RewardRedemption,
)
from categories.models import Category
from transactions.forms import TransactionForm
from transactions.models import Transaction
from transactions.services import sync_user_ledger


User = get_user_model()


class TransactionFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('owner', password='test')
        cls.other = User.objects.create_user('other', password='test')
        cls.category = Category.objects.create(user=cls.user, name='General')
        cls.other_category = Category.objects.create(user=cls.other, name='Private')
        cls.bank = Bank.objects.create(user=cls.user, name='North Bank')
        cls.account = BankAccount.objects.create(
            user=cls.user, bank=cls.bank, name='Daily', currency='BRL',
            opening_balance=Decimal('1000.00')
        )
        cls.debit = DebitCard.objects.create(
            user=cls.user, account=cls.account, name='Daily Debit'
        )
        cls.credit = CreditCard.objects.create(
            user=cls.user, account=cls.account, name='Blue Credit',
            closing_day=24, due_day=31
        )
        cls.other_bank = Bank.objects.create(user=cls.other, name='Other Bank')
        cls.other_account = BankAccount.objects.create(
            user=cls.other, bank=cls.other_bank, name='Secret', currency='BRL'
        )
        cls.other_credit = CreditCard.objects.create(
            user=cls.other, account=cls.other_account, name='Other Card',
            closing_day=10, due_day=10
        )

    def make_transaction(self, **overrides):
        values = {
            'user': self.user,
            'title': 'Purchase',
            'amount': Decimal('120.00'),
            'transaction_type': Transaction.TransactionType.EXPENSE,
            'category': self.category,
            'payment_channel': Transaction.PaymentChannel.ACCOUNT,
            'bank_account': self.account,
            'date': date(2026, 1, 15),
        }
        values.update(overrides)
        return Transaction.objects.create(**values)


class TransactionValidationTests(TransactionFixture):
    def assert_invalid(self, **overrides):
        item = self.make_transaction()
        for field, value in overrides.items():
            setattr(item, field, value)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_account_and_pix_require_only_account(self):
        for channel in (Transaction.PaymentChannel.ACCOUNT, Transaction.PaymentChannel.PIX):
            item = self.make_transaction(payment_channel=channel)
            item.full_clean()
        self.assert_invalid(payment_channel=Transaction.PaymentChannel.PIX, bank_account=None)

    def test_pix_requires_an_enabled_account(self):
        self.account.pix_enabled = False
        self.account.save(update_fields=['pix_enabled'])

        self.assert_invalid(payment_channel=Transaction.PaymentChannel.PIX)

    def test_debit_card_requires_only_debit_card(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            bank_account=None,
            debit_card=self.debit,
        )
        item.full_clean()
        self.assert_invalid(
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            debit_card=self.debit,
        )

    def test_credit_card_requires_only_credit_card(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
        )
        item.full_clean()
        self.assertTrue(item.is_credit_card)

    def test_every_relation_must_have_same_owner(self):
        self.assert_invalid(bank_account=self.other_account)
        self.assert_invalid(category=self.other_category)
        self.assert_invalid(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.other_credit,
        )

    def test_income_cannot_use_cards(self):
        self.assert_invalid(
            transaction_type=Transaction.TransactionType.INCOME,
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
        )

    def test_installments_and_override_are_credit_only(self):
        self.assert_invalid(installments=2)
        self.assert_invalid(billing_override=Transaction.BillChoice.NEXT)

    def test_fixed_and_installments_are_incompatible(self):
        self.assert_invalid(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
            installments=2,
            is_fixed=True,
        )

    def test_payment_properties(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            bank_account=None,
            debit_card=self.debit,
        )
        self.assertEqual(item.payment_account, self.account)
        self.assertEqual(item.payment_name, 'Daily Debit')
        self.assertEqual(item.payment_label, 'North Bank > Daily / Daily Debit')


class TransactionCalendarTests(TransactionFixture):
    def credit_transaction(self, **overrides):
        return self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None,
            credit_card=self.credit,
            **overrides,
        )

    def test_card_payment_date_is_due_date_even_at_zero_offset(self):
        item = self.credit_transaction(date=date(2026, 1, 10))
        self.assertEqual(item.billing_offset, 0)
        self.assertEqual(item.payment_date, date(2026, 1, 31))

    def test_statement_offset_and_short_due_month_are_clamped(self):
        item = self.credit_transaction(date=date(2026, 1, 24))
        self.assertEqual(item.billed_month, date(2026, 2, 1))
        self.assertEqual(item.payment_date, date(2026, 2, 28))

    def test_billing_override_wins(self):
        current = self.credit_transaction(
            date=date(2026, 1, 25), billing_override=Transaction.BillChoice.CURRENT
        )
        self.assertEqual(current.billed_month, date(2026, 1, 1))

    def test_installments_round_to_exact_total(self):
        item = self.credit_transaction(amount=Decimal('100.00'), installments=3)
        amounts = [item.amount_for_month(2026, month) for month in (1, 2, 3)]
        self.assertEqual(amounts, [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')])
        self.assertEqual(sum(amounts), item.amount)


class LedgerSyncTests(TransactionFixture):
    def test_pix_and_debit_are_immediate_debits(self):
        pix = self.make_transaction(title='External PIX', payment_channel=Transaction.PaymentChannel.PIX)
        self.make_transaction(
            title='Store', amount=Decimal('30.00'),
            payment_channel=Transaction.PaymentChannel.DEBIT_CARD,
            bank_account=None, debit_card=self.debit,
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        movements = BankMovement.objects.filter(user=self.user).order_by('amount')
        self.assertEqual(movements.count(), 2)
        self.assertEqual({movement.direction for movement in movements}, {'DEBIT'})
        self.assertEqual(
            BankMovement.objects.get(source_key=f'transaction:{pix.pk}:2026-01').description,
            'External PIX',
        )
        self.assertEqual(self.account.current_balance(as_of=date(2026, 1, 31)), Decimal('850.00'))

    def test_income_is_credit(self):
        self.make_transaction(
            amount=Decimal('500.00'), transaction_type=Transaction.TransactionType.INCOME
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        movement = BankMovement.objects.get(user=self.user)
        self.assertEqual((movement.direction, movement.kind), ('CREDIT', 'INCOME'))

    def test_credit_purchase_only_debits_cash_on_invoice_due_date(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None, credit_card=self.credit,
            date=date(2026, 1, 25),
        )
        sync_user_ledger(self.user, through_date=date(2026, 3, 1), projection_months=0)
        invoice = CardInvoice.objects.get(card=self.credit, reference_month=date(2026, 2, 1))
        movement = BankMovement.objects.get(user=self.user)
        self.assertEqual(invoice.amount, item.amount)
        self.assertEqual(invoice.status, CardInvoice.Status.PAID)
        self.assertEqual(movement.kind, BankMovement.Kind.INVOICE)
        self.assertEqual(movement.effective_date, date(2026, 2, 28))
        self.assertFalse(BankMovement.objects.filter(kind=BankMovement.Kind.EXPENSE).exists())

    def test_deleting_credit_purchase_removes_invoice_and_settlement(self):
        item = self.make_transaction(
            payment_channel=Transaction.PaymentChannel.CREDIT_CARD,
            bank_account=None, credit_card=self.credit,
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertTrue(CardInvoice.objects.filter(user=self.user).exists())
        item.delete()
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertFalse(CardInvoice.objects.filter(user=self.user).exists())
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_recurring_ledger_is_idempotent_and_clamps_day(self):
        item = self.make_transaction(date=date(2026, 1, 31), is_fixed=True)
        for _ in range(2):
            sync_user_ledger(self.user, through_date=date(2026, 3, 31), projection_months=0)
        movements = BankMovement.objects.filter(user=self.user).order_by('effective_date')
        self.assertEqual(movements.count(), 3)
        self.assertEqual(
            list(movements.values_list('effective_date', flat=True)),
            [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)],
        )
        self.assertEqual(movements.first().source_key, f'transaction:{item.pk}:2026-01')

    def test_update_and_delete_remove_stale_projection(self):
        item = self.make_transaction(amount=Decimal('10.00'))
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        item.amount = Decimal('25.00')
        item.save()
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertEqual(BankMovement.objects.get(user=self.user).amount, Decimal('25.00'))
        item.delete()
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=0)
        self.assertFalse(BankMovement.objects.filter(user=self.user).exists())

    def test_iof_credit_card_is_included_in_invoice(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Miles')
        RewardRedemption.objects.create(
            user=self.user, program=program, points=Decimal('1000'),
            target_account=self.account, target_amount=Decimal('10'),
            iof_amount=Decimal('2.50'), iof_credit_card=self.credit,
            date=date(2026, 1, 25),
        )
        sync_user_ledger(self.user, through_date=date(2026, 1, 31), projection_months=2)
        invoice = CardInvoice.objects.get(card=self.credit, reference_month=date(2026, 2, 1))
        self.assertEqual(invoice.amount, Decimal('2.50'))


class TransactionFormAndListTests(TransactionFixture):
    def setUp(self):
        self.client.force_login(self.user)

    def test_form_options_are_scoped_to_user(self):
        form = TransactionForm(user=self.user)
        self.assertQuerySetEqual(form.fields['bank_account'].queryset, [self.account])
        self.assertNotIn(self.other_credit, form.fields['credit_card'].queryset)

    def test_create_form_includes_category_search(self):
        response = self.client.get(reverse('transactions:create'))
        self.assertContains(response, 'id="category-search"', html=False)
        self.assertContains(response, 'Type to filter categories')
        self.assertContains(response, 'role="combobox"', html=False)
        self.assertContains(response, 'id="category-fallback"', html=False)
        self.assertContains(response, 'id="payment-channel-status"', html=False)
        self.assertNotContains(response, 'id="debit-card-fields" data-has-errors="false" hidden', html=False)
        self.assertNotContains(response, 'id="credit-card-fields" data-has-errors="false" hidden', html=False)

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
