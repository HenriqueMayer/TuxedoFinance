# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Server contracts behind the progressive editorial transaction sheet."""
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser

from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserPreference
from banking.forms import BankTransferForm
from banking.models import Bank, BankAccount, CreditCard, DebitCard
from categories.models import Category
from pages.templatetags.form_ui import form_control
from transactions.forms import TransactionForm
from transactions.models import Transaction


class FormControls(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.controls = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in ('input', 'select', 'option', 'fieldset'):
            self.controls.append((tag, dict(attrs)))

    def inputs(self, name):
        return [attrs for tag, attrs in self.controls if tag == 'input' and attrs.get('name') == name]


class EditorialTransactionFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user('editorial-owner', password='test')
        cls.other = user_model.objects.create_user('editorial-other', password='test')
        cls.bank = Bank.objects.create(user=cls.owner, name='Editorial bank', color='#315D50')
        cls.account = BankAccount.objects.create(
            pk=1001, user=cls.owner, bank=cls.bank, name='Owned account',
            currency='BRL', opening_balance=Decimal('1000.00'),
        )
        cls.category = Category.objects.create(pk=1001, user=cls.owner, name='Owned category')
        cls.debit = DebitCard.objects.create(
            user=cls.owner, account=cls.account, name='Owned debit', color='#253330',
        )
        cls.credit = CreditCard.objects.create(
            pk=1001, user=cls.owner, account=cls.account, name='Owned credit',
            closing_day=20, due_day=10, color='#5B3E7C',
            gradient_end='#C6A173', gradient_angle=45,
        )
        other_bank = Bank.objects.create(user=cls.other, name='Private bank')
        other_account = BankAccount.objects.create(user=cls.other, bank=other_bank, name='Private account')
        cls.other_category = Category.objects.create(user=cls.other, name='Private category')
        cls.other_credit = CreditCard.objects.create(
            user=cls.other, account=other_account, name='Private credit',
            closing_day=15, due_day=25,
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def payload(self, **overrides):
        values = {
            'title': 'Native transaction', 'amount': '12.34',
            'transaction_type': 'EXPENSE', 'payment_channel': 'ACCOUNT',
            'category': str(self.category.pk), 'bank_account': str(self.account.pk),
            'date': '14/08/2026', 'installments': '1',
        }
        values.update(overrides)
        return values

    def test_initial_short_choices_are_native_unselected_radio_groups(self):
        response = self.client.get(reverse('transactions:create'))
        self.assertEqual(response.status_code, 200)
        controls = FormControls(response.content.decode())
        for name, count in (('transaction_type', 2), ('payment_channel', 4)):
            with self.subTest(field=name):
                radios = controls.inputs(name)
                self.assertEqual(len(radios), count)
                self.assertTrue(all(control.get('type') == 'radio' for control in radios))
                self.assertTrue(all('checked' not in control for control in radios))
                self.assertTrue(all('required' in control for control in radios))
                self.assertContains(response, f'data-entry-choice="{name}"')
        self.assertNotContains(response, '<select name="transaction_type"')
        self.assertNotContains(response, '<select name="payment_channel"')

    def test_invalid_native_post_retains_segment_selection_and_error_relationships(self):
        response = self.client.post(
            reverse('transactions:create'),
            self.payload(amount='0', date='31/02/2026', payment_channel='CREDIT_CARD',
                         bank_account='', credit_card=''),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.filter(user=self.owner).count(), 0)
        controls = FormControls(response.content.decode())
        for name, selected in (('transaction_type', 'EXPENSE'), ('payment_channel', 'CREDIT_CARD')):
            chosen = [control for control in controls.inputs(name) if 'checked' in control]
            self.assertEqual([control['value'] for control in chosen], [selected])
        self.assertContains(response, 'value="31/02/2026"')
        self.assertContains(response, 'id="id_date-error-1"')
        self.assertContains(response, 'id="id_payment_channel-error-1"')
        payment = next(control for control in controls.inputs('payment_channel') if 'checked' in control)
        self.assertEqual(payment.get('aria-invalid'), 'true')
        self.assertIn('id_payment_channel-error-1', payment.get('aria-describedby', ''))

    def test_native_post_creates_the_same_single_owned_financial_source(self):
        response = self.client.post(reverse('transactions:create'), self.payload())
        self.assertEqual(response.status_code, 302)
        item = Transaction.objects.get(user=self.owner)
        self.assertEqual(item.amount, Decimal('12.34'))
        self.assertEqual(item.bank_account, self.account)
        self.assertEqual(item.category, self.category)
        self.assertEqual(item.date, date(2026, 8, 14))
        self.assertEqual(item.payment_channel, Transaction.PaymentChannel.ACCOUNT)

    def test_owned_record_fields_keep_shared_selects_and_unlocalized_identifiers(self):
        form = TransactionForm(user=self.owner)
        for name in ('category', 'bank_account', 'debit_card', 'credit_card'):
            with self.subTest(field=name):
                self.assertIsInstance(form.fields[name].widget, forms.Select)
                rendered = str(form_control(form[name]))
                self.assertIn('data-search-select', rendered)
                self.assertIn(f'id="id_{name}"', rendered)
                self.assertNotIn('Private ', rendered)
        self.assertIn('value="1001"', str(form_control(form['category'])))
        self.assertIn('value="1001"', str(form_control(form['credit_card'])))
        self.assertNotIn('value="1.001"', str(form_control(form['credit_card'])))
        forged = TransactionForm(
            user=self.owner,
            data=self.payload(category=str(self.other_category.pk)),
        )
        self.assertFalse(forged.is_valid())
        self.assertIn('category', forged.errors)

    def test_card_shortcut_preserves_deliberate_owned_context(self):
        response = self.client.get(reverse('transactions:create'), {'credit_card': self.credit.pk})
        form = response.context['form']
        self.assertEqual(form['transaction_type'].value(), 'EXPENSE')
        self.assertEqual(form['payment_channel'].value(), 'CREDIT_CARD')
        self.assertEqual(str(form['credit_card'].value()), str(self.credit.pk))
        controls = FormControls(response.content.decode())
        self.assertEqual(
            [control['value'] for control in controls.inputs('payment_channel') if 'checked' in control],
            ['CREDIT_CARD'],
        )
        foreign = self.client.get(reverse('transactions:create'), {'credit_card': self.other_credit.pk})
        self.assertNotIn('credit_card', foreign.context['form'].initial)

    def test_payment_miniature_metadata_is_owned_complete_and_html_escaped(self):
        self.account.name = 'Daily <account> & savings'
        self.account.save(update_fields=['name'])
        form = TransactionForm(user=self.owner)
        for name, record, kind in (
            ('bank_account', self.account, 'account'),
            ('debit_card', self.debit, 'card'),
            ('credit_card', self.credit, 'card'),
        ):
            with self.subTest(field=name):
                rendered = str(form_control(form[name]))
                self.assertIn('data-payment-choices="true"', rendered)
                self.assertIn(f'data-payment-kind="{kind}"', rendered)
                parsed = FormControls(rendered)
                option = next(attrs for tag, attrs in parsed.controls
                              if tag == 'option' and attrs.get('value') == str(record.pk))
                self.assertEqual(option['data-choice-name'], record.name)
                self.assertEqual(option['data-bank-color'], self.bank.color)
                self.assertIn(self.bank.name, option['data-choice-detail'])
                self.assertIn(self.account.currency, option['data-choice-detail'])
                if kind == 'card':
                    self.assertIn(self.account.name, option['data-choice-detail'])
                    self.assertEqual(option['data-card-color'], record.color)
                    self.assertEqual(option['data-card-gradient-end'], record.gradient_end)
                    self.assertEqual(option['data-card-gradient-angle'], str(record.gradient_angle))
                else:
                    self.assertEqual(option['data-pix-enabled'], 'true')
                self.assertNotIn('<account>', rendered)
                self.assertIn('&lt;account&gt;', rendered)
                self.assertNotIn('Private ', rendered)
        self.assertNotIn('data-payment-choices', str(form_control(form['category'])))

    def test_amount_enhancement_keeps_native_decimal_validation_and_post_contract(self):
        form = TransactionForm(user=self.owner)
        self.assertIsInstance(form.fields['amount'].widget, forms.NumberInput)
        self.assertIn('data-money-input', form.fields['amount'].widget.attrs)
        self.assertIn('type="number"', str(form['amount']))
        valid = TransactionForm(user=self.owner, data=self.payload(amount='1234.56'))
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.cleaned_data['amount'], Decimal('1234.56'))
        for value in ('12.345', 'NaN', '1e100'):
            with self.subTest(amount=value):
                invalid = TransactionForm(user=self.owner, data=self.payload(amount=value))
                self.assertFalse(invalid.is_valid())
                self.assertIn('amount', invalid.errors)

    def test_shared_calendar_preserves_both_date_formats_across_forms(self):
        preference = UserPreference.for_user(self.owner)
        for order, text in (('DMY', '14/08/2026'), ('MDY', '08/14/2026')):
            with self.subTest(order=order):
                preference.date_format = order
                preference.save(update_fields=['date_format'])
                form = TransactionForm(user=self.owner, data=self.payload(date=text))
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data['date'], date(2026, 8, 14))
                for name in ('date', 'fixed_until'):
                    self.assertEqual(form.fields[name].widget.attrs['data-date-picker'], 'true')
                    self.assertEqual(form.fields[name].widget.attrs['data-date-order'], order)
                    self.assertNotIn('type="date"', str(form[name]))
                self.assertIn(f'value="{text}"', str(form['date']))
                iso_form = TransactionForm(user=self.owner, data=self.payload(date='2026-08-14'))
                self.assertTrue(iso_form.is_valid(), iso_form.errors)
                self.assertEqual(iso_form.cleaned_data['date'], date(2026, 8, 14))
        transfer = BankTransferForm(user=self.owner)
        self.assertEqual(transfer.fields['date'].widget.attrs['data-date-picker'], 'true')
