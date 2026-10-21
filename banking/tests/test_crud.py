"""Crud coverage for banking."""

from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils.html import strip_tags
from core.urls import urlpatterns as core_urlpatterns
from banking.models import Bank, BankAccount, CardInvoice, CreditCard, DebitCard, LoyaltyEntry, LoyaltyProgram
from banking.tests.factories import make_account


urlpatterns = [*core_urlpatterns, path('banking/', include('banking.urls'))]


User = get_user_model()


@override_settings(ROOT_URLCONF=__name__)
class BankingViewTests(TestCase):
    def test_anonymous_bank_pages_redirect_before_querying_the_ledger(self):
        self.client.logout()
        for url in (reverse('banking:list'), reverse('banking:detail', args=[1])):
            with self.subTest(url=url), self.assertNumQueries(0):
                response = self.client.get(url)
                self.assertRedirects(
                    response, f"{reverse('accounts:login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def setUp(self):
        self.user = User.objects.create_user('views', password='test')
        self.other = User.objects.create_user('views-other', password='test')
        self.account = make_account(self.user, opening='50.00')
        self.foreign = make_account(self.other, bank_name='Secret Bank')
        self.client.force_login(self.user)

    def test_list_and_detail_render_native_balance_and_hide_other_owner(self):
        response = self.client.get(reverse('banking:list'))
        self.assertContains(response, 'Nubank')
        self.assertIn('BRL 50,00', ' '.join(strip_tags(response.content.decode()).split()))
        self.assertNotContains(response, 'Secret Bank')
        detail = self.client.get(reverse('banking:detail', args=[self.account.bank_id]))
        self.assertContains(detail, 'Add debit card')
        self.assertIn('BRL 50,00', ' '.join(strip_tags(detail.content.decode()).split()))
        self.assertEqual(
            self.client.get(reverse('banking:detail', args=[self.foreign.bank_id])).status_code,
            404,
        )

    def test_retired_search_does_not_hide_banks_or_expose_another_owner(self):
        self.assertContains(self.client.get(reverse('banking:list'), {'q': 'Checking'}), 'Nubank')
        response = self.client.get(reverse('banking:list'), {'q': 'missing'})
        self.assertContains(response, 'Nubank')
        self.assertNotContains(response, 'Secret Bank')
        self.assertNotContains(response, 'bank-filter-form')

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
            {'bank': self.account.bank_id, 'name': 'Savings', 'currency': 'USD', 'opening_balance': '4.00', 'opening_date': '2025-01-01'},
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
        self.assertContains(self.client.get(reverse('banking:programs')), 'Miles')
        self.client.post(
            reverse('banking:program_update', args=[program.pk]),
            {'name': 'Travel Miles', 'bank': self.account.bank_id, 'cards': [], 'unit_name': 'Miles'},
        )
        program.refresh_from_db()
        self.assertEqual(program.name, 'Travel Miles')
        self.client.post(reverse('banking:program_delete', args=[program.pk]))
        self.assertFalse(LoyaltyProgram.objects.filter(pk=program.pk).exists())

    def test_loyalty_entry_form_marks_conditional_invoice_and_purchase_fields(self):
        response = self.client.get(reverse('banking:entry_create'))

        self.assertEqual(response.context['form_variant'], 'loyalty_entry')
        self.assertContains(response, 'id="loyalty-invoice-fields"')
        self.assertContains(response, 'id="loyalty-purchase-fields"')
        self.assertContains(response, "kind.value === 'INVOICE_AWARD'")
        self.assertContains(response, "kind.value === 'PURCHASE'")

    def test_invoice_entry_link_prefills_the_relevant_kind_and_direction(self):
        card = CreditCard.objects.create(
            user=self.user,
            account=self.account,
            name='Rewards card',
            closing_day=10,
            due_day=20,
        )
        invoice = CardInvoice.objects.create(
            user=self.user,
            card=card,
            reference_month=date(2026, 9, 1),
            due_date=date(2026, 9, 20),
            amount=Decimal('0.00'),
        )

        response = self.client.get(reverse('banking:entry_create'), {'invoice': invoice.pk})

        self.assertEqual(response.context['form']['invoice'].value(), str(invoice.pk))
        self.assertEqual(
            response.context['form']['kind'].value(),
            LoyaltyEntry.Kind.INVOICE_AWARD,
        )
        self.assertEqual(
            response.context['form']['direction'].value(),
            LoyaltyEntry.Direction.CREDIT,
        )
