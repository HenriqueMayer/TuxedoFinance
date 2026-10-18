"""Commitments coverage for sandbox."""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from sandbox.models import ScenarioDraft


D = Decimal


User = get_user_model()


class CommitmentProjectionTests(TestCase):
    def setUp(self):
        from datetime import date
        from banking.models import Bank, BankAccount, CreditCard
        from categories.models import Category
        from transactions.models import Transaction
        self.user = User.objects.create_user('commitments', password='test')
        self.client.force_login(self.user)
        self.bank = Bank.objects.create(user=self.user, name='Bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Checking', currency='BRL')
        self.card = CreditCard.objects.create(user=self.user, account=self.account, name='Card', closing_day=24, due_day=1)
        self.category = Category.objects.filter(user=self.user).first()
        self.purchase = Transaction.objects.create(user=self.user, title='Three payments', amount=D('100'),
            transaction_type='EXPENSE', category=self.category, payment_channel='CREDIT_CARD',
            credit_card=self.card, installments=3, date=date(2026, 8, 25))

    def test_payment_month_remainders_card_costs_and_no_invoice_duplication_or_writes(self):
        from datetime import date
        from banking.models import CardInvoice, LoyaltyEntry, LoyaltyProgram
        from sandbox.planning import commitment_snapshot
        CardInvoice.objects.create(user=self.user, card=self.card, reference_month=date(2026, 9, 1), due_date=date(2026, 10, 1), amount=999)
        program = LoyaltyProgram.objects.create(user=self.user, name='Miles', unit_name='points')
        LoyaltyEntry.objects.create(user=self.user, program=program, direction='CREDIT', kind='PURCHASE', amount=100,
            cash_amount=50, funding_credit_card=self.card, date=date(2026, 9, 5))
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        installments = [row for row in snapshot['rows'] if row['kind'] == 'installment']
        self.assertEqual([row['amount'] for row in installments], ['33.34', '33.33', '33.33'])
        self.assertEqual([row['payment_date'] for row in installments], ['2026-10-01', '2026-11-01', '2026-12-01'])
        self.assertEqual(len(snapshot['rows']), 4)
        self.assertEqual(sum(D(row['amount']) for row in snapshot['rows']), D('150'))
        self.assertEqual(self.user.bank_movements.count(), 0)
        self.assertEqual(CardInvoice.objects.get().amount, D('999'))

        reference_snapshot = commitment_snapshot(
            self.user, date(2026, 9, 1), month_basis='reference_month',
        )
        from sandbox.planning import snapshot_total
        self.assertEqual(snapshot_total(reference_snapshot, '2026-09'), D('83.34'))
        self.assertEqual(snapshot_total(reference_snapshot, '2026-10'), D('33.33'))
        self.assertEqual(snapshot_total(reference_snapshot, '2026-11'), D('33.33'))
        self.assertEqual(snapshot_total(reference_snapshot, '2026-12'), D('0'))

    def test_reference_month_matches_report_across_card_due_months(self):
        from datetime import date
        from dashboard.services import get_instrument_activity
        from transactions.models import Transaction
        self.purchase.delete()
        for title, amount, month, card in [
            ('September Black', '3732.71', 9, True),
            ('September Roxinho', '613.84', 9, True),
            ('September Visa', '499.36', 9, True),
            ('September account', '75', 9, False),
            ('October Black', '1275.30', 10, True),
            ('October Roxinho', '613.84', 10, True),
        ]:
            Transaction.objects.create(
                user=self.user, title=title, amount=D(amount), transaction_type='EXPENSE',
                category=self.category, payment_channel='CREDIT_CARD' if card else 'ACCOUNT',
                credit_card=self.card if card else None, bank_account=None if card else self.account,
                date=date(2026, month, 5),
            )
        for month, expected, count in [(9, '4920.91', 4), (10, '1889.14', 2), (11, '0', 0)]:
            with self.subTest(month=month):
                response = self.client.post(reverse('sandbox:index'), {
                    'action': 'forecast', 'planning_month': f'2026-{month:02}',
                })
                forecast = response.context['forecast']
                self.assertEqual(forecast['total'], D(expected))
                self.assertEqual(forecast['count'], count)
                report = get_instrument_activity(self.user, 2026, month)
                self.assertEqual(forecast['total'], report['expense_total'])

    def test_legacy_saved_snapshot_keeps_payment_basis(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot
        self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'Legacy', 'planning_month': '2026-10',
            'gross_salary': '5000',
        })
        draft = ScenarioDraft.objects.get()
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        snapshot.pop('month_basis')
        draft.payload['calculation_version'] = 1
        draft.payload['snapshot'] = snapshot
        draft.save()
        opened = self.client.get(reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertEqual(opened.context['forecast']['total'], D('33.34'))
        compared = self.client.get(reverse('sandbox:compare'), {'draft': draft.pk})
        self.assertEqual(compared.context['scenarios'][0]['result']['budget'].fixed_bills, D('33.34'))

    def test_selected_month_forecast_is_used_automatically(self):
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'forecast', 'planning_month': '2026-10',
        })
        self.assertEqual(response.context['forecast']['total'], D('33.33'))
        self.assertEqual(response.context['forecast']['count'], 1)
        self.assertContains(response, 'R$ 33,33')
        self.assertIsNone(response.context['result'])

        response = self.client.post(reverse('sandbox:index'), {
            'action': 'calculate', 'planning_month': '2026-10', 'gross_salary': '5000',
            'variable_label': ['Rent'], 'variable_type': ['currency'], 'variable_value': ['450'],
        })
        self.assertEqual(response.context['result']['budget'].fixed_bills, D('33.33'))
        self.assertEqual(response.context['result']['budget'].custom_expenses, D('450.00'))
        self.assertEqual(response.context['result']['budget'].remaining, D('4015.16'))
        self.assertEqual(ScenarioDraft.objects.count(), 0)

    def test_forecast_changes_with_the_selected_month(self):
        october = self.client.post(reverse('sandbox:index'), {
            'action': 'forecast', 'planning_month': '2026-10',
        })
        december = self.client.post(reverse('sandbox:index'), {
            'action': 'forecast', 'planning_month': '2026-12',
        })
        self.assertEqual(october.context['forecast']['total'], D('33.33'))
        self.assertEqual(december.context['forecast']['total'], D('0.00'))

    def test_optional_save_keeps_a_stable_forecast_snapshot(self):
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'save', 'draft_name': 'October', 'planning_month': '2026-10',
            'gross_salary': '5000',
        })
        draft = ScenarioDraft.objects.get()
        self.assertRedirects(response, reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertTrue(draft.payload['complete'])
        self.assertTrue(draft.payload['snapshot']['rows'])
        self.purchase.amount = D('300')
        self.purchase.save()
        reopened = self.client.get(reverse('sandbox:draft_detail', args=[draft.pk]))
        self.assertEqual(reopened.context['result']['budget'].fixed_bills, D('33.33'))
        self.assertEqual(reopened.context['result']['budget'].remaining, D('4465.16'))
        self.assertTrue(reopened.context['draft_save_open'])
        compared = self.client.get(reverse('sandbox:compare'), {'draft': draft.pk})
        self.assertEqual(compared.context['scenarios'][0]['result']['budget'].fixed_bills, D('33.33'))

    def test_missing_fx_marks_forecast_incomplete_and_blocks_calculation(self):
        from datetime import date
        from sandbox.planning import commitment_snapshot, snapshot_total
        self.account.currency = 'USD'
        self.account.save()
        snapshot = commitment_snapshot(self.user, date(2026, 10, 1))
        self.assertIsNone(snapshot['rows'][0]['amount'])
        with self.assertRaises(ValidationError):
            snapshot_total(snapshot, '2026-10')
        response = self.client.post(reverse('sandbox:index'), {
            'action': 'calculate', 'planning_month': '2026-10', 'gross_salary': '5000',
        })
        self.assertIsNone(response.context['forecast']['total'])
        self.assertIsNone(response.context['result'])
        self.assertContains(response, 'Incomplete forecast')
        self.assertContains(response, 'exchange rate')
