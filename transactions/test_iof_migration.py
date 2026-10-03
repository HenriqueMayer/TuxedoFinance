# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from datetime import date
from decimal import Decimal
from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RedemptionIOFMigrationTests(TransactionTestCase):
    def test_upgrade_backfills_existing_iof_without_reposting_cash(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('transactions', '0001_initial'), ('banking', '0007_bank_color'),
                  ('categories', '0002_category_transaction_type')]
        try:
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            User = old.get_model('auth', 'User')
            Bank = old.get_model('banking', 'Bank')
            Account = old.get_model('banking', 'BankAccount')
            Card = old.get_model('banking', 'CreditCard')
            Program = old.get_model('banking', 'LoyaltyProgram')
            Redemption = old.get_model('banking', 'RewardRedemption')
            Movement = old.get_model('banking', 'BankMovement')
            Category = old.get_model('categories', 'Category')
            user = User.objects.create(username='legacy-iof')
            bank = Bank.objects.create(user=user, name='Legacy bank')
            account = Account.objects.create(user=user, bank=bank, name='Legacy account', currency='BRL')
            card = Card.objects.create(user=user, account=account, name='Legacy card', closing_day=20, due_day=1)
            program = Program.objects.create(user=user, name='Legacy rewards')
            Category.objects.create(user=user, name='IOF', transaction_type='INCOME')
            movement = Movement.objects.create(user=user, account=account, amount='3', direction='DEBIT',
                                               kind='EXPENSE', effective_date=date(2026, 10, 3), source_key='reward-redemption:legacy:iof')
            common = {'user': user, 'program': program, 'points': '2500', 'target_account': account,
                      'target_amount': '11.47', 'date': date(2026, 10, 3)}
            card_source = Redemption.objects.create(**common, iof_amount='2', iof_credit_card=card)
            account_source = Redemption.objects.create(**common, iof_amount='3', iof_account=account, iof_movement=movement)
            Redemption.objects.create(**common, iof_amount='0')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            current = executor.loader.project_state(latest).apps
            Transaction = current.get_model('transactions', 'Transaction')
            self.assertEqual(Transaction.objects.count(), 2)
            item = Transaction.objects.get(reward_redemption_id=card_source.pk)
            self.assertEqual((item.amount, item.credit_card_id, item.payment_channel), (Decimal('2'), card.pk, 'CREDIT_CARD'))
            self.assertEqual(item.category.name, 'IOF (2)')
            self.assertEqual(Transaction.objects.get(reward_redemption_id=account_source.pk).bank_account_id, account.pk)
            self.assertEqual(current.get_model('banking', 'BankMovement').objects.count(), 1)
            migration = import_module('transactions.migrations.0002_transaction_reward_redemption_and_more')
            with connection.schema_editor() as editor:
                migration.backfill_iof_transactions(current, editor)
            self.assertEqual(Transaction.objects.count(), 2)
        finally:
            MigrationExecutor(connection).migrate(latest)
