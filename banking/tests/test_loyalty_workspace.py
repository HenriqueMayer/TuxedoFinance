# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Owned loyalty consultation preserves balances, origins and complete history."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from banking.models import Bank, BankAccount, BankMovement, CreditCard, LoyaltyEntry, LoyaltyProgram, RewardRedemption


class LoyaltyWorkspaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('loyalty-workspace-owner')
        self.other = get_user_model().objects.create_user('loyalty-workspace-other')
        self.bank = Bank.objects.create(user=self.user, name='Cedar bank')
        self.account = BankAccount.objects.create(user=self.user, bank=self.bank, name='Daily', currency='BRL')
        self.card = CreditCard.objects.create(user=self.user, account=self.account, name='Travel card', closing_day=20, due_day=28, color='#65418C')
        self.program = LoyaltyProgram.objects.create(user=self.user, bank=self.bank, name='Travel rewards', unit_name='Miles')
        self.program.cards.add(self.card)
        self.independent = LoyaltyProgram.objects.create(user=self.user, name='Independent points', unit_name='Points')
        self.credit = self.entry('100.50')
        self.entry('12.25', direction='DEBIT', kind='EXPIRATION')
        self.client.force_login(self.user)

    def entry(self, amount, **kwargs):
        return LoyaltyEntry.objects.create(user=kwargs.pop('user', self.user), program=kwargs.pop('program', self.program),
            amount=amount, direction=kwargs.pop('direction', 'CREDIT'), kind=kwargs.pop('kind', 'ADJUSTMENT'),
            date=kwargs.pop('date', date(2026, 10, 1)), notes=kwargs.pop('notes', 'Local evidence'), **kwargs)

    def test_overview_shows_owned_programs_cards_and_native_points_without_writes(self):
        original = list(LoyaltyEntry.objects.values())
        response = self.client.get(reverse('banking:programs'))
        self.assertEqual(response.status_code, 200)
        programs = {program.pk: program for program in response.context['programs']}
        self.assertEqual(set(programs), {self.program.pk, self.independent.pk})
        self.assertEqual(programs[self.program.pk].displayed_balance, Decimal('88.25'))
        self.assertEqual(programs[self.independent.pk].displayed_balance, Decimal('0'))
        self.assertRegex(response.content.decode(), r'loyalty-program-balance">88[,.]25')
        self.assertContains(response, 'Miles')
        self.assertContains(response, 'Travel card')
        self.assertContains(response, 'data-live-results="loyalty-results"')
        self.assertContains(response, 'class="card-miniature')
        self.assertEqual(list(LoyaltyEntry.objects.values()), original)
        self.assertFalse(BankMovement.objects.exists())

    def test_card_search_cannot_duplicate_balance_and_bank_search_retains_independent_results(self):
        second_card = CreditCard.objects.create(user=self.user, account=self.account, name='Travel spare', closing_day=1, due_day=10)
        self.program.cards.add(second_card)
        response = self.client.get(reverse('banking:programs'), {'q': 'Travel'})
        self.assertEqual(len(response.context['programs']), 1)
        self.assertEqual(response.context['programs'][0].displayed_balance, Decimal('88.25'))
        for query in ('Cedar', 'Miles', 'Travel spare'):
            response = self.client.get(reverse('banking:programs'), {'q': query})
            self.assertEqual(list(response.context['programs']), [self.program])
        response = self.client.get(reverse('banking:programs'), {'q': 'Independent'})
        self.assertEqual(list(response.context['programs']), [self.independent])

    def test_foreign_legacy_bank_cards_and_entries_do_not_leak_or_change_balance(self):
        private_bank = Bank.objects.create(user=self.other, name='Private institution')
        private_account = BankAccount.objects.create(user=self.other, bank=private_bank, name='Private account', currency='BRL')
        private_card = CreditCard.objects.create(user=self.other, account=private_account, name='Private card', closing_day=1, due_day=10)
        broken_card = CreditCard.objects.create(user=self.user, account=private_account, name='Malformed legacy card', closing_day=1, due_day=10)
        self.program.cards.add(private_card, broken_card)
        self.program.bank = private_bank
        self.program.save(update_fields=['bank'])
        self.entry('999999', user=self.other, notes='Private entry')
        foreign_program = LoyaltyProgram.objects.create(user=self.other, name='Private program')
        self.entry('999999', program=foreign_program, notes='Foreign program evidence')
        response = self.client.get(reverse('banking:programs'))
        for secret in ('Private institution', 'Private card', 'Malformed legacy card', 'Private entry', 'Private program', 'Foreign program evidence'):
            self.assertNotContains(response, secret)
        self.assertEqual(next(program for program in response.context['programs'] if program.pk == self.program.pk).displayed_balance, Decimal('88.25'))
        for query in ('Private', 'Malformed'):
            self.assertEqual(list(self.client.get(reverse('banking:programs'), {'q': query}).context['programs']), [])
        self.assertEqual(self.client.get(reverse('banking:program_entries', args=[foreign_program.pk])).status_code, 404)

    def test_overview_bounds_recent_entries_but_full_history_has_independent_pagination(self):
        for number in range(35):
            self.entry('1', notes=f'Entry {number:02}')
        response = self.client.get(reverse('banking:programs'))
        program = next(program for program in response.context['programs'] if program.pk == self.program.pk)
        self.assertEqual(program.entry_count, 37)
        self.assertEqual(len(program.recent_entries), 10)
        self.assertContains(response, reverse('banking:program_entries', args=[self.program.pk]))
        history = self.client.get(reverse('banking:program_entries', args=[self.program.pk]))
        self.assertEqual(history.context['paginator'].count, 37)
        self.assertEqual(len(history.context['entries']), 30)
        second = self.client.get(reverse('banking:program_entries', args=[self.program.pk]), {'page': 2})
        self.assertEqual(len(second.context['entries']), 7)
        search = self.client.get(reverse('banking:program_entries', args=[self.program.pk]), {'q': 'Entry 03'})
        self.assertEqual(len(search.context['entries']), 1)
        self.assertEqual(search.context['selected_program'].displayed_balance, Decimal('123.25'))

    def test_program_pagination_is_complete_and_ordered(self):
        LoyaltyProgram.objects.bulk_create([LoyaltyProgram(user=self.user, name=f'Extra {number:02}') for number in range(25)])
        first = self.client.get(reverse('banking:programs'))
        second = self.client.get(reverse('banking:programs'), {'page': 2})
        self.assertEqual(first.context['paginator'].count, 27)
        self.assertEqual(len(first.context['programs']), 20)
        self.assertEqual(len(second.context['programs']), 7)
        ids = [program.pk for program in first.context['programs']] + [program.pk for program in second.context['programs']]
        self.assertEqual(ids, list(LoyaltyProgram.objects.filter(user=self.user).order_by('name', 'pk').values_list('pk', flat=True)))

    def test_explicit_filtered_origin_survives_invalid_form_and_cancel(self):
        origin = reverse('banking:programs') + '?q=Travel'
        response = self.client.get(origin)
        self.assertContains(response, 'next=%2Fbanking%2Floyalty%2F%3Fq%3DTravel')
        create = reverse('banking:entry_create')
        response = self.client.get(create, {'program': self.program.pk, 'next': origin})
        self.assertEqual(response.context['cancel_url'], origin)
        invalid = self.client.post(create, {'program': self.program.pk, 'direction': 'CREDIT', 'kind': 'ADJUSTMENT', 'amount': '-1', 'date': '2026-10-01', 'next': origin})
        self.assertEqual(invalid.context['cancel_url'], origin)
        self.assertIn('amount', invalid.context['form'].errors)
        self.assertEqual(LoyaltyEntry.objects.filter(user=self.user, program=self.program).count(), 2)

    def test_generated_redemption_entry_exposes_source_editor_without_independent_edit_delete(self):
        debit = self.entry('10', direction='DEBIT', kind='REDEMPTION', notes='Generated reward')
        redemption = RewardRedemption.objects.create(user=self.user, program=self.program, points=10, target_account=self.account,
            target_amount=1, date=date(2026, 10, 1), loyalty_entry=debit)
        response = self.client.get(reverse('banking:program_entries', args=[self.program.pk]))
        self.assertContains(response, reverse('banking:redemption_update', args=[redemption.pk]) + '?next=')
        self.assertNotContains(response, reverse('banking:entry_update', args=[debit.pk]))
        self.assertNotContains(response, reverse('banking:entry_delete', args=[debit.pk]))

    def test_invalid_search_is_recoverable_and_reads_remain_authenticated_gets(self):
        for url in (reverse('banking:programs'), reverse('banking:program_entries', args=[self.program.pk])):
            response = self.client.get(url, {'q': 'x' * 201})
            self.assertIn('q', response.context['filter_form'].errors)
            self.assertEqual(response.context['paginator'].count, 0)
            self.assertContains(response, 'loyalty-filter-q-error-1')
            self.assertEqual(self.client.post(url).status_code, 405)
            self.client.logout()
            self.assertEqual(self.client.get(url).status_code, 302)
            self.client.force_login(self.user)
