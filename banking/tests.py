from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from core.urls import urlpatterns as core_urlpatterns

from banking.forms import LoyaltyProgramForm
from banking.models import (
    Bank,
    BankAccount,
    BankMovement,
    BankTransfer,
    CardInvoice,
    CreditCard,
    DebitCard,
    ExchangeRate,
    LoyaltyEntry,
    LoyaltyProgram,
    RewardRedemption,
)
from banking.services import (
    MissingExchangeRate,
    convert,
    create_movement,
    create_reward_redemption,
    create_transfer,
    latest_exchange_rate,
    sync_loyalty_entry_funding,
)


urlpatterns = [*core_urlpatterns, path('banking/', include('banking.urls'))]
User = get_user_model()


def make_account(user, *, bank_name='Nubank', name='Checking', currency='BRL', opening='0.00'):
    bank, _ = Bank.objects.get_or_create(user=user, name=bank_name)
    return BankAccount.objects.create(
        user=user,
        bank=bank,
        name=name,
        currency=currency,
        opening_balance=Decimal(opening),
    )


class OwnershipAndConstraintTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', password='test')
        self.other = User.objects.create_user('other', password='test')
        self.account = make_account(self.user)

    def test_bank_name_is_unique_per_user_only(self):
        Bank.objects.create(user=self.other, name='Nubank')
        with self.assertRaises(IntegrityError):
            Bank.objects.create(user=self.user, name='Nubank')

    def test_account_rejects_bank_from_another_owner(self):
        foreign_bank = Bank.objects.create(user=self.other, name='Private')
        account = BankAccount(
            user=self.user, bank=foreign_bank, name='Forged', currency='BRL'
        )
        with self.assertRaises(ValidationError):
            account.full_clean()

    def test_cards_reject_account_from_another_owner(self):
        for model, extra in (
            (DebitCard, {}),
            (CreditCard, {'closing_day': 10, 'due_day': 20}),
        ):
            card = model(user=self.other, account=self.account, name=model.__name__, **extra)
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                card.full_clean()

    def test_positive_amount_database_checks(self):
        with self.assertRaises(IntegrityError):
            BankMovement.objects.create(
                user=self.user,
                account=self.account,
                direction=BankMovement.Direction.CREDIT,
                kind=BankMovement.Kind.ADJUSTMENT,
                amount=Decimal('0.00'),
                effective_date=date.today(),
            )


class BalanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('balance', password='test')
        self.account = make_account(self.user, opening='100.00')

    def movement(self, direction, amount, on):
        return create_movement(
            user=self.user,
            account=self.account,
            direction=direction,
            kind=BankMovement.Kind.ADJUSTMENT,
            amount=Decimal(amount),
            effective_date=on,
        )

    def test_balance_uses_opening_and_signed_movements_through_date(self):
        self.movement(BankMovement.Direction.CREDIT, '25.00', date(2026, 1, 10))
        self.movement(BankMovement.Direction.DEBIT, '8.00', date(2026, 1, 20))
        self.assertEqual(self.account.current_balance(date(2026, 1, 15)), Decimal('125.00'))
        self.assertEqual(self.account.current_balance(date(2026, 1, 20)), Decimal('117.00'))

    def test_current_balance_excludes_future_movements(self):
        self.movement(
            BankMovement.Direction.CREDIT,
            '999.00',
            timezone.localdate() + timedelta(days=1),
        )
        self.assertEqual(self.account.current_balance(), Decimal('100.00'))

    def test_movement_affects_balance_immediately_on_effective_date(self):
        today = timezone.localdate()
        self.movement(BankMovement.Direction.DEBIT, '12.50', today)
        self.assertEqual(self.account.current_balance(), Decimal('87.50'))


class TransferTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('transfer', password='test')
        self.source = make_account(self.user, name='Source', opening='100.00')
        self.destination = make_account(self.user, name='Destination', opening='20.00')

    def test_transfer_creates_linked_debit_credit_pair_and_is_neutral(self):
        transfer = create_transfer(
            user=self.user,
            source_account=self.source,
            destination_account=self.destination,
            source_amount=Decimal('30.00'),
            destination_amount=Decimal('30.00'),
            date=timezone.localdate(),
            notes='Own transfer',
        )
        movements = list(transfer.movements.order_by('direction'))
        self.assertEqual(len(movements), 2)
        self.assertEqual({m.kind for m in movements}, {BankMovement.Kind.TRANSFER})
        self.assertEqual(self.source.current_balance(), Decimal('70.00'))
        self.assertEqual(self.destination.current_balance(), Decimal('50.00'))
        self.assertEqual(
            self.source.current_balance() + self.destination.current_balance(),
            Decimal('120.00'),
        )

    def test_cross_currency_transfer_preserves_two_native_amounts(self):
        usd = make_account(self.user, name='USD', currency='USD')
        transfer = create_transfer(
            user=self.user,
            source_account=self.source,
            destination_account=usd,
            source_amount=Decimal('50.00'),
            destination_amount=Decimal('10.00'),
            date=timezone.localdate(),
        )
        self.assertEqual(transfer.source_amount, Decimal('50.00'))
        self.assertEqual(transfer.destination_amount, Decimal('10.00'))
        self.assertEqual(usd.current_balance(), Decimal('10.00'))

    def test_transfer_rejects_same_account_and_different_owner(self):
        same = BankTransfer(
            user=self.user,
            source_account=self.source,
            destination_account=self.source,
            source_amount=1,
            destination_amount=1,
            date=date.today(),
        )
        with self.assertRaises(ValidationError):
            same.full_clean()
        other = User.objects.create_user('transfer-other')
        foreign = make_account(other)
        with self.assertRaises(ValidationError):
            create_transfer(
                user=self.user,
                source_account=self.source,
                destination_account=foreign,
                source_amount=1,
                destination_amount=1,
                date=date.today(),
            )


class CardAndInvoiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('cards')
        self.account = make_account(self.user)
        self.card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Platinum',
            closing_day=31,
            due_day=31,
        )

    def test_statement_month_clamps_closing_day_in_short_month(self):
        self.assertEqual(self.card.statement_month(date(2025, 2, 27)), date(2025, 2, 1))
        self.assertEqual(self.card.statement_month(date(2025, 2, 28)), date(2025, 3, 1))

    def test_best_purchase_day_matches_the_configured_closing_day(self):
        self.assertEqual(self.card.best_purchase_day, 31)
        self.card.closing_day = 24
        self.assertEqual(self.card.best_purchase_day, 24)

    def test_statement_override_preserves_explicit_current_or_next(self):
        purchase = date(2026, 1, 31)
        self.assertEqual(self.card.statement_month(purchase, override=0), date(2026, 1, 1))
        self.assertEqual(self.card.statement_month(purchase, override=1), date(2026, 2, 1))
        with self.assertRaises(ValueError):
            self.card.statement_month(purchase, override=2)

    def test_due_date_clamps_short_month(self):
        self.assertEqual(self.card.due_date_for(date(2024, 2, 18)), date(2024, 2, 29))

    def test_due_date_moves_to_next_month_when_due_day_precedes_closing_day(self):
        self.card.closing_day = 24
        self.card.due_day = 1
        self.assertEqual(self.card.due_date_for(date(2026, 8, 1)), date(2026, 9, 1))

    def test_invoice_requires_first_day_and_is_unique_per_card_month(self):
        invalid = CardInvoice(
            user=self.user,
            card=self.card,
            reference_month=date(2026, 1, 2),
            due_date=date(2026, 1, 31),
            amount=Decimal('0.00'),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        CardInvoice.objects.create(
            user=self.user,
            card=self.card,
            reference_month=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            amount=Decimal('0.00'),
        )
        with self.assertRaises(IntegrityError):
            CardInvoice.objects.create(
                user=self.user,
                card=self.card,
                reference_month=date(2026, 1, 1),
                due_date=date(2026, 1, 31),
                amount=Decimal('1.00'),
            )

    def test_invoice_is_aggregate_and_account_property_is_linked_account(self):
        invoice = CardInvoice.objects.create(
            user=self.user,
            card=self.card,
            reference_month=date(2026, 2, 1),
            due_date=date(2026, 2, 28),
            amount=Decimal('200.00'),
        )
        self.assertEqual(invoice.account, self.account)
        self.assertEqual(self.account.current_balance(), Decimal('0.00'))


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


class ExchangeRateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('rates')

    def rate(self, source, target, value, on):
        return ExchangeRate.objects.create(
            user=self.user,
            from_currency=source,
            to_currency=target,
            rate=Decimal(value),
            effective_date=on,
        )

    def test_latest_rate_is_as_of_and_direct_conversion_is_supported(self):
        old = self.rate('USD', 'BRL', '5.00', date(2026, 1, 1))
        self.rate('USD', 'BRL', '6.00', date(2026, 2, 1))
        self.assertEqual(latest_exchange_rate(self.user, 'USD', 'BRL', date(2026, 1, 15)), old)
        self.assertEqual(convert(self.user, 10, 'USD', 'BRL', date(2026, 1, 15)), Decimal('50.00000000'))

    def test_inverse_and_identity_conversion(self):
        self.rate('USD', 'BRL', '5.00', date(2026, 1, 1))
        self.assertEqual(convert(self.user, 50, 'BRL', 'USD', date(2026, 1, 1)), Decimal('10'))
        self.assertEqual(convert(self.user, '7.25', 'BRL', 'BRL'), Decimal('7.25'))

    def test_missing_rate_is_explicit(self):
        with self.assertRaises(MissingExchangeRate):
            convert(self.user, 1, 'EUR', 'BRL', date(2026, 1, 1))


class RewardRedemptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('rewards')
        self.target = make_account(self.user, name='Target')
        self.iof = make_account(self.user, name='IOF', opening='10.00')
        self.card = CreditCard.objects.create(
            user=self.user,
            account=self.iof,
            name='IOF card',
            closing_day=10,
            due_day=20,
        )
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Rewards')
        LoyaltyEntry.objects.create(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.ADJUSTMENT,
            amount=Decimal('1000.00'),
            date=date.today(),
        )

    def redeem(self, **kwargs):
        values = {
            'user': self.user,
            'program': self.program,
            'points': Decimal('100.00'),
            'target_account': self.target,
            'target_amount': Decimal('25.00'),
            'date': timezone.localdate(),
        }
        values.update(kwargs)
        return create_reward_redemption(**values)

    def test_redemption_creates_points_debit_and_target_reward_credit(self):
        redemption = self.redeem()
        self.assertEqual(self.program.balance, Decimal('900.00'))
        self.assertEqual(self.target.current_balance(), Decimal('25.00'))
        self.assertFalse(redemption.has_pending_credit_card_iof)
        self.assertEqual(
            BankMovement.objects.get(account=self.target).kind,
            BankMovement.Kind.REWARD,
        )

    def test_account_funded_iof_creates_immediate_expense_debit(self):
        self.redeem(iof_amount=Decimal('2.00'), iof_account=self.iof)
        self.assertEqual(self.iof.current_balance(), Decimal('8.00'))
        movement = BankMovement.objects.get(account=self.iof)
        self.assertEqual((movement.direction, movement.kind), ('DEBIT', 'EXPENSE'))

    def test_credit_card_iof_is_persisted_and_explicitly_pending(self):
        redemption = self.redeem(
            iof_amount=Decimal('2.00'), iof_credit_card=self.card
        )
        self.assertTrue(redemption.has_pending_credit_card_iof)
        self.assertFalse(BankMovement.objects.filter(account=self.iof).exists())

    def test_iof_requires_exactly_one_instrument_or_none_for_zero(self):
        invalid_values = (
            {'iof_amount': Decimal('1.00')},
            {'iof_amount': Decimal('1.00'), 'iof_account': self.iof, 'iof_credit_card': self.card},
            {'iof_amount': Decimal('0.00'), 'iof_account': self.iof},
        )
        for values in invalid_values:
            redemption = RewardRedemption(
                user=self.user,
                program=self.program,
                points=1,
                target_account=self.target,
                target_amount=1,
                date=date.today(),
                **values,
            )
            with self.subTest(values=values), self.assertRaises(ValidationError):
                redemption.full_clean()

    def test_redemption_rejects_insufficient_points(self):
        with self.assertRaises(ValidationError):
            self.redeem(points=Decimal('1001.00'))


class LoyaltyPurchaseFundingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('point-purchase')
        self.account = make_account(self.user, opening='100.00')
        self.card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Rewards Card',
            closing_day=10,
            due_day=20,
        )
        self.program = LoyaltyProgram.objects.create(user=self.user, name='Miles')

    def test_account_funded_purchase_debits_balance_once(self):
        entry = LoyaltyEntry.objects.create(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.PURCHASE,
            amount=Decimal('1000.00'),
            cash_amount=Decimal('25.00'),
            funding_account=self.account,
            date=timezone.localdate(),
        )
        sync_loyalty_entry_funding(entry)
        sync_loyalty_entry_funding(entry)

        entry.refresh_from_db()
        self.assertEqual(self.account.current_balance(), Decimal('75.00'))
        self.assertEqual(entry.funding_movement.source_key, f'loyalty-entry:{entry.pk}')

    def test_card_funded_purchase_has_no_immediate_movement(self):
        entry = LoyaltyEntry(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.CREDIT,
            kind=LoyaltyEntry.Kind.PURCHASE,
            amount=Decimal('1000.00'),
            cash_amount=Decimal('25.00'),
            funding_credit_card=self.card,
            date=timezone.localdate(),
        )
        entry.full_clean()
        entry.save()
        sync_loyalty_entry_funding(entry)

        self.assertIsNone(entry.funding_movement)
        self.assertEqual(self.account.current_balance(), Decimal('100.00'))

    def test_invoice_award_must_be_credit(self):
        entry = LoyaltyEntry(
            user=self.user,
            program=self.program,
            direction=LoyaltyEntry.Direction.DEBIT,
            kind=LoyaltyEntry.Kind.INVOICE_AWARD,
            amount=Decimal('10.00'),
            date=timezone.localdate(),
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()


@override_settings(ROOT_URLCONF=__name__)
class BankingViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('views', password='test')
        self.other = User.objects.create_user('views-other', password='test')
        self.account = make_account(self.user, opening='50.00')
        self.foreign = make_account(self.other, bank_name='Secret Bank')
        self.client.force_login(self.user)

    def test_list_and_detail_render_native_balance_and_hide_other_owner(self):
        response = self.client.get(reverse('banking:list'))
        self.assertContains(response, 'Nubank')
        self.assertContains(response, 'BRL 50,00')
        self.assertNotContains(response, 'Secret Bank')
        detail = self.client.get(reverse('banking:detail', args=[self.account.bank_id]))
        self.assertContains(detail, 'Add debit card')
        self.assertContains(detail, 'BRL 50,00')
        self.assertEqual(
            self.client.get(reverse('banking:detail', args=[self.foreign.bank_id])).status_code,
            404,
        )

    def test_search_matches_account_and_has_empty_state(self):
        self.assertContains(self.client.get(reverse('banking:list'), {'q': 'Checking'}), 'Nubank')
        self.assertContains(self.client.get(reverse('banking:list'), {'q': 'missing'}), 'No matching banks')

    def test_bank_crud_and_duplicate_is_friendly(self):
        response = self.client.post(reverse('banking:create'), {'name': 'New Bank'})
        bank = Bank.objects.get(user=self.user, name='New Bank')
        self.assertRedirects(response, reverse('banking:list'))
        self.client.post(reverse('banking:update', args=[bank.pk]), {'name': 'Renamed'})
        bank.refresh_from_db()
        self.assertEqual(bank.name, 'Renamed')
        duplicate = self.client.post(reverse('banking:create'), {'name': 'Renamed'})
        self.assertContains(duplicate, 'already have a bank', status_code=200)
        self.client.post(reverse('banking:delete', args=[bank.pk]))
        self.assertFalse(Bank.objects.filter(pk=bank.pk).exists())

    def test_account_and_card_crud_is_owned_and_returns_to_bank(self):
        response = self.client.post(
            reverse('banking:account_create'),
            {'bank': self.account.bank_id, 'name': 'Savings', 'currency': 'USD', 'opening_balance': '4.00'},
        )
        savings = BankAccount.objects.get(user=self.user, name='Savings')
        self.assertRedirects(response, reverse('banking:detail', args=[self.account.bank_id]))
        forged = self.client.post(
            reverse('banking:account_create'),
            {'bank': self.foreign.bank_id, 'name': 'Forged', 'currency': 'BRL', 'opening_balance': '0'},
        )
        self.assertEqual(forged.status_code, 200)
        self.assertFalse(BankAccount.objects.filter(user=self.user, name='Forged').exists())
        debit = self.client.post(
            reverse('banking:debit_card_create'),
            {'account': savings.pk, 'name': 'Debit'},
        )
        self.assertEqual(debit.status_code, 302)
        credit = self.client.post(
            reverse('banking:credit_card_create'),
            {
                'account': savings.pk,
                'name': 'Credit',
                'card_type': CreditCard.CardType.VIRTUAL,
                'closing_day': 12,
                'due_day': 22,
            },
        )
        self.assertEqual(credit.status_code, 302)
        self.assertTrue(DebitCard.objects.filter(account=savings, name='Debit').exists())
        card = CreditCard.objects.get(account=savings, name='Credit')
        self.assertEqual(card.card_type, CreditCard.CardType.VIRTUAL)
        self.assertContains(
            self.client.get(reverse('banking:detail', args=[self.account.bank_id])),
            'Virtual',
        )

    def test_program_crud_supports_independent_program(self):
        create = self.client.post(
            reverse('banking:program_create'),
            {'name': 'Miles', 'bank': '', 'cards': [], 'unit_name': 'Miles'},
        )
        program = LoyaltyProgram.objects.get(user=self.user, name='Miles')
        self.assertRedirects(create, reverse('banking:list'))
        self.assertContains(self.client.get(reverse('banking:list')), 'Independent loyalty programs')
        self.client.post(
            reverse('banking:program_update', args=[program.pk]),
            {'name': 'Travel Miles', 'bank': self.account.bank_id, 'cards': [], 'unit_name': 'Miles'},
        )
        program.refresh_from_db()
        self.assertEqual(program.name, 'Travel Miles')
        self.client.post(reverse('banking:program_delete', args=[program.pk]))
        self.assertFalse(LoyaltyProgram.objects.filter(pk=program.pk).exists())
