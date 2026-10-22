# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic financial confirmations: no installation data or live model calls."""
from datetime import date, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import uuid

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.utils.crypto import salted_hmac

from assistant import action_service
from assistant.action_service import ActionError, action_choices, cancel_action, confirm_action, prepare_action
from assistant.models import ActionProposal, Conversation, GenerationRun, Message
from assistant.tests.support import make_finances, make_owner
from banking.models import BankAccount, BankMovement, CardInvoice, CreditCard, DebitCard, LoyaltyProgram, RewardRedemption
from categories.models import Category
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation
from planning.services import save_budget
from transactions.models import Transaction, TransactionSplit
from transactions.projection import ProjectionLimitExceeded


class FinancialActionTests(TestCase):
    def setUp(self):
        self.user, self.other = make_owner('action-owner'), make_owner('action-other')
        self.bank, self.account, self.category, self.item = make_finances(self.user)
        self.private_bank, self.private_account, self.private_category, self.private_item = make_finances(self.other, 'Private')
        self.conversation = Conversation.objects.create(user=self.user)
        self.private_conversation = Conversation.objects.create(user=self.other)
        self.session = 'synthetic-session'
        self.credit = CreditCard.objects.create(user=self.user, account=self.account, name='Owned card',
            closing_day=20, due_day=1, manual_settlement_from=date(2026, 10, 1))
        self.debit = DebitCard.objects.create(user=self.user, account=self.account, name='Owned debit')

    def parameters(self, **changes):
        result = {'title': 'Reviewed purchase', 'amount': '25.40', 'currency': 'BRL',
                  'date': '2026-10-15', 'transaction_type': 'EXPENSE',
                  'account_id': self.account.pk, 'category_id': self.category.pk}
        result.update(changes)
        return result

    def proposal(self, name='transaction.create', parameters=None, **kwargs):
        return prepare_action(self.user, self.session, self.conversation, name,
                              self.parameters() if parameters is None else parameters, **kwargs)

    def counts(self):
        return {model.__name__: model.objects.count() for model in
                (Transaction, TransactionSplit, BankMovement, CardInvoice, FinancialGoal, GoalAllocation, CategoryBudget)}

    def assert_action_error(self, code, callback, *args, **kwargs):
        with self.assertRaises(ActionError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def generation(self, status='running', session=None):
        message = Message.objects.create(conversation=self.conversation, role='user', content='Synthetic request')
        session_digest = salted_hmac('assistant.chat.session.v1',
            f'{self.user.pk}:{self.session if session is None else session}', algorithm='sha256').hexdigest()
        return GenerationRun.objects.create(conversation=self.conversation, input_message=message,
            model_slug='synthetic-model', session_digest=session_digest, status=status)

    def test_prepare_only_records_the_review_and_never_synchronizes_finances(self):
        before = self.counts()
        with patch('assistant.action_service.sync_user_ledger') as sync:
            proposal = self.proposal()
        self.assertEqual(self.counts(), before)
        sync.assert_not_called()
        self.assertEqual(proposal.status, ActionProposal.Status.PENDING)
        self.assertEqual(proposal.parameters['amount'], '25.40')
        self.assertIn({'label': 'Amount', 'value': 'BRL 25.40'}, proposal.summary)
        self.assertEqual(proposal.result_url, '')
        self.assertTrue(timezone.now() < proposal.expires_at < timezone.now() + timedelta(minutes=31))

    def test_explicit_confirmation_creates_once_and_uses_the_canonical_ledger(self):
        proposal = self.proposal()
        before = Transaction.objects.count()
        result = confirm_action(self.user, self.session, proposal.pk)
        item = Transaction.objects.get(pk=result.result['object_id'])
        self.assertEqual(item.amount, Decimal('25.40'))
        self.assertEqual(item.user, self.user)
        self.assertEqual(item.payment_channel, 'ACCOUNT')
        self.assertTrue(BankMovement.objects.filter(user=self.user, source_key__startswith=f'transaction:{item.pk}:').exists())
        self.assertIn(str(item.pk), result.result_url)
        repeated = confirm_action(self.user, self.session, proposal.pk)
        self.assertEqual(repeated.result, result.result)
        self.assertEqual(Transaction.objects.count(), before + 1)

    def test_request_uuid_reuse_is_idempotent_but_conflicting_payload_is_refused(self):
        request_id = uuid.uuid4()
        original = self.proposal(request_id=request_id)
        self.assertEqual(self.proposal(request_id=request_id).pk, original.pk)
        self.assert_action_error('request_conflict', self.proposal,
            parameters=self.parameters(amount='25.41'), request_id=request_id)
        self.assert_action_error('request_conflict', prepare_action, self.user, 'another-session',
            self.conversation, 'transaction.create', self.parameters(), request_id=request_id)

    def test_confirmation_is_bound_to_the_owner_and_original_session(self):
        proposal = self.proposal()
        before = self.counts()
        for owner, session in [(self.other, self.session), (self.user, 'another-session')]:
            self.assert_action_error('not_found', confirm_action, owner, session, proposal.pk)
            self.assert_action_error('not_found', cancel_action, owner, session, proposal.pk)
        self.assertEqual(self.counts(), before)
        self.assert_action_error('not_found', prepare_action, self.user, self.session,
            self.private_conversation, 'transaction.create', self.parameters())

    def test_disabled_user_cannot_prepare_or_confirm_or_query(self):
        proposal = self.proposal()
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assert_action_error('unauthorized', confirm_action, self.user, self.session, proposal.pk)
        self.assert_action_error('unauthorized', self.proposal)
        self.assert_action_error('unauthorized', action_choices, self.user, 'accounts')

    def test_cancel_and_expiry_never_write_finances(self):
        proposal = self.proposal()
        before = self.counts()
        self.assertEqual(cancel_action(self.user, self.session, proposal.pk).status, 'cancelled')
        self.assertEqual(cancel_action(self.user, self.session, proposal.pk).status, 'cancelled')
        self.assert_action_error('proposal_unavailable', confirm_action, self.user, self.session, proposal.pk)
        expired = self.proposal()
        ActionProposal.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_action_error('proposal_expired', confirm_action, self.user, self.session, expired.pk)
        self.assertEqual(self.counts(), before)

    def test_running_failed_or_cancelled_generation_cannot_execute_a_proposal(self):
        run = self.generation()
        proposal = self.proposal(run_id=run.pk)
        before = self.counts()
        for status in ('running', 'failed', 'cancelled'):
            run.status = status
            run.save(update_fields=['status'])
            self.assert_action_error('generation_not_completed', confirm_action, self.user, self.session, proposal.pk)
        self.assertEqual(self.counts(), before)
        run.status = 'completed'
        run.save(update_fields=['status'])
        self.assertEqual(confirm_action(self.user, self.session, proposal.pk).status, 'executed')

    def test_generation_owner_session_and_deletion_never_create_orphan_authority(self):
        run = self.generation(session='foreign-session')
        self.assert_action_error('not_found', self.proposal, run_id=run.pk)
        run.delete()
        run = self.generation()
        proposal = self.proposal(run_id=run.pk)
        run.delete()
        self.assertFalse(ActionProposal.objects.filter(pk=proposal.pk).exists())

    def test_revalidation_refuses_foreign_deleted_or_changed_references(self):
        self.assert_action_error('invalid_reference', self.proposal,
            parameters=self.parameters(account_id=self.private_account.pk))
        self.assert_action_error('invalid_reference', self.proposal,
            parameters=self.parameters(category_id=self.private_category.pk))
        proposal = self.proposal()
        self.account.name = 'Changed since review'
        self.account.save(update_fields=['name', 'updated_at'])
        self.assert_action_error('proposal_changed', confirm_action, self.user, self.session, proposal.pk)
        proposal = self.proposal()
        # An unreferenced reviewed category can disappear before confirmation.
        temporary = Category.objects.create(user=self.user, name='Temporary')
        proposal = self.proposal(parameters=self.parameters(category_id=temporary.pk))
        temporary.delete()
        self.assert_action_error('invalid_reference', confirm_action, self.user, self.session, proposal.pk)

    def test_native_currency_is_never_reinterpreted_or_converted(self):
        self.assert_action_error('currency_mismatch', self.proposal,
            parameters=self.parameters(currency='USD'))
        proposal = self.proposal()
        self.account.currency = 'USD'
        self.account.save(update_fields=['currency', 'updated_at'])
        self.assert_action_error('currency_mismatch', confirm_action, self.user, self.session, proposal.pk)

    def test_foreign_bank_hidden_inside_an_owned_account_is_refused(self):
        malformed = BankAccount.objects.create(user=self.user, bank=self.private_bank,
            name='Invalid legacy ownership', currency='BRL')
        self.assert_action_error('invalid_reference', self.proposal,
            parameters=self.parameters(account_id=malformed.pk))
        labels = str(action_choices(self.user, 'accounts'))
        self.assertNotIn('Invalid legacy ownership', labels)
        self.assertNotIn('Private bank', labels)

    def test_canonical_form_rejects_category_type_date_pix_and_installment_mismatch(self):
        income = Category.objects.create(user=self.user, name='Income category', transaction_type='INCOME')
        for changes in ({'category_id': income.pk}, {'date': '2026-09-01'},
                        {'installments': 2}, {'billing_override': 0}, {'fixed_until': '2026-11-01'}):
            with self.subTest(changes=changes):
                self.assert_action_error('validation_failed', self.proposal, parameters=self.parameters(**changes))
        self.account.pix_enabled = False
        self.account.save(update_fields=['pix_enabled'])
        self.assert_action_error('validation_failed', self.proposal,
            parameters=self.parameters(payment_channel='PIX'))

    def test_card_payment_uses_owned_card_currency_and_preserves_invoice_accounting(self):
        proposal = self.proposal(parameters=self.parameters(account_id=None,
            payment_channel='CREDIT_CARD', credit_card_id=self.credit.pk, installments=3,
            billing_override=1, notes='Reviewed notes'))
        summary = str(proposal.summary)
        self.assertIn('Owned card', summary)
        self.assertIn('Installments', summary)
        self.assertIn('Confirmed payments', summary)
        result = confirm_action(self.user, self.session, proposal.pk)
        item = Transaction.objects.get(pk=result.result['object_id'])
        self.assertEqual(item.credit_card, self.credit)
        self.assertIsNone(item.bank_account_id)
        self.assertEqual(item.installments, 3)
        self.assertEqual(item.notes, 'Reviewed notes')
        self.assertFalse(BankMovement.objects.filter(source_key__startswith=f'transaction:{item.pk}:').exists())
        self.assertTrue(CardInvoice.objects.filter(card=self.credit).exists())

    def test_card_cannot_silently_use_another_account_or_receive_income(self):
        self.assert_action_error('invalid_reference', self.proposal,
            parameters=self.parameters(account_id=self.private_account.pk,
                payment_channel='CREDIT_CARD', credit_card_id=self.credit.pk))
        self.assert_action_error('validation_failed', self.proposal,
            parameters=self.parameters(account_id=None, transaction_type='INCOME',
                payment_channel='DEBIT_CARD', debit_card_id=self.debit.pk))

    def test_pix_and_fixed_schedule_keep_native_options_and_precision(self):
        proposal = self.proposal(parameters=self.parameters(payment_channel='PIX',
            amount='0.01', is_fixed=True, fixed_until='2026-12-15'))
        result = confirm_action(self.user, self.session, proposal.pk)
        item = Transaction.objects.get(pk=result.result['object_id'])
        self.assertEqual(item.amount, Decimal('0.01'))
        self.assertTrue(item.is_fixed)
        self.assertEqual(item.payment_channel, 'PIX')
        self.assertEqual(item.fixed_until, date(2026, 12, 15))

    def test_projection_failure_rolls_back_source_and_proposal_claim(self):
        proposal = self.proposal()
        before = self.counts()
        with patch('assistant.action_service.sync_user_ledger', side_effect=ProjectionLimitExceeded()):
            with self.assertRaises(ActionError):
                confirm_action(self.user, self.session, proposal.pk)
        self.assertEqual(self.counts(), before)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, 'pending')
        self.assertEqual(proposal.result, {})

    def test_categorization_preserves_all_other_source_fields_and_rejects_concurrent_edit(self):
        category = Category.objects.create(user=self.user, name='Reviewed category', transaction_type='EXPENSE')
        Transaction.objects.filter(pk=self.item.pk).update(title='  Legacy purchase  ', notes='  preserved note  ')
        self.item.refresh_from_db()
        proposal = self.proposal('transaction.categorize', {'transaction_id': self.item.pk, 'category_id': category.pk})
        before = {field.attname: getattr(self.item, field.attname) for field in self.item._meta.concrete_fields
                  if field.name not in {'category', 'updated_at'}}
        result = confirm_action(self.user, self.session, proposal.pk)
        self.assertEqual(result.result['object_id'], self.item.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.category, category)
        for field, value in before.items():
            self.assertEqual(getattr(self.item, field), value)
        next_proposal = self.proposal('transaction.categorize', {'transaction_id': self.item.pk, 'category_id': self.category.pk})
        self.item.notes = 'Concurrent user edit'
        self.item.save(update_fields=['notes', 'updated_at'])
        self.assert_action_error('proposal_changed', confirm_action, self.user, self.session, next_proposal.pk)

    def test_split_transaction_requires_the_full_editor_and_is_not_a_lookup_choice(self):
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount=self.item.amount)
        self.assert_action_error('split_requires_form', self.proposal, 'transaction.categorize',
            {'transaction_id': self.item.pk, 'category_id': self.category.pk})
        self.assertEqual(action_choices(self.user, 'transactions', 'purchase')['items'], [])

    def test_generated_reward_redemption_expense_keeps_its_edit_lock(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Owned program', bank=self.bank)
        redemption = RewardRedemption.objects.create(user=self.user, program=program,
            points='10.00', target_account=self.account, target_amount='1.00', date=date(2026, 10, 10))
        self.item.reward_redemption = redemption
        self.item.save(update_fields=['reward_redemption'])
        before = self.counts()
        self.assert_action_error('invalid_reference', self.proposal, 'transaction.categorize',
            {'transaction_id': self.item.pk, 'category_id': self.category.pk})
        self.assertEqual(action_choices(self.user, 'transactions', 'purchase')['items'], [])
        self.assertEqual(self.counts(), before)

    def test_foreign_card_and_cross_owner_card_account_are_refused_without_label_leaks(self):
        card = CreditCard.objects.create(user=self.other, account=self.private_account,
            name='Private card', closing_day=10, due_day=20)
        self.assert_action_error('invalid_reference', self.proposal,
            parameters=self.parameters(account_id=None, payment_channel='CREDIT_CARD', credit_card_id=card.pk))
        malformed = CreditCard.objects.create(user=self.user, account=self.private_account,
            name='Invalid legacy card', closing_day=10, due_day=20)
        self.assert_action_error('invalid_reference', self.proposal,
            parameters=self.parameters(account_id=None, payment_channel='CREDIT_CARD', credit_card_id=malformed.pk))
        choices = str(action_choices(self.user, 'credit_cards'))
        self.assertNotIn('Private card', choices)
        self.assertNotIn('Invalid legacy card', choices)

    def test_an_injected_category_split_after_review_blocks_categorization(self):
        proposal = self.proposal('transaction.categorize',
            {'transaction_id': self.item.pk, 'category_id': self.category.pk})
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount=self.item.amount)
        self.assert_action_error('split_requires_form', confirm_action, self.user, self.session, proposal.pk)
        self.assertEqual(TransactionSplit.objects.get(transaction=self.item).amount, self.item.amount)

    def test_create_goal_has_no_implicit_reservation_or_new_cash(self):
        before = self.counts()
        proposal = self.proposal('goal.create', {'name': 'Reviewable reserve', 'target_amount': '500.25',
            'currency': 'USD', 'target_date': None})
        self.assertEqual(self.counts(), before)
        result = confirm_action(self.user, self.session, proposal.pk)
        goal = FinancialGoal.objects.get(pk=result.result['object_id'])
        self.assertEqual(goal.target_amount, Decimal('500.25'))
        self.assertEqual(goal.currency, 'USD')
        self.assertIsNone(goal.target_date)
        self.assertEqual(GoalAllocation.objects.count(), 0)
        self.assertEqual(BankMovement.objects.count(), before['BankMovement'])

    def test_budget_uses_canonical_overlap_check_during_preview_and_confirmation(self):
        parameters = {'category_id': self.category.pk, 'month': '2026-10', 'currency': 'BRL', 'amount': '150.00'}
        proposal = self.proposal('budget.create', parameters)
        child = Category.objects.create(user=self.user, name='Child', parent_category=self.category)
        save_budget(CategoryBudget(user=self.user, category=child, month=date(2026, 10, 1), currency='BRL', amount='1.00'))
        self.assert_action_error('validation_failed', confirm_action, self.user, self.session, proposal.pk)
        self.assertEqual(CategoryBudget.objects.count(), 1)
        self.assert_action_error('validation_failed', self.proposal, 'budget.create', parameters)

    def test_budget_confirmation_stores_the_first_day_without_financial_movements(self):
        before = self.counts()
        proposal = self.proposal('budget.create', {'category_id': self.category.pk,
            'month': '2026-11', 'currency': 'BRL', 'amount': '99.99'})
        result = confirm_action(self.user, self.session, proposal.pk)
        budget = CategoryBudget.objects.get(pk=result.result['object_id'])
        self.assertEqual(budget.month, date(2026, 11, 1))
        self.assertEqual(budget.amount, Decimal('99.99'))
        self.assertEqual(BankMovement.objects.count(), before['BankMovement'])

    def test_strict_values_forbid_float_exponent_extra_fields_and_other_actions(self):
        for changes in ({'amount': 1.23}, {'amount': '1e-999999999'}, {'amount': '-1.00'},
                        {'amount': '1.001'}, {'account_id': True}, {'notes': 'x' * 2001},
                        {'payment_channel': 'TRANSFER'}, {'installments': True},
                        {'is_fixed': 'false'}, {'billing_override': False},
                        {'date': '15/10/2026'}, {'date': '2026-02-30'}, {'split_categories': True}):
            with self.subTest(changes=changes):
                self.assert_action_error('invalid_parameters', self.proposal, parameters=self.parameters(**changes))
        for action in ('transaction.archive', 'bank.transfer', 'invoice.pay', 'alert.propose'):
            self.assert_action_error('unsupported_action', self.proposal, action, {})

    def test_lookups_are_owned_bounded_and_do_not_return_balances_or_notes(self):
        for index in range(25):
            Category.objects.create(user=self.user, name=f'Choice {index:02}')
        result = action_choices(self.user, 'categories')
        self.assertEqual(len(result['items']), 20)
        self.assertTrue(result['has_more'])
        self.assertNotIn('Private', str(result))
        account = action_choices(self.user, 'accounts')['items'][0]
        self.assertEqual(set(account), {'id', 'label', 'currency', 'pix_enabled'})
        card = action_choices(self.user, 'credit_cards')['items'][0]
        self.assertEqual(card['account_id'], self.account.pk)
        self.assertNotIn('opening_balance', str(account))
        self.assert_action_error('query_required', action_choices, self.user, 'transactions')
        transactions = action_choices(self.user, 'transactions', 'purchase')
        self.assertEqual([row['id'] for row in transactions['items']], [self.item.pk])
        self.assertNotIn('PRIVATE NOTES', str(transactions))
        self.assert_action_error('unsupported_choice', action_choices, self.user, 'all_history')

    def test_lookup_category_type_compatibility_is_not_inferred_from_labels(self):
        income = Category.objects.create(user=self.user, name='Salary', transaction_type='INCOME')
        result = action_choices(self.user, 'categories', transaction_type='EXPENSE')
        self.assertNotIn(income.pk, [row['id'] for row in result['items']])
        self.assertIn(self.category.pk, [row['id'] for row in result['items']])


class ConcurrentConfirmationTests(TransactionTestCase):
    def test_parallel_confirmations_never_duplicate_a_financial_write(self):
        user = make_owner('concurrent-action-owner')
        _bank, account, category, _item = make_finances(user)
        conversation = Conversation.objects.create(user=user)
        proposal = prepare_action(user, 'same-session', conversation, 'transaction.create', {
            'title': 'Concurrent review', 'amount': '1.23', 'currency': 'BRL', 'date': '2026-10-15',
            'transaction_type': 'EXPENSE', 'account_id': account.pk, 'category_id': category.pk})
        barrier = Barrier(2, timeout=10)
        original_lookup = action_service._owned_proposal

        def ready(*args):
            result = original_lookup(*args)
            barrier.wait()
            return result

        def confirm():
            close_old_connections()
            try:
                return confirm_action(user, 'same-session', proposal.pk).status
            except ActionError as error:
                return error.code
            finally:
                close_old_connections()

        with patch('assistant.action_service._owned_proposal', side_effect=ready), ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(confirm), pool.submit(confirm)
            results = [first.result(timeout=15), second.result(timeout=15)]
        self.assertIn('executed', results)
        self.assertTrue(all(result in {'executed', 'proposal_unavailable', 'storage_unavailable'} for result in results))
        self.assertEqual(Transaction.objects.filter(user=user, title='Concurrent review').count(), 1)
        self.assertEqual(confirm_action(user, 'same-session', proposal.pk).status, 'executed')
        self.assertEqual(Transaction.objects.filter(user=user, title='Concurrent review').count(), 1)
