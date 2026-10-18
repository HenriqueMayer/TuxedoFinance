# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CardInvoice, CreditCard, ExchangeRate, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from banking.services import create_reward_redemption, update_reward_redemption
from categories.models import Category
from dashboard.services import get_dashboard_summary, get_expenses_by_instrument
from sandbox.planning import commitment_snapshot
from transactions.models import Transaction
from transactions.services import sync_user_ledger


@patch('django.utils.timezone.localdate', return_value=date(2026, 9, 25))
class RewardRedemptionViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('redemption-history')
        self.client.force_login(self.user)
        receiving = Bank.objects.create(user=self.user, name='Receiving bank')
        funding = Bank.objects.create(user=self.user, name='Funding bank')
        self.target = BankAccount.objects.create(user=self.user, bank=receiving, name='Reward account', currency='BRL')
        self.funding = BankAccount.objects.create(user=self.user, bank=funding, name='IOF account', currency='USD', opening_balance=Decimal('100'))
        self.card = CreditCard.objects.create(user=self.user, account=self.funding, name='IOF card', closing_day=20, due_day=28)
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Independent rewards', unit_name='Miles')
        LoyaltyEntry.objects.create(user=self.user, program=self.program, direction='CREDIT', kind='ADJUSTMENT', amount='1000', date=date(2026, 9, 1))

    def redeem(self, **funding):
        return create_reward_redemption(
            user=self.user, program=self.program, points=Decimal('100'),
            target_account=self.target, target_amount=Decimal('25'), date=date(2026, 9, 21), **funding,
        )

    def detail(self, bank_id):
        return self.client.get(reverse('banking:detail', args=[bank_id]))

    def test_save_opens_history_and_card_iof_settles_once_on_due_date(self, localdate):
        response = self.client.post(reverse('banking:redemption_create'), {
            'program': self.program.pk, 'points': '100', 'target_account': self.target.pk,
            'target_amount': '25', 'iof_amount': '2.50', 'iof_credit_card': self.card.pk,
            'date': '2026-09-21', 'notes': 'September redemption',
        })
        self.assertRedirects(response, reverse('banking:detail', args=[self.target.bank_id]) + '#reward-redemptions')
        invoice = CardInvoice.objects.get(card=self.card)
        self.assertEqual((invoice.reference_month, invoice.due_date, invoice.amount), (date(2026, 10, 1), date(2026, 10, 28), Decimal('2.50')))
        self.assertEqual(self.target.current_balance(as_of=date(2026, 9, 25)), Decimal('25'))
        self.assertEqual(self.funding.current_balance(as_of=date(2026, 9, 25)), Decimal('100'))
        for _ in range(2):
            sync_user_ledger(self.user, through_date=date(2026, 10, 28))
        self.assertEqual(self.funding.current_balance(as_of=date(2026, 10, 28)), Decimal('97.50'))
        self.assertEqual(CardInvoice.objects.filter(card=self.card).count(), 1)
        self.assertEqual(BankMovement.objects.filter(account=self.funding).count(), 1)
        self.assertEqual(Transaction.objects.get(user=self.user).amount, Decimal("2.50"))

    def test_existing_card_iof_is_visible_in_receiving_and_funding_banks(self, localdate):
        redemption = self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        for bank_id in (self.target.bank_id, self.funding.bank_id):
            with self.subTest(bank_id=bank_id):
                response = self.detail(bank_id)
                self.assertEqual(response.context['redemptions'], [redemption])
                for text in ('Reward redemptions', 'Independent rewards', 'IOF on reward redemption', 'IOF card', 'Oct 2026', '28/10/2026'):
                    self.assertContains(response, text)
                self.assertContains(response, 'USD 2,50')
                self.assertContains(response, '+BRL 25,00')

    def test_account_iof_and_zero_iof_preserve_their_distinct_funding(self, localdate):
        self.redeem(iof_amount=Decimal('1.25'), iof_account=self.funding)
        self.redeem()
        response = self.detail(self.target.bank_id)
        self.assertContains(response, 'Debited from')
        self.assertContains(response, 'IOF account')
        self.assertContains(response, 'USD 1,25')
        self.assertContains(response, 'No IOF charged.')
        self.assertNotContains(response, 'Included in invoice')
        self.assertFalse(CardInvoice.objects.filter(user=self.user).exists())
        self.assertEqual(self.funding.current_balance(as_of=date(2026, 9, 25)), Decimal('98.75'))

    def test_history_excludes_unrelated_banks_and_other_users(self, localdate):
        self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        unrelated = Bank.objects.create(user=self.user, name='Unrelated bank')
        self.assertNotContains(self.detail(unrelated.pk), 'id="reward-redemptions"')
        other = get_user_model().objects.create_user('other-redemption-owner')
        self.client.force_login(other)
        self.assertEqual(self.detail(self.target.bank_id).status_code, 404)
        self.client.force_login(self.user)
        # Even an inconsistent legacy source row cannot leak through an owned
        # endpoint merely because its receiving account matches this bank.
        redemption = self.program.redemptions.get()
        redemption.user = other
        redemption.save(update_fields=['user'])
        self.assertNotContains(self.detail(self.target.bank_id), 'id="reward-redemptions"')

    def edit_data(self, **changes):
        data = {'program': self.program.pk, 'points': '100', 'target_account': self.target.pk,
                'target_amount': '25', 'date': '2026-09-21', 'iof_amount': '2.50',
                'iof_credit_card': self.card.pk, 'iof_account': '', 'notes': ''} | changes
        return {f'redemption-{key}': str(value) for key, value in data.items()}

    def test_derived_iof_is_visible_but_edit_and_delete_are_blocked(self, localdate):
        redemption = self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        item = redemption.iof_transaction
        response = self.client.get(reverse('transactions:list'))
        self.assertContains(response, 'IOF on reward redemption')
        self.assertContains(response, 'Managed by reward redemption')
        self.assertContains(response, 'USD 2,50')
        self.assertNotContains(response, reverse('transactions:update', args=[item.pk]))
        for endpoint, pk in [('transactions:update', item.pk), ('transactions:delete', item.pk),
                             ('banking:entry_update', redemption.loyalty_entry_id),
                             ('banking:entry_delete', redemption.loyalty_entry_id)]:
            for method in [self.client.get, self.client.post]:
                self.assertEqual(method(reverse(endpoint, args=[pk])).status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.amount, Decimal('2.50'))
        self.assertContains(self.client.get(reverse('transactions:export')), 'IOF on reward redemption')
        self.assertNotContains(self.client.get(reverse('transactions:list'), {'month': '2026-09'}), 'Managed by reward redemption')
        self.assertContains(self.client.get(reverse('transactions:list'), {'month': '2026-10'}), 'Managed by reward redemption')
        self.client.cookies['django_language'] = 'pt-br'
        self.assertContains(self.client.get(reverse('transactions:list'), {'q': 'resgate'}), 'IOF sobre resgate de pontos')
        del self.client.cookies['django_language']

    def test_inline_edit_keeps_bound_errors_and_original_points_available(self, localdate):
        redemption = self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        url = reverse('banking:redemption_update', args=[redemption.pk])
        response = self.client.get(url, follow=True)
        self.assertContains(response, 'id="id_redemption-iof_credit_card"')
        response = self.client.post(url, self.edit_data(points='1001', iof_amount='3.75'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The program does not have enough points.')
        self.assertEqual(response.context['redemption_form']['iof_credit_card'].value(), str(self.card.pk))
        redemption.refresh_from_db()
        self.assertEqual(redemption.iof_transaction.amount, Decimal('2.50'))
        self.assertEqual(self.program.balance, Decimal('900'))
        response = self.client.post(url, self.edit_data(points='1000', iof_amount='3.75'))
        self.assertEqual(response.status_code, 302)
        redemption.refresh_from_db()
        self.assertEqual(self.program.balance, Decimal('0'))
        self.assertEqual(redemption.iof_transaction.amount, Decimal('3.75'))
        self.assertEqual(CardInvoice.objects.get(card=self.card).amount, Decimal('3.75'))

    def test_source_transitions_remove_old_debits_and_keep_one_expense(self, localdate):
        redemption = self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        item_id = redemption.iof_transaction.pk
        url = reverse('banking:redemption_update', args=[redemption.pk])
        response = self.client.post(url, self.edit_data(iof_credit_card='', iof_account=self.funding.pk, iof_amount='4'))
        self.assertEqual(response.status_code, 302)
        redemption.refresh_from_db()
        self.assertEqual(redemption.iof_transaction.pk, item_id)
        self.assertEqual(redemption.iof_transaction.payment_channel, 'ACCOUNT')
        self.assertEqual(self.funding.current_balance(as_of=date(2026, 9, 25)), Decimal('96'))
        self.assertEqual(BankMovement.objects.filter(account=self.funding).count(), 1)
        self.assertFalse(CardInvoice.objects.exists())
        self.assertEqual(self.client.post(url, self.edit_data(iof_amount='5', date='2026-09-19')).status_code, 302)
        redemption.refresh_from_db()
        self.assertIsNone(redemption.iof_movement)
        self.assertEqual(redemption.iof_transaction.pk, item_id)
        self.assertEqual(CardInvoice.objects.get(card=self.card).reference_month, date(2026, 9, 1))
        self.assertEqual(self.funding.current_balance(as_of=date(2026, 9, 25)), Decimal('100'))
        self.assertEqual(self.client.post(url, self.edit_data(iof_amount='0', iof_credit_card='')).status_code, 302)
        self.assertFalse(Transaction.objects.exists())
        self.assertFalse(CardInvoice.objects.exists())
        self.assertFalse(BankMovement.objects.filter(account=self.funding).exists())

    def test_reports_and_sandbox_count_the_linked_expense_once(self, localdate):
        redemption = self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        ExchangeRate.objects.create(user=self.user, from_currency='USD', to_currency='BRL', rate='5', effective_date=date(2026, 9, 1))
        sync_user_ledger(self.user)
        summary = get_dashboard_summary(self.user, 2026, 10)
        self.assertEqual(summary['expense_month'], Decimal('12.50'))
        self.assertEqual(get_expenses_by_instrument(self.user, 2026, 10)['total'], Decimal('12.50'))
        rows = commitment_snapshot(self.user, date(2026, 9, 1))['rows']
        self.assertEqual([row['key'] for row in rows], [f'iof:{redemption.pk}'])
        self.assertEqual(rows[0]['native_amount'], '2.50')
        self.assertEqual(CardInvoice.objects.get(card=self.card).amount, Decimal('2.50'))

    def test_edit_program_and_destination_updates_existing_sources(self, localdate):
        redemption = self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        new_program = LoyaltyProgram.objects.create(user=self.user, name='New rewards')
        LoyaltyEntry.objects.create(user=self.user, program=new_program, direction='CREDIT', kind='ADJUSTMENT', amount='300', date=date(2026, 9, 1))
        ids = (redemption.loyalty_entry_id, redemption.reward_movement_id)
        update_reward_redemption(redemption=redemption, user=self.user, program=new_program,
                                 points=Decimal('150'), target_account=self.funding,
                                 target_amount=Decimal('30'), date=date(2026, 9, 22), iof_amount=Decimal('0'))
        redemption.refresh_from_db()
        self.assertEqual((redemption.loyalty_entry_id, redemption.reward_movement_id), ids)
        self.assertEqual((self.program.balance, new_program.balance), (Decimal('1000'), Decimal('150')))
        self.assertEqual(self.target.current_balance(as_of=date(2026, 9, 25)), Decimal('0'))
        self.assertEqual(self.funding.current_balance(as_of=date(2026, 9, 25)), Decimal('130'))

    def test_category_collision_and_legacy_sync_are_idempotent(self, localdate):
        Category.objects.create(user=self.user, name='IOF', transaction_type='INCOME')
        redemption = RewardRedemption.objects.create(user=self.user, program=self.program, points='100', target_account=self.target,
                                                     target_amount='25', date=date(2026, 9, 21), iof_amount='2.50', iof_credit_card=self.card)
        for _ in range(2):
            sync_user_ledger(self.user)
        item = Transaction.objects.get(reward_redemption=redemption)
        self.assertEqual(item.category.name, 'IOF (2)')
        self.assertEqual(item.category.transaction_type, 'EXPENSE')
        self.assertEqual(CardInvoice.objects.get(card=self.card).amount, Decimal('2.50'))
        self.assertEqual(Transaction.objects.count(), 1)

    def test_editing_is_scoped_to_the_source_owner(self, localdate):
        redemption = self.redeem(iof_amount=Decimal('2.50'), iof_credit_card=self.card)
        other = get_user_model().objects.create_user('foreign-redemption-editor')
        self.client.force_login(other)
        url = reverse('banking:redemption_update', args=[redemption.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.edit_data()).status_code, 404)
        self.client.force_login(self.user)
        unrelated = Bank.objects.create(user=self.user, name='Empty bank')
        self.assertEqual(self.client.get(reverse('banking:detail', args=[unrelated.pk]), {'edit_redemption': redemption.pk}).status_code, 404)
        self.assertEqual(self.client.get(reverse('banking:detail', args=[self.target.bank_id]), {'edit_redemption': 'invalid'}).status_code, 404)
