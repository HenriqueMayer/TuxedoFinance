# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Reject excessive legacy schedules before writes and preserve recovery paths."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import ERROR, SUCCESS, get_messages
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CreditCard, DebitCard
from categories.models import Category
from transactions import services
from transactions.models import Transaction
from transactions.projection import (
    ProjectionLimitExceeded, occurrence_months, occurrence_window, validate_occurrences,
)
from transactions.tests.queries import writes


class ProjectionGuardFixture:
    """Synthetic owned instruments shared without introducing a test atomic block."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user('projection-guard-owner')
        self.category = Category.objects.create(user=self.user, name='Projection expenses')
        self.bank = Bank.objects.create(user=self.user, name='Projection bank')
        self.account = BankAccount.objects.create(
            user=self.user, bank=self.bank, name='Projection account', currency='BRL',
            opening_balance=Decimal('1000.00'),
        )
        self.debit = DebitCard.objects.create(
            user=self.user, account=self.account, name='Projection debit',
        )
        self.credit = CreditCard.objects.create(
            user=self.user, account=self.account, name='Projection credit',
            closing_day=24, due_day=31,
        )

    def source(self, **changes):
        values = {
            'user': self.user, 'category': self.category, 'title': 'Existing expense',
            'amount': Decimal('17.23'), 'transaction_type': 'EXPENSE',
            'payment_channel': 'ACCOUNT', 'bank_account': self.account,
            'date': date(2026, 1, 15),
        }
        values.update(changes)
        return Transaction(**values)

    def save_source(self, **changes):
        item = self.source(**changes)
        # Deliberately use the ORM path which historical imports can also use.
        item.save()
        return item

    def existing_projection(self):
        account_source = self.save_source()
        self.save_source(
            title='Existing card purchase', amount=Decimal('31.41'),
            payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit,
        )
        services.sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        self.assertTrue(BankMovement.objects.filter(user=self.user).exists())
        self.assertTrue(CardInvoice.objects.filter(user=self.user).exists())
        return account_source

    def financial_state(self):
        return {
            model.__name__: list(model.objects.order_by('pk').values())
            for model in (Transaction, BankMovement, CardInvoice)
        }

    def post_data(self, **changes):
        values = {
            'title': 'Recoverable submission', 'amount': '22.34',
            'transaction_type': 'EXPENSE', 'category': str(self.category.pk),
            'payment_channel': 'ACCOUNT', 'bank_account': str(self.account.pk),
            'date': '2026-01-15', 'installments': '1',
            'notes': 'Keep this unsaved explanation.',
            'next': '/transactions/?q=Recoverable&sort=oldest',
        }
        values.update(changes)
        return values


class MonthlyOccurrenceBoundaryTests(ProjectionGuardFixture, TestCase):
    def test_open_schedule_accepts_1199_and_1200_but_rejects_1201_occurrences(self):
        horizon = date(2099, 12, 31)
        for start, expected in (
            (date(2000, 2, 1), 1199),
            (date(2000, 1, 1), 1200),
            (date(1999, 12, 1), 1201),
        ):
            with self.subTest(occurrences=expected):
                item = self.source(date=start, is_fixed=True)
                self.assertEqual(occurrence_window(item, horizon), (start, expected))
                months = list(occurrence_months(item, horizon))
                self.assertEqual(len(months), expected)
                self.assertEqual((months[0], months[-1]), (start, date(2099, 12, 1)))
                if expected > 1200:
                    with self.assertRaises(ProjectionLimitExceeded):
                        validate_occurrences(item, horizon)
                else:
                    validate_occurrences(item, horizon)

    def test_card_billing_shift_counts_billed_months_at_the_limit(self):
        item = self.source(
            date=date(1999, 12, 31), is_fixed=True,
            payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit,
        )
        horizon = date(2099, 12, 31)
        self.assertEqual(item.billing_offset, 1)
        self.assertEqual(occurrence_window(item, horizon), (date(2000, 1, 1), 1200))
        validate_occurrences(item, horizon)
        item.billing_override = Transaction.BillChoice.CURRENT
        self.assertEqual(occurrence_window(item, horizon), (date(1999, 12, 1), 1201))
        with self.assertRaises(ProjectionLimitExceeded):
            validate_occurrences(item, horizon)

    def test_account_instruments_exclude_an_occurrence_after_the_horizon_day(self):
        for channel, instrument in (
            ('ACCOUNT', {'bank_account': self.account}),
            ('PIX', {'bank_account': self.account}),
            ('DEBIT_CARD', {'bank_account': None, 'debit_card': self.debit}),
        ):
            with self.subTest(channel=channel):
                item = self.source(
                    date=date(1999, 12, 31), is_fixed=True,
                    payment_channel=channel, **instrument,
                )
                horizon = date(2099, 12, 30)
                self.assertEqual(occurrence_window(item, horizon), (date(1999, 12, 1), 1200))
                months = list(occurrence_months(item, horizon))
                self.assertEqual(len(months), 1200)
                self.assertEqual(months[-1], date(2099, 11, 1))
                validate_occurrences(item, horizon)
                self.assertEqual(occurrence_window(item, date(2099, 12, 31))[1], 1201)
                with self.assertRaises(ProjectionLimitExceeded):
                    validate_occurrences(item, date(2099, 12, 31))

    def test_fixed_until_keeps_the_shifted_final_bill_at_all_three_boundaries(self):
        for end, final_bill, expected in (
            (date(2099, 11, 1), date(2099, 12, 1), 1199),
            (date(2099, 12, 1), date(2100, 1, 1), 1200),
            (date(2100, 1, 1), date(2100, 2, 1), 1201),
        ):
            with self.subTest(occurrences=expected):
                item = self.source(
                    date=date(2000, 1, 31), is_fixed=True, fixed_until=end,
                    payment_channel='CREDIT_CARD', bank_account=None, credit_card=self.credit,
                )
                horizon = date(2200, 1, 31)
                self.assertEqual(occurrence_window(item, horizon), (date(2000, 2, 1), expected))
                months = list(occurrence_months(item, horizon))
                self.assertEqual(len(months), expected)
                self.assertEqual(months[-1], final_bill)
                self.assertEqual(item.amount_for_month(final_bill.year, final_bill.month), item.amount)
                if expected > 1200:
                    with self.assertRaises(ProjectionLimitExceeded):
                        validate_occurrences(item, horizon)
                else:
                    validate_occurrences(item, horizon)

    def test_a_long_gap_after_a_short_ended_schedule_does_not_count_as_work(self):
        item = self.source(date=date.min, is_fixed=True, fixed_until=date(1, 3, 31))
        horizon = date(2026, 10, 18)
        self.assertEqual(occurrence_window(item, horizon), (date.min, 3))
        self.assertEqual(list(occurrence_months(item, horizon)), [
            date(1, 1, 1), date(1, 2, 1), date(1, 3, 1),
        ])
        validate_occurrences(item, horizon)


class LedgerProjectionAtomicityTests(ProjectionGuardFixture, TransactionTestCase):
    def test_every_direct_orm_instrument_is_rejected_before_begin_or_any_write(self):
        self.existing_projection()
        self.assertFalse(connection.in_atomic_block)
        for channel, instrument in (
            ('ACCOUNT', {'bank_account': self.account}),
            ('PIX', {'bank_account': self.account}),
            ('DEBIT_CARD', {'bank_account': None, 'debit_card': self.debit}),
            ('CREDIT_CARD', {'bank_account': None, 'credit_card': self.credit}),
        ):
            with self.subTest(channel=channel):
                excessive = self.save_source(
                    title=f'Imported excessive {channel}', date=date.min,
                    is_fixed=True, payment_channel=channel, **instrument,
                )
                before = self.financial_state()
                with CaptureQueriesContext(connection) as queries:
                    with self.assertRaises(ProjectionLimitExceeded):
                        services.sync_user_ledger(self.user, through_date=date(2026, 10, 18))
                self.assertEqual(writes(queries), [])
                self.assertFalse(any(
                    query['sql'].lstrip().upper().startswith(('BEGIN', 'SAVEPOINT'))
                    for query in queries
                ), [query['sql'] for query in queries])
                self.assertEqual(self.financial_state(), before)
                self.assertFalse(connection.in_atomic_block)
                excessive.delete()

    def test_source_changed_after_preflight_is_rechecked_and_rolled_back_under_lock(self):
        item = self.existing_projection()
        before = self.financial_state()
        original_sources = services._sources
        source_reads = 0

        def changed_locked_sources(user):
            nonlocal source_reads
            source_reads += 1
            if source_reads == 2:
                self.assertTrue(connection.in_atomic_block)
                Transaction.objects.filter(pk=item.pk).update(date=date.min, is_fixed=True)
            return original_sources(user)

        with patch('transactions.services._sources', side_effect=changed_locked_sources):
            with CaptureQueriesContext(connection) as queries:
                with self.assertRaises(ProjectionLimitExceeded):
                    services.sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        self.assertEqual(source_reads, 2)
        # Only the deliberately injected source race wrote; projection never did.
        self.assertEqual(len(writes(queries)), 1)
        self.assertIn('"transactions_transaction"', writes(queries)[0])
        self.assertTrue(any(query['sql'].upper().startswith('ROLLBACK') for query in queries))
        self.assertEqual(self.financial_state(), before)
        self.assertFalse(connection.in_atomic_block)


class LedgerProjectionRecoveryTests(ProjectionGuardFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_legacy_gets_reach_the_real_list_with_a_warning_and_preserve_balances(self):
        self.existing_projection()
        excessive = self.save_source(title='Legacy schedule requiring review', date=date.min, is_fixed=True)
        invoice = CardInvoice.objects.get(user=self.user)
        before = self.financial_state()
        for url in (
            reverse('dashboard:index'),
            reverse('dashboard:reports'),
            reverse('banking:list'),
            reverse('banking:detail', args=[self.bank.pk]),
            reverse('banking:invoices'),
            reverse('banking:card_invoices', args=[self.credit.pk]),
            reverse('banking:invoice_detail', args=[invoice.pk]),
            reverse('planning:index'),
        ):
            with self.subTest(url=url):
                response = self.client.get(url, follow=True)
                self.assertEqual(response.redirect_chain, [(reverse('transactions:list'), 302)])
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'transactions/list.html')
                self.assertTrue(response.context['has_transactions'])
                self.assertIn(excessive.pk, [item.pk for item in response.context['transactions']])
                self.assertContains(response, excessive.title)
                self.assertContains(response, 'Ledger synchronization was stopped.')
                self.assertContains(response, 'No changes were saved.')
                notices = list(get_messages(response.wsgi_request))
                self.assertTrue(any(message.level == ERROR for message in notices))
                self.assertFalse(any(message.level == SUCCESS for message in notices))
                self.assertEqual(self.financial_state(), before)

    def test_htmx_refusal_requests_a_full_redirect_to_the_recovery_list(self):
        self.save_source(title='Legacy HTMX schedule', date=date.min, is_fixed=True)
        for headers in ({'HTTP_HX_REQUEST': 'true'}, {'HTTP_X_TUXEDO_ASSETS': 'legacy-revision'}):
            with self.subTest(headers=headers):
                response = self.client.get(reverse('dashboard:index'), **headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b'')
                self.assertEqual(response['HX-Redirect'], reverse('transactions:list'))

    def test_two_excessive_sources_can_be_corrected_one_at_a_time_before_sync_resumes(self):
        account_source = self.existing_projection()
        card_source = Transaction.objects.get(user=self.user, credit_card=self.credit)
        Transaction.objects.filter(pk__in=[account_source.pk, card_source.pk]).update(
            date=date.min, is_fixed=True,
        )
        before = self.financial_state()
        untouched = Transaction.objects.filter(pk=card_source.pk).values().get()
        first = self.client.post(
            reverse('transactions:update', args=[account_source.pk]),
            self.post_data(title=account_source.title, amount='67.89', next=reverse('transactions:list')),
            follow=True,
        )
        self.assertEqual(first.redirect_chain, [(reverse('transactions:list'), 302)])
        self.assertEqual(first.status_code, 200)
        account_source.refresh_from_db()
        self.assertEqual(account_source.date, date(2026, 1, 15))
        self.assertEqual(account_source.amount, Decimal('67.89'))
        self.assertFalse(account_source.is_fixed)
        self.assertEqual(Transaction.objects.filter(pk=card_source.pk).values().get(), untouched)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)
        self.assertEqual(self.financial_state()['BankMovement'], before['BankMovement'])
        self.assertEqual(self.financial_state()['CardInvoice'], before['CardInvoice'])
        self.assertTrue(any(
            'synchronization' in str(message).lower() and 'stopped' in str(message).lower()
            for message in get_messages(first.wsgi_request)
        ))
        self.assertNotContains(first, 'No changes were saved.')
        second = self.client.post(
            reverse('transactions:update', args=[card_source.pk]),
            self.post_data(
                title=card_source.title, amount='98.76', payment_channel='CREDIT_CARD',
                bank_account='', credit_card=str(self.credit.pk), next=reverse('transactions:list'),
            ),
            follow=True,
        )
        self.assertEqual(second.redirect_chain, [(reverse('transactions:list'), 302)])
        self.assertEqual(second.status_code, 200)
        card_source.refresh_from_db()
        self.assertEqual(card_source.date, date(2026, 1, 15))
        self.assertEqual(card_source.amount, Decimal('98.76'))
        self.assertFalse(card_source.is_fixed)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)
        self.assertEqual(BankMovement.objects.get(
            source_key=f'transaction:{account_source.pk}:2026-01',
        ).amount, Decimal('67.89'))
        self.assertEqual(CardInvoice.objects.get(card=self.credit).amount, Decimal('98.76'))
        self.assertEqual(self.client.get(reverse('dashboard:index')).status_code, 200)

    def test_two_excessive_sources_can_be_deleted_one_at_a_time_preserving_other_data(self):
        account_source = self.existing_projection()
        card_source = Transaction.objects.get(user=self.user, credit_card=self.credit)
        healthy = self.save_source(title='Unrelated preserved source', amount=Decimal('5.67'))
        services.sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        healthy_values = Transaction.objects.filter(pk=healthy.pk).values().get()
        healthy_movement = BankMovement.objects.filter(
            source_key=f'transaction:{healthy.pk}:2026-01',
        ).values().get()
        Transaction.objects.filter(pk__in=[account_source.pk, card_source.pk]).update(
            date=date.min, is_fixed=True,
        )
        before = self.financial_state()
        untouched = Transaction.objects.filter(pk=card_source.pk).values().get()
        first = self.client.post(reverse('transactions:delete', args=[account_source.pk]), follow=True)
        self.assertEqual(first.redirect_chain, [(reverse('transactions:list'), 302)])
        self.assertEqual(first.status_code, 200)
        self.assertFalse(Transaction.objects.filter(pk=account_source.pk).exists())
        self.assertEqual(Transaction.objects.filter(pk=card_source.pk).values().get(), untouched)
        self.assertEqual(self.financial_state()['BankMovement'], before['BankMovement'])
        self.assertEqual(self.financial_state()['CardInvoice'], before['CardInvoice'])
        self.assertTrue(any(
            'synchronization' in str(message).lower() and 'stopped' in str(message).lower()
            for message in get_messages(first.wsgi_request)
        ))
        self.assertNotContains(first, 'No changes were saved.')
        second = self.client.post(reverse('transactions:delete', args=[card_source.pk]), follow=True)
        self.assertEqual(second.redirect_chain, [(reverse('transactions:list'), 302)])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(Transaction.objects.filter(pk=card_source.pk).exists())
        self.assertEqual(Transaction.objects.filter(pk=healthy.pk).values().get(), healthy_values)
        self.assertEqual(list(BankMovement.objects.filter(user=self.user).values()), [healthy_movement])
        self.assertFalse(CardInvoice.objects.filter(user=self.user).exists())
        self.account.refresh_from_db()
        self.assertEqual(self.account.opening_balance, Decimal('1000.00'))
        self.assertEqual(self.client.get(reverse('dashboard:index')).status_code, 200)

    def test_an_ordinary_deletion_still_rolls_back_while_excessive_sources_remain(self):
        ordinary = self.existing_projection()
        self.save_source(title='First legacy blocker', date=date.min, is_fixed=True)
        self.save_source(title='Second legacy blocker', date=date.min, is_fixed=True)
        before = self.financial_state()
        response = self.client.post(reverse('transactions:delete', args=[ordinary.pk]), follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('transactions:list'), 302)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.financial_state(), before)
        self.assertContains(response, 'No changes were saved.')
        self.assertFalse(any(message.level == SUCCESS for message in get_messages(response.wsgi_request)))

    def test_another_users_excessive_source_does_not_block_owned_consultations(self):
        self.existing_projection()
        other = get_user_model().objects.create_user('projection-guard-other')
        other_category = Category.objects.create(user=other, name='Private category')
        other_bank = Bank.objects.create(user=other, name='Private bank')
        other_account = BankAccount.objects.create(
            user=other, bank=other_bank, name='Private account', currency='BRL',
        )
        private = self.save_source(
            user=other, category=other_category, bank_account=other_account,
            title='Private excessive source', date=date.min, is_fixed=True,
        )
        private_values = Transaction.objects.filter(pk=private.pk).values().get()
        services.sync_user_ledger(self.user, through_date=date(2026, 10, 18))
        for route in ('dashboard:index', 'banking:list', 'banking:invoices', 'planning:index'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, private.title)
                self.assertNotContains(response, 'Ledger synchronization was stopped.')
        self.assertEqual(Transaction.objects.filter(pk=private.pk).values().get(), private_values)
        self.assertFalse(BankMovement.objects.filter(user=other).exists())
        self.assertFalse(CardInvoice.objects.filter(user=other).exists())

    def test_create_sync_failure_rolls_back_source_and_keeps_bound_values_without_success(self):
        self.existing_projection()
        legacy = self.save_source(title='Legacy blocker', date=date.min, is_fixed=True)
        before = self.financial_state()
        payload = self.post_data()
        response = self.client.post(reverse('transactions:create'), payload)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.is_bound)
        self.assertIsNone(form.instance.pk)
        self.assertEqual(form['title'].value(), payload['title'])
        self.assertEqual(form['amount'].value(), payload['amount'])
        self.assertEqual(form['notes'].value(), payload['notes'])
        self.assertEqual(response.context['return_url'], payload['next'])
        self.assertEqual(form.non_field_errors().as_data()[0].code, 'projection_limit')
        self.assertFalse(any(message.level == SUCCESS for message in get_messages(response.wsgi_request)))
        self.assertEqual(self.financial_state(), before)
        # The owner can repair the historical source and retry the same draft.
        correction = self.client.post(reverse('transactions:update', args=[legacy.pk]),
                                      self.post_data(title=legacy.title, is_fixed='on'))
        self.assertEqual(correction.status_code, 302)
        retry = self.client.post(reverse('transactions:create'), payload)
        self.assertEqual(retry.status_code, 302)
        created = Transaction.objects.get(user=self.user, title=payload['title'])
        self.assertEqual(created.amount, Decimal(payload['amount']))
        self.assertTrue(BankMovement.objects.filter(source_key=f'transaction:{created.pk}:2026-01').exists())

    def test_update_sync_failure_rolls_back_source_and_keeps_the_attempt_bound(self):
        item = self.existing_projection()
        self.save_source(title='Legacy blocker', date=date.min, is_fixed=True)
        before = self.financial_state()
        payload = self.post_data(title='Unsaved replacement title', amount='67.89')
        response = self.client.post(reverse('transactions:update', args=[item.pk]), payload)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.is_bound)
        self.assertEqual(form.instance.pk, item.pk)
        self.assertEqual(form['title'].value(), payload['title'])
        self.assertEqual(form['amount'].value(), payload['amount'])
        self.assertEqual(form.non_field_errors().as_data()[0].code, 'projection_limit')
        self.assertFalse(any(message.level == SUCCESS for message in get_messages(response.wsgi_request)))
        self.assertEqual(self.financial_state(), before)
