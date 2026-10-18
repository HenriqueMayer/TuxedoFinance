"""Loyalty coverage for banking."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from banking.forms import LoyaltyProgramForm
from banking.models import CreditCard, LoyaltyEntry, LoyaltyProgram
from banking.tests.factories import make_account


User = get_user_model()


class LoyaltyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('loyalty')
        self.other = User.objects.create_user('loyalty-other')
        self.client.force_login(self.user)
        self.account = make_account(self.user)
        self.card = CreditCard.objects.create(
            user=self.user, account=self.account, name='Gold', closing_day=10, due_day=20
        )

    def test_program_can_be_independent_bank_linked_and_card_linked(self):
        independent = LoyaltyProgram.objects.create(user=self.user, name='Airline')
        linked = LoyaltyProgram.objects.create(
            user=self.user, name='Bank points', bank=self.account.bank
        )
        linked.cards.add(self.card)
        self.assertIsNone(independent.bank)
        self.assertEqual(list(linked.cards.all()), [self.card])

    def test_program_balance_sums_signed_decimal_entries(self):
        program = LoyaltyProgram.objects.create(user=self.user, name='Points')
        LoyaltyEntry.objects.create(
            user=self.user,
            program=program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.ADJUSTMENT,
            amount=Decimal('100.50'),
            date=date.today(),
        )
        LoyaltyEntry.objects.create(
            user=self.user,
            program=program,
            direction=LoyaltyEntry.Direction.DEBIT,
            kind=LoyaltyEntry.Kind.EXPIRATION,
            amount=Decimal('12.25'),
            date=date.today(),
        )
        self.assertEqual(program.balance, Decimal('88.25'))

    def test_program_form_filters_and_rejects_foreign_relations(self):
        foreign_account = make_account(self.other)
        foreign_card = CreditCard.objects.create(
            user=self.other,
            account=foreign_account,
            name='Foreign',
            closing_day=1,
            due_day=2,
        )
        form = LoyaltyProgramForm(user=self.user)
        self.assertNotIn(foreign_card, form.fields['cards'].queryset)
        forged = LoyaltyProgram(user=self.user, name='Forged', bank=foreign_account.bank)
        with self.assertRaises(ValidationError):
            forged.full_clean()

    def test_program_form_filters_cards_to_the_selected_bank(self):
        inter_account = make_account(self.user, bank_name='Banco Inter', name='Inter account')
        inter_card = CreditCard.objects.create(
            user=self.user,
            account=inter_account,
            name='InterBlack',
            closing_day=10,
            due_day=20,
        )
        program = LoyaltyProgram.objects.create(
            user=self.user,
            name='Pontos Loop',
            bank=inter_account.bank,
        )
        program.cards.add(inter_card)

        form = LoyaltyProgramForm(user=self.user, instance=program)

        self.assertEqual(list(form.fields['cards'].queryset), [inter_card])
        self.assertNotIn(self.card, form.fields['cards'].queryset)

    def test_program_form_rejects_a_card_from_another_bank(self):
        inter_account = make_account(self.user, bank_name='Banco Inter', name='Inter account')
        form = LoyaltyProgramForm(
            user=self.user,
            data={
                'name': 'Pontos Loop',
                'bank': inter_account.bank_id,
                'cards': [self.card.pk],
                'unit_name': 'Points',
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn('cards', form.errors)

    def test_new_program_from_bank_context_locks_bank_and_filters_cards(self):
        inter_account = make_account(self.user, bank_name='Banco Inter', name='Inter account')
        inter_card = CreditCard.objects.create(
            user=self.user,
            account=inter_account,
            name='InterBlack',
            closing_day=10,
            due_day=20,
        )

        response = self.client.get(
            reverse('banking:program_create') + f'?bank={inter_account.bank_id}'
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.fields['bank'].disabled)
        self.assertEqual(list(form.fields['cards'].queryset), [inter_card])
        self.assertNotIn(self.card, form.fields['cards'].queryset)
        self.assertContains(response, 'InterBlack')
        self.assertContains(response, 'id="id_bank"')
        self.assertContains(response, 'disabled')
        self.assertNotContains(response, '>Gold<')
