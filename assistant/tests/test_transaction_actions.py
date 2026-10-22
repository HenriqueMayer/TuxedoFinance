# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic source-transaction edits/deletions require reviewed confirmation."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import uuid

from django.forms.models import model_to_dict
from django.test import TestCase
from django.urls import reverse

from assistant.action_service import ActionError, confirm_action, normalize_parameters, prepare_action
from assistant.models import ActionProposal, Conversation
from assistant.tests.support import make_finances, make_owner
from banking.models import BankAccount, BankMovement, CardInvoice, CreditCard, LoyaltyProgram, RewardRedemption
from categories.models import Category
from transactions.models import Transaction, TransactionSplit
from transactions.projection import ProjectionLimitExceeded
from transactions.services import sync_user_ledger


class TransactionMutationActionTests(TestCase):
    def setUp(self):
        self.user, self.other = make_owner('mutation-owner'), make_owner('mutation-other')
        self.bank, self.account, self.category, self.item = make_finances(self.user)
        _private_bank, self.private_account, self.private_category, self.private_item = make_finances(self.other, 'Private')
        self.conversation = Conversation.objects.create(user=self.user)
        self.session = 'synthetic-mutation-session'
        self.credit = CreditCard.objects.create(user=self.user, account=self.account, name='Reviewed card',
            closing_day=20, due_day=1, manual_settlement_from=date(2026, 10, 1))

    def propose(self, name='transaction.update', changes=None, transaction_id=None, **kwargs):
        parameters = {'transaction_id': transaction_id or self.item.pk}
        if name == 'transaction.update':
            parameters['changes'] = {'title': 'Reviewed edited title'} if changes is None else changes
        return prepare_action(self.user, self.session, self.conversation, name, parameters, **kwargs)

    def assert_error(self, code, callback, *args, **kwargs):
        with self.assertRaises(ActionError) as error:
            callback(*args, **kwargs)
        self.assertEqual(error.exception.code, code)

    def test_partial_update_preserves_omission_in_the_reviewed_parameters(self):
        normalized = normalize_parameters('transaction.update', {
            'transaction_id': self.item.pk, 'changes': {'amount': '10.2'}})
        self.assertEqual(normalized, {'transaction_id': self.item.pk, 'changes': {'amount': '10.20'}})
        self.assertEqual(normalize_parameters('transaction.delete', {'transaction_id': self.item.pk}),
                         {'transaction_id': self.item.pk})

    def test_update_preview_and_confirmation_reuse_native_form_without_resetting_unrequested_fields(self):
        self.item.notes = '  Existing whitespace stays unchanged  '
        self.item.installments = 1
        self.item.save(update_fields=['notes', 'installments'])
        before = model_to_dict(self.item)
        with patch('assistant.action_service.sync_user_ledger') as sync:
            proposal = self.propose()
        sync.assert_not_called()
        self.item.refresh_from_db()
        self.assertEqual(model_to_dict(self.item), before)
        self.assertEqual(proposal.parameters['changes'], {'title': 'Reviewed edited title'})
        summary = str(proposal.summary)
        self.assertIn('Title · before', summary)
        self.assertIn('Title · after', summary)
        self.assertNotIn('Existing whitespace', summary)
        result = confirm_action(self.user, self.session, proposal.pk)
        self.assertEqual(result.result['object_id'], self.item.pk)
        self.item.refresh_from_db()
        for field, value in before.items():
            self.assertEqual(getattr(self.item, field if field != 'category' else 'category_id')
                             if field not in {'user', 'bank_account', 'debit_card', 'credit_card', 'reward_redemption'}
                             else getattr(self.item, field + '_id'),
                             'Reviewed edited title' if field == 'title' else value)
        self.assertEqual(self.item.notes, '  Existing whitespace stays unchanged  ')

    def test_update_only_notes_does_not_trim_the_saved_title(self):
        self.item.title = '  Legacy title with intentional spaces  '
        self.item.save(update_fields=['title'])
        proposal = self.propose(changes={'notes': 'New reviewed note'})
        confirm_action(self.user, self.session, proposal.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, '  Legacy title with intentional spaces  ')
        self.assertEqual(self.item.notes, 'New reviewed note')

    def test_explicit_optional_clears_are_not_confused_with_omitted_values(self):
        self.item.is_fixed = True
        self.item.fixed_until = date(2026, 12, 10)
        self.item.notes = 'To clear deliberately'
        self.item.save(update_fields=['is_fixed', 'fixed_until', 'notes'])
        proposal = self.propose(changes={'notes': '', 'fixed_until': None})
        confirm_action(self.user, self.session, proposal.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, '')
        self.assertIsNone(self.item.fixed_until)
        self.assertTrue(self.item.is_fixed)

    def test_amount_update_keeps_exact_native_cents_and_reconciles_existing_ledger_identity(self):
        sync_user_ledger(self.user)
        movement = BankMovement.objects.get(source_key__startswith=f'transaction:{self.item.pk}:')
        proposal = self.propose(changes={'amount': '0.01'})
        before_count = Transaction.objects.count()
        result = confirm_action(self.user, self.session, proposal.pk)
        movement.refresh_from_db()
        self.assertEqual(movement.amount, Decimal('0.01'))
        self.assertEqual(Transaction.objects.get(pk=self.item.pk).amount, Decimal('0.01'))
        self.assertEqual(confirm_action(self.user, self.session, proposal.pk).result, result.result)
        self.assertEqual(Transaction.objects.count(), before_count)

    def test_update_reference_ownership_and_category_type_are_rechecked(self):
        self.assert_error('invalid_reference', self.propose, transaction_id=self.private_item.pk)
        self.assert_error('invalid_reference', self.propose, changes={'category_id': self.private_category.pk})
        self.assert_error('invalid_reference', self.propose, changes={'account_id': self.private_account.pk})
        income = Category.objects.create(user=self.user, name='Income only', transaction_type='INCOME')
        self.assert_error('validation_failed', self.propose, changes={'category_id': income.pk})
        self.assert_error('validation_failed', self.propose, changes={'date': '2026-09-01'})

    def test_channel_switch_requires_deliberate_clear_and_never_reuses_an_incompatible_instrument(self):
        self.assert_error('invalid_parameters', self.propose,
            changes={'payment_channel': 'CREDIT_CARD', 'credit_card_id': self.credit.pk})
        proposal = self.propose(changes={'payment_channel': 'CREDIT_CARD', 'credit_card_id': self.credit.pk,
            'account_id': None, 'installments': 2, 'billing_override': 1})
        summary = str(proposal.summary)
        self.assertIn('Payment instrument · before', summary)
        self.assertIn('Payment instrument · after', summary)
        self.assertIn('Reviewed card', summary)
        confirm_action(self.user, self.session, proposal.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.credit_card, self.credit)
        self.assertIsNone(self.item.bank_account_id)
        self.assertEqual(self.item.installments, 2)
        self.assertFalse(BankMovement.objects.filter(source_key__startswith=f'transaction:{self.item.pk}:').exists())
        self.assertTrue(CardInvoice.objects.filter(card=self.credit).exists())
        self.assert_error('validation_failed', self.propose,
            changes={'payment_channel': 'ACCOUNT', 'account_id': self.account.pk})

    def test_different_currency_account_requires_explicit_native_currency_acknowledgement(self):
        usd = BankAccount.objects.create(user=self.user, bank=self.bank, name='USD account', currency='USD',
            opening_date=date(2026, 10, 1))
        self.assert_error('currency_confirmation_required', self.propose, changes={'account_id': usd.pk})
        self.assert_error('currency_mismatch', self.propose, changes={'account_id': usd.pk, 'currency': 'BRL'})
        proposal = self.propose(changes={'account_id': usd.pk, 'currency': 'USD', 'amount': '14.25'})
        self.assertIn('BRL 12.34', str(proposal.summary))
        self.assertIn('USD 14.25', str(proposal.summary))
        confirm_action(self.user, self.session, proposal.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.native_currency, 'USD')
        self.assertEqual(self.item.amount, Decimal('14.25'))

    def test_update_and_delete_refuse_generated_or_split_sources(self):
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount=self.item.amount)
        for name in ('transaction.update', 'transaction.delete'):
            self.assert_error('split_requires_form', self.propose, name)
        self.item.splits.all().delete()
        program = LoyaltyProgram.objects.create(user=self.user, name='Generated lock')
        redemption = RewardRedemption.objects.create(user=self.user, program=program, points='1.00',
            target_account=self.account, target_amount='1.00', date=date(2026, 10, 10))
        self.item.reward_redemption = redemption
        self.item.save(update_fields=['reward_redemption'])
        for name in ('transaction.update', 'transaction.delete'):
            self.assert_error('invalid_reference', self.propose, name)

    def test_changed_record_or_late_split_prevents_update_and_delete(self):
        update = self.propose()
        delete = self.propose('transaction.delete')
        self.item.notes = 'A later edit changes the reviewed record'
        self.item.save(update_fields=['notes', 'updated_at'])
        for proposal in (update, delete):
            self.assert_error('proposal_changed', confirm_action, self.user, self.session, proposal.pk)
        update = self.propose()
        delete = self.propose('transaction.delete')
        TransactionSplit.objects.create(transaction=self.item, category=self.category, amount=self.item.amount)
        for proposal in (update, delete):
            self.assert_error('split_requires_form', confirm_action, self.user, self.session, proposal.pk)

    def test_noop_or_invalid_partial_fields_cannot_be_interpreted_as_a_different_operation(self):
        self.assert_error('no_changes', self.propose, changes={'title': self.item.title})
        self.assert_error('no_changes', self.propose, changes={'currency': 'BRL'})
        for changes in ({}, {'user_id': self.other.pk}, {'amount': 1.23}, {'notes': None},
                        {'is_fixed': None}, {'category_id': None}, {'delete': True}, {'amount': '1e-2'}):
            self.assert_error('invalid_parameters', self.propose, changes=changes)
        self.assert_error('invalid_parameters', normalize_parameters, 'transaction.update',
            {'transaction_id': self.item.pk, 'changes': {'title': 'Reviewed'}, 'title': 'Unexpected'})
        self.assert_error('invalid_parameters', normalize_parameters, 'transaction.delete',
            {'transaction_id': self.item.pk, 'cascade': True})

    def test_large_unchanged_legacy_notes_stay_private_and_intact(self):
        self.item.notes = 'PRIVATE LEGACY NOTE ' * 200
        self.item.save(update_fields=['notes'])
        proposal = self.propose()
        deletion = self.propose('transaction.delete')
        self.assertNotIn('PRIVATE LEGACY NOTE', str(proposal.summary))
        self.assertNotIn('PRIVATE LEGACY NOTE', str(deletion.summary))
        self.assert_error('long_notes_require_form', self.propose, changes={'notes': 'Replace'})
        confirm_action(self.user, self.session, proposal.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, 'PRIVATE LEGACY NOTE ' * 200)

    def test_delete_preview_is_read_only_and_names_the_complete_source_scope(self):
        sync_user_ledger(self.user)
        before = (Transaction.objects.count(), BankMovement.objects.count())
        with patch('assistant.action_service.sync_user_ledger') as sync:
            proposal = self.propose('transaction.delete')
        sync.assert_not_called()
        self.assertEqual((Transaction.objects.count(), BankMovement.objects.count()), before)
        summary = str(proposal.summary)
        self.assertIn('Delete transaction', summary)
        self.assertIn(self.item.title, summary)
        self.assertIn('BRL 12.34', summary)
        self.assertIn('all of its scheduled occurrences', summary)

    def test_delete_confirmation_removes_only_the_owned_source_and_reconciles_its_movement(self):
        sync_user_ledger(self.user)
        proposal = self.propose('transaction.delete')
        source_id = self.item.pk
        result = confirm_action(self.user, self.session, proposal.pk)
        self.assertFalse(Transaction.objects.filter(pk=source_id).exists())
        self.assertTrue(Transaction.objects.filter(pk=self.private_item.pk).exists())
        self.assertFalse(BankMovement.objects.filter(source_key__startswith=f'transaction:{source_id}:').exists())
        self.assertEqual(result.result, {'object_id': source_id, 'url': reverse('transactions:list'), 'operation': 'deleted'})
        self.assertEqual(confirm_action(self.user, self.session, proposal.pk).result, result.result)

    def test_foreign_source_session_and_owner_cannot_delete_or_update(self):
        self.assert_error('invalid_reference', self.propose, 'transaction.delete', transaction_id=self.private_item.pk)
        for name in ('transaction.update', 'transaction.delete'):
            proposal = self.propose(name)
            self.assert_error('not_found', confirm_action, self.other, self.session, proposal.pk)
            self.assert_error('not_found', confirm_action, self.user, 'another-session', proposal.pk)
        self.assertTrue(Transaction.objects.filter(pk=self.item.pk).exists())

    def test_changed_or_missing_source_cannot_be_silently_recreated(self):
        proposal = self.propose()
        self.item.delete()
        self.assert_error('invalid_reference', confirm_action, self.user, self.session, proposal.pk)
        self.assertFalse(Transaction.objects.filter(title='Reviewed edited title').exists())

    def test_failed_ledger_sync_rolls_back_both_update_and_delete_with_pending_review(self):
        for name in ('transaction.update', 'transaction.delete'):
            proposal = self.propose(name)
            original_title = self.item.title
            with patch('assistant.action_service.sync_user_ledger', side_effect=ProjectionLimitExceeded()):
                self.assert_error('projection_limit', confirm_action, self.user, self.session, proposal.pk)
            self.item.refresh_from_db()
            self.assertEqual(self.item.title, original_title)
            proposal.refresh_from_db()
            self.assertEqual(proposal.status, 'pending')
            self.assertEqual(proposal.result, {})

    def test_legacy_excessive_recurrence_can_be_removed_while_another_source_still_blocks_sync(self):
        Transaction.objects.filter(pk=self.item.pk).update(date=date(1901, 1, 1), is_fixed=True)
        self.item.refresh_from_db()
        other_source = Transaction.objects.create(user=self.user, title='Other excessive source', amount='1.00',
            transaction_type='EXPENSE', category=self.category, payment_channel='ACCOUNT', bank_account=self.account,
            date=date(1901, 1, 1), is_fixed=True)
        proposal = self.propose('transaction.delete')
        result = confirm_action(self.user, self.session, proposal.pk)
        self.assertFalse(Transaction.objects.filter(pk=self.item.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=other_source.pk).exists())
        self.assertEqual(result.result['warnings'], ['projection_pending'])

    def test_legacy_excessive_recurrence_can_be_explicitly_repaired_without_changing_other_fields(self):
        Transaction.objects.filter(pk=self.item.pk).update(date=date(1901, 1, 1), is_fixed=True)
        self.item.refresh_from_db()
        other_source = Transaction.objects.create(user=self.user, title='Other excessive source', amount='1.00',
            transaction_type='EXPENSE', category=self.category, payment_channel='ACCOUNT', bank_account=self.account,
            date=date(1901, 1, 1), is_fixed=True)
        proposal = self.propose(changes={'date': '2026-10-15', 'fixed_until': '2026-12-15'})
        result = confirm_action(self.user, self.session, proposal.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.date, date(2026, 10, 15))
        self.assertEqual(self.item.fixed_until, date(2026, 12, 15))
        self.assertTrue(self.item.is_fixed)
        self.assertTrue(Transaction.objects.filter(pk=other_source.pk).exists())
        self.assertEqual(result.result['warnings'], ['projection_pending'])

    def test_update_request_identity_normalizes_values_without_inserting_unrequested_defaults(self):
        request_id = uuid.uuid4()
        first = self.propose(changes={'amount': '10.2'}, request_id=request_id)
        second = self.propose(changes={'amount': '10.20'}, request_id=request_id)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ActionProposal.objects.filter(request_id=request_id).count(), 1)
        self.assertEqual(first.parameters['changes'], {'amount': '10.20'})
