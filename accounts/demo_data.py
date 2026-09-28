# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit, fictional demo profiles; never read or clone an existing owner."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import translation

from accounts.demo_investments import seed_investments_and_drafts
from accounts.models import UserPreference
from banking.models import (
    Bank, BankAccount, CreditCard, DebitCard, ExchangeRate, LoyaltyEntry,
    LoyaltyProgram,
)
from banking.services import (
    create_reward_redemption, create_transfer, sync_loyalty_entry_funding,
)
from categories.models import Category
from transactions.models import Transaction
from transactions.services import sync_user_ledger


def _month(anchor, offset, day=1):
    index = anchor.year * 12 + anchor.month - 1 + offset
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day, monthrange(year, month)[1]))


def _create(model, **values):
    item = model(**values)
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def seed_demo_profile(*, language, username, password, as_of):
    """Create a complete new owner atomically; collisions never update data."""
    if language not in {'pt', 'en'}:
        raise ValueError('Demo language must be pt or en.')
    if not 1901 <= as_of.year <= 9988:
        raise ValueError('The reference year must be between 1901 and 9988, matching the planning forms.')
    User = get_user_model()
    if User.objects.filter(username__iexact=username).exists():
        raise ValueError('Username already exists. Choose a new --username; no data was changed.')

    def label(en, pt):
        return pt if language == 'pt' else en

    with translation.override('pt-br' if language == 'pt' else 'en'):
        user = User(username=username, first_name=label('Demo', 'Demonstração'))
        user.set_password(password)
        user.full_clean()
        user.save()
        _create(UserPreference, user=user, base_currency='BRL',
                date_format='DMY' if language == 'pt' else 'MDY')
        # Only the just-created user's signup categories are replaced. No existing
        # owner is accepted, even if its username resembles a demonstration user.
        user.categories.all().delete()

        def category(en, pt, kind='EXPENSE', parent=None):
            return _create(Category, user=user, name=label(en, pt),
                           transaction_type=kind, parent_category=parent)

        income = category('Income', 'Receitas', 'INCOME')
        salary = category('Salary', 'Salário', 'INCOME', income)
        freelance = category('Freelance work', 'Trabalho autônomo', 'INCOME', income)
        housing = category('Housing', 'Moradia')
        rent = category('Rent', 'Aluguel', parent=housing)
        utilities = category('Utilities', 'Contas da casa', parent=housing)
        food = category('Food', 'Alimentação')
        groceries = category('Groceries', 'Mercado', parent=food)
        dining = category('Dining out', 'Restaurantes', parent=food)
        transport = category('Transportation', 'Transporte')
        health = category('Health and fitness', 'Saúde e atividade física')
        learning = category('Education', 'Educação')
        subscriptions = category('Subscriptions', 'Assinaturas')
        travel = category('Travel', 'Viagens')
        technology = category('Technology', 'Tecnologia')
        pets = category('Pets', 'Animais de estimação')
        gifts = category('Gifts and reimbursements', 'Presentes e reembolsos', None)

        primary = _create(Bank, user=user, name=label('Aurora Demo Bank', 'Banco Aurora Demo'), color='#B88D57')
        global_bank = _create(Bank, user=user, name=label('Horizon Demo Bank', 'Banco Horizonte Demo'), color='#4F7CAC')
        second = _create(Bank, user=user, name=label('Cedar Demo Bank', 'Banco Cedro Demo'), color='#56876D')

        def account(bank, en, pt, currency, balance, **extra):
            return _create(BankAccount, user=user, bank=bank, name=label(en, pt),
                           currency=currency, opening_balance=Decimal(balance), **extra)

        checking = account(primary, 'Everyday account', 'Conta do dia a dia', 'BRL', '6500', reserved_amount=Decimal('1500'))
        savings = account(second, 'Emergency reserve', 'Reserva de emergência', 'BRL', '18000', planning_enabled=False)
        goals = account(primary, 'Travel goals', 'Objetivos de viagem', 'BRL', '2500', reserved_amount=Decimal('1000'))
        global_account = account(global_bank, 'Dollar account', 'Conta em dólares', 'USD', '2200', pix_enabled=False, planning_enabled=False)
        euro = account(global_bank, 'Euro wallet', 'Carteira em euros', 'EUR', '800', pix_enabled=False, planning_enabled=False)
        debit = _create(DebitCard, user=user, account=checking, name=label('Everyday debit', 'Débito cotidiano'))
        _create(DebitCard, user=user, account=global_account, name=label('Travel debit', 'Débito de viagem'))

        def card(en, pt, kind, closing, due):
            return _create(CreditCard, user=user, account=checking, name=label(en, pt),
                           card_type=kind, closing_day=closing, due_day=due)

        physical = card('Aurora physical', 'Aurora físico', 'PHYSICAL', 24, 5)
        virtual = card('Aurora online', 'Aurora virtual', 'VIRTUAL', 18, 25)
        additional = card('Aurora household', 'Aurora adicional', 'ADDITIONAL', 28, 8)

        for index, offset in enumerate(range(-12, 1)):
            for currency, base in [('USD', Decimal('4.85')), ('EUR', Decimal('5.35'))]:
                _create(ExchangeRate, user=user, from_currency=currency, to_currency='BRL',
                        rate=base + Decimal(index % 5) * Decimal('.07'),
                        effective_date=_month(as_of, offset),
                        notes=label('Fictional demonstration rate', 'Cotação fictícia de demonstração'))

        def entry(en, pt, amount, cat, when, channel='CREDIT_CARD', instrument=None, kind='EXPENSE', **extra):
            field = {'ACCOUNT': 'bank_account', 'PIX': 'bank_account',
                     'DEBIT_CARD': 'debit_card', 'CREDIT_CARD': 'credit_card'}[channel]
            return _create(Transaction, user=user, title=label(en, pt), amount=Decimal(amount),
                           category=cat, date=when, transaction_type=kind, payment_channel=channel,
                           **{field: instrument or physical}, **extra)

        # A recurring event is stored once, then projected by the same ledger
        # service as real data. Repeating it for every month would double-count.
        entry('Monthly salary', 'Salário mensal', '8600', salary, _month(as_of, -12, 5),
              'ACCOUNT', checking, 'INCOME', is_fixed=True)
        entry('Apartment rent', 'Aluguel do apartamento', '2200', rent, _month(as_of, -12, 8),
              'PIX', checking, is_fixed=True)
        entry('Internet plan', 'Plano de internet', '119.90', utilities, _month(as_of, -12, 10),
              'ACCOUNT', checking, is_fixed=True)
        entry('Streaming subscription', 'Assinatura de streaming', '49.90', subscriptions,
              _month(as_of, -12, 12), instrument=virtual, is_fixed=True)
        entry('Fitness membership', 'Mensalidade da academia', '139.90', health,
              _month(as_of, -12, 15), 'DEBIT_CARD', debit, is_fixed=True)
        entry('Language course', 'Curso de idiomas', '280', learning, _month(as_of, -10, 9),
              instrument=virtual, is_fixed=True, fixed_until=_month(as_of, -3, 9))
        entry('Professional course', 'Curso de aperfeiçoamento', '190', learning,
              _month(as_of, -1, 9), instrument=virtual, is_fixed=True, fixed_until=_month(as_of, 3, 9))

        for index, offset in enumerate(range(-12, 1)):
            # Current-month purchases may be scheduled later in the month; the
            # interface can therefore demonstrate both realized and forecast data.
            entry('Supermarket', 'Supermercado', str(Decimal('520.30') + index * Decimal('11.35')),
                  groceries, _month(as_of, offset, 6), 'DEBIT_CARD', debit)
            entry('Fresh produce', 'Feira da semana', str(Decimal('120.50') + (index % 4) * 13),
                  groceries, _month(as_of, offset, 20), 'PIX', checking)
            entry('Dinner with friends', 'Jantar com amigos', str(Decimal('164.90') + (index % 5) * 17),
                  dining, _month(as_of, offset, 14))
            entry('Electricity bill', 'Conta de energia', str(Decimal('180.45') + (index % 6) * 12),
                  utilities, _month(as_of, offset, 17), 'ACCOUNT', checking)
            entry('City transport', 'Transporte urbano', str(Decimal('210') + (index % 3) * 22),
                  transport, _month(as_of, offset, 11), 'PIX', checking)
            entry('Pet supplies', 'Cuidados com os animais', '148.90', pets,
                  _month(as_of, offset, 21), instrument=additional)
            if index % 3 == 0:
                entry('Design project', 'Projeto de design', '1350', freelance,
                      _month(as_of, offset, 19), 'PIX', checking, 'INCOME')
            create_transfer(user=user, source_account=checking, destination_account=goals,
                            source_amount=Decimal('300'), destination_amount=Decimal('300'),
                            date=_month(as_of, offset, 7), notes=label('Travel allocation', 'Reserva para viagem'))

        entry('Laptop in 10 installments', 'Notebook em 10 parcelas', '4799.99', technology,
              _month(as_of, -4, 16), installments=10)
        entry('Completed appliance purchase', 'Compra de eletrodoméstico concluída', '1800', housing,
              _month(as_of, -11, 13), installments=6, instrument=additional)
        entry('Holiday tickets', 'Passagens de férias', '2400', travel,
              _month(as_of, -1, 26), installments=4)
        entry('Online workshop: current bill', 'Oficina online: fatura atual', '89.90', learning,
              as_of, instrument=virtual, billing_override=Transaction.BillChoice.CURRENT)
        entry('Headphones: next bill', 'Fones: próxima fatura', '249.90', technology,
              as_of, instrument=virtual, billing_override=Transaction.BillChoice.NEXT)
        entry('Birthday gift', 'Presente de aniversário', '180', gifts, _month(as_of, -2, 10), 'PIX', checking)
        entry('Shared trip reimbursement', 'Reembolso de viagem compartilhada', '220', gifts,
              _month(as_of, -2, 14), 'ACCOUNT', checking, 'INCOME')
        entry('Museum tickets', 'Ingressos de museu', '35', travel, _month(as_of, -2, 18), 'ACCOUNT', euro)
        entry('International software', 'Software internacional', '24', technology,
              _month(as_of, -1, 12), 'ACCOUNT', global_account)
        entry('Next holiday booking', 'Reserva das próximas férias', '650', travel,
              _month(as_of, 1, 10), 'ACCOUNT', goals)

        for offset, destination, source_amount, target_amount in [
            (-6, savings, '1500', '1500'), (-4, global_account, '1000', '200'),
            (-2, euro, '550', '100'),
        ]:
            create_transfer(user=user, source_account=checking, destination_account=destination,
                            source_amount=Decimal(source_amount), destination_amount=Decimal(target_amount),
                            date=_month(as_of, offset, 9), notes=label('Goal funding', 'Aporte para objetivos'))

        program = _create(LoyaltyProgram, user=user, bank=primary,
                          name=label('Aurora Demo Miles', 'Milhas Aurora Demo'),
                          unit_name=label('Miles', 'Milhas'))
        program.cards.add(physical, virtual, additional)
        cashback = _create(LoyaltyProgram, user=user, name=label('Demo Cashback', 'Cashback Demo'),
                           unit_name=label('Points', 'Pontos'))

        def loyalty(target, direction, kind, amount, when, en, pt, **extra):
            item = _create(LoyaltyEntry, user=user, program=target, direction=direction,
                           kind=kind, amount=Decimal(amount), date=when, notes=label(en, pt), **extra)
            sync_loyalty_entry_funding(item)
            return item

        loyalty(program, 'CREDIT', 'ADJUSTMENT', '48000', _month(as_of, -12),
                'Fictional opening miles', 'Saldo inicial fictício de milhas')
        loyalty(cashback, 'CREDIT', 'ADJUSTMENT', '1800', _month(as_of, -6),
                'Fictional cashback balance', 'Saldo fictício de cashback')
        loyalty(program, 'CREDIT', 'PURCHASE', '3000', _month(as_of, -3, 12),
                'Miles purchased through account', 'Compra de milhas pela conta',
                funding_account=checking, cash_amount=Decimal('75'))
        loyalty(program, 'CREDIT', 'PURCHASE', '5000', _month(as_of, -1, 15),
                'Miles purchased by card', 'Compra de milhas no cartão',
                funding_credit_card=virtual, cash_amount=Decimal('120'))
        loyalty(program, 'DEBIT', 'EXPIRATION', '500', _month(as_of, -2, 28),
                'Expired promotional miles', 'Expiração de milhas promocionais')
        for offset, target, points, amount, iof, funding in [
            (-5, checking, '4000', '100', '0', {}),
            (-3, global_account, '6000', '50', '8.50', {'iof_account': checking}),
            (-1, global_account, '5000', '40', '6.80', {'iof_credit_card': physical}),
        ]:
            create_reward_redemption(user=user, program=program, points=Decimal(points),
                                     target_account=target, target_amount=Decimal(amount),
                                     date=_month(as_of, offset, 19), iof_amount=Decimal(iof),
                                     notes=label('Demonstration redemption', 'Resgate de demonstração'), **funding)

        sync_user_ledger(user, through_date=as_of)
        invoice = user.card_invoices.filter(card=physical, due_date__lte=as_of).order_by('-due_date').first()
        loyalty(program, 'CREDIT', 'INVOICE_AWARD', '1250', invoice.due_date,
                'Points earned on a paid bill', 'Pontos recebidos de fatura paga', invoice=invoice)
        seed_investments_and_drafts(
            user=user, language=language, as_of=as_of, checking=checking, savings=savings,
            global_account=global_account, primary_bank=primary, global_bank=global_bank, program=program,
        )
        return user
