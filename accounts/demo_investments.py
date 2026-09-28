# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic investment history and saved planning examples for opt-in demos."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.http import QueryDict

from accounts.models import UserPreference
from investments.models import Asset, Investment, InvestmentProduct
from investments.services import refresh_fx_snapshot, sync_investment_ledger
from sandbox.forms import SalarySandboxForm, YieldSimulationForm
from sandbox.models import ScenarioDraft
from sandbox.planning import commitment_snapshot, simulate_yield, snapshot_total
from sandbox.tax_rules import get_tax_rules


COPY = {
    'en': {
        'portfolio': 'Long-term portfolio',
        'global_portfolio': 'International portfolio',
        'cash_product': 'Monthly cash pots',
        'cash_asset': 'Monthly bills reserve',
        'fixed_asset': 'Demo fixed-income bond',
        'currency_asset': 'Dollar reserve',
        'crypto_asset': 'Demo digital asset',
        'equity_asset': 'Demo global equity fund',
        'other_asset': 'Demo alternative fund',
        'monthly_investment': 'Monthly long-term contribution',
        'cash_deposit': 'Keep monthly funds earning yield before paying bills',
        'cash_withdrawal': 'Return monthly funds to the everyday account',
        'yield': 'Recorded synthetic internal yield',
        'international': 'Monthly international diversification',
        'points': 'Convert loyalty points into a long-term position',
        'cross_currency': 'Buy a dollar-denominated asset using the BRL account',
        'withdrawal': 'Partial withdrawal for a planned goal',
        'notes': 'Fictional demonstration values; these are not market quotes.',
        'budget_current': 'Current month: balanced plan',
        'budget_alternative': 'Current month: higher salary scenario',
        'emergency': 'Emergency reserve',
        'investment': 'Additional investment',
        'travel': 'Travel goal',
        'yield_draft': 'Two-year savings goal with a planned withdrawal',
    },
    'pt': {
        'portfolio': 'Carteira de longo prazo',
        'global_portfolio': 'Carteira internacional',
        'cash_product': 'Cofrinhos do mês',
        'cash_asset': 'Reserva para as contas do mês',
        'fixed_asset': 'Título de renda fixa demonstrativo',
        'currency_asset': 'Reserva em dólares',
        'crypto_asset': 'Ativo digital demonstrativo',
        'equity_asset': 'Fundo global de ações demonstrativo',
        'other_asset': 'Fundo alternativo demonstrativo',
        'monthly_investment': 'Aporte mensal de longo prazo',
        'cash_deposit': 'Deixar os recursos do mês rendendo antes de pagar as contas',
        'cash_withdrawal': 'Devolver os recursos do mês à conta do dia a dia',
        'yield': 'Rendimento interno sintético registrado',
        'international': 'Diversificação internacional mensal',
        'points': 'Converter pontos em uma posição de longo prazo',
        'cross_currency': 'Comprar ativo em dólares usando a conta em reais',
        'withdrawal': 'Resgate parcial para um objetivo planejado',
        'notes': 'Valores fictícios de demonstração; não são cotações de mercado.',
        'budget_current': 'Mês atual: plano equilibrado',
        'budget_alternative': 'Mês atual: cenário com salário maior',
        'emergency': 'Reserva de emergência',
        'investment': 'Investimento adicional',
        'travel': 'Objetivo de viagem',
        'yield_draft': 'Objetivo de dois anos com resgate planejado',
    },
}


def _month(value: date, offset: int, day: int = 1) -> date:
    index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day, monthrange(year, month)[1]))


def _save(model, **values):
    record = model(**values)
    record.full_clean()
    record.save()
    return record


def _operation(**values):
    operation = _save(Investment, **values)
    refresh_fx_snapshot(operation)
    sync_investment_ledger(operation)
    return operation


def _draft(*, user, name, kind, inputs, snapshot=None):
    """Keep demo payloads aligned with the forms without making HTTP requests."""
    data = QueryDict(mutable=True)
    for key, values in inputs.items():
        data.setlist(key, values)
    form = (SalarySandboxForm if kind == ScenarioDraft.Kind.BUDGET else YieldSimulationForm)(data)
    if not form.is_valid():
        raise ValidationError(form.errors)
    cleaned = form.cleaned_data
    if kind == ScenarioDraft.Kind.BUDGET:
        snapshot_total(snapshot, cleaned['planning_month'].strftime('%Y-%m'))
    else:
        simulate_yield(
            initial=cleaned['initial_balance'], start_month=cleaned['start_month'],
            months=cleaned['months'], rate=cleaned['rate'], rate_period=cleaned['rate_period'],
            contribution=cleaned['contribution'], withdrawal=cleaned['withdrawal'],
            overrides=cleaned['overrides'],
        )
    return _save(
        ScenarioDraft, user=user, name=name, kind=kind,
        payload={
            'schema_version': 1,
            'calculation_version': 2 if kind == ScenarioDraft.Kind.BUDGET else 1,
            'input_format': {
                'date_order': UserPreference.for_user(user).date_format,
                'month': 'YYYY-MM', 'decimal': '.',
            },
            'inputs': inputs, 'snapshot': snapshot, 'complete': True,
            'tax_rule_year': get_tax_rules().year,
        },
    )


def seed_investments_and_drafts(
    *, user, language, as_of, checking, savings, global_account,
    primary_bank, global_bank, program,
):
    """Populate a new demo owner inside the caller's atomic, localized context.

    Accounts use BRL/BRL/USD respectively. Transactions, loyalty funding and
    exchange rates must exist first so saved plans capture the full demo month.
    """
    labels = COPY[language]
    portfolio = _save(
        InvestmentProduct, user=user, bank=primary_bank, name=labels['portfolio'],
        purpose=InvestmentProduct.Purpose.INVESTMENT,
    )
    global_portfolio = _save(
        InvestmentProduct, user=user, bank=global_bank, name=labels['global_portfolio'],
        purpose=InvestmentProduct.Purpose.INVESTMENT,
    )
    cash_product = _save(
        InvestmentProduct, user=user, bank=primary_bank, name=labels['cash_product'],
        purpose=InvestmentProduct.Purpose.MONTHLY_CASH,
    )
    cash = _save(
        Asset, user=user, name=labels['cash_asset'], code='DEMO-CASH',
        asset_class=Asset.AssetClass.LIQUIDITY, currency='BRL',
        valuation_mode=Asset.ValuationMode.MONETARY,
        opening_balance=Decimal('2400.00'), opening_product=cash_product,
    )
    fixed = _save(
        Asset, user=user, name=labels['fixed_asset'], code='DEMO-FIXED',
        asset_class=Asset.AssetClass.FIXED_INCOME, currency='BRL',
        valuation_mode=Asset.ValuationMode.MONETARY,
        opening_balance=Decimal('6000.00'), opening_product=portfolio,
    )
    currency = _save(
        Asset, user=user, name=labels['currency_asset'], code='DEMO-USD',
        asset_class=Asset.AssetClass.CURRENCY, currency='USD',
        valuation_mode=Asset.ValuationMode.MONETARY,
        opening_balance=Decimal('250.00'), opening_product=global_portfolio,
    )
    crypto = _save(
        Asset, user=user, name=labels['crypto_asset'], code='DEMO-CRYPTO',
        asset_class=Asset.AssetClass.CRYPTO, currency='USD',
        valuation_mode=Asset.ValuationMode.UNITS,
        opening_quantity=Decimal('2.00000000'),
        opening_unit_price=Decimal('90.00000000'), opening_product=global_portfolio,
    )
    equity = _save(
        Asset, user=user, name=labels['equity_asset'], code='DEMO-EQUITY',
        asset_class=Asset.AssetClass.EQUITY, currency='USD',
        valuation_mode=Asset.ValuationMode.UNITS,
        opening_quantity=Decimal('12.00000000'),
        opening_unit_price=Decimal('50.00000000'), opening_product=global_portfolio,
    )
    alternative = _save(
        Asset, user=user, name=labels['other_asset'], code='DEMO-OTHER',
        asset_class=Asset.AssetClass.OTHER, currency='BRL',
        valuation_mode=Asset.ValuationMode.UNITS,
        opening_quantity=Decimal('10.00000000'),
        opening_unit_price=Decimal('40.00000000'), opening_product=portfolio,
    )

    for offset in range(-11, 1):
        index = offset + 11
        # In the current month, all sample operations remain effective as of
        # insertion, including when a profile is created on the first day.
        deposit_date = min(_month(as_of, offset, 7), as_of)
        yield_date = min(_month(as_of, offset, 18), as_of)
        withdrawal_date = min(_month(as_of, offset, 23), as_of)
        _operation(
            user=user, product=cash_product, asset=cash, kind=Investment.Kind.DEPOSIT,
            amount=Decimal('650.00'), cash_amount=Decimal('650.00'),
            source_account=checking, date=deposit_date, reason=labels['cash_deposit'],
        )
        _operation(
            user=user, product=cash_product, asset=cash, kind=Investment.Kind.YIELD,
            amount=Decimal('18.00') + Decimal(index), date=yield_date, reason=labels['yield'],
        )
        _operation(
            user=user, product=cash_product, asset=cash, kind=Investment.Kind.WITHDRAWAL,
            amount=Decimal('450.00'), cash_amount=Decimal('450.00'),
            destination_account=checking, date=withdrawal_date, reason=labels['cash_withdrawal'],
        )
        _operation(
            user=user, product=portfolio, asset=fixed, kind=Investment.Kind.DEPOSIT,
            amount=Decimal('250.00'), cash_amount=Decimal('250.00'),
            source_account=savings, date=deposit_date, reason=labels['monthly_investment'],
        )
        _operation(
            user=user, product=portfolio, asset=fixed, kind=Investment.Kind.YIELD,
            amount=Decimal('35.00') + Decimal(index), date=yield_date, reason=labels['yield'],
        )
        price = Decimal('55.00') + Decimal(index)
        _operation(
            user=user, product=global_portfolio, asset=equity, kind=Investment.Kind.DEPOSIT,
            quantity=Decimal('1.00000000'), unit_price=price,
            cash_amount=price + Decimal('0.50'), fees=Decimal('0.50'),
            source_account=global_account, date=deposit_date,
            reason=labels['international'], notes=labels['notes'],
        )

    _operation(
        user=user, product=portfolio, asset=alternative, kind=Investment.Kind.DEPOSIT,
        quantity=Decimal('5.00000000'), unit_price=Decimal('42.00000000'),
        source_program=program, source_points=Decimal('7000.00'),
        date=_month(as_of, -5, 15), reason=labels['points'],
    )
    _operation(
        user=user, product=global_portfolio, asset=crypto, kind=Investment.Kind.DEPOSIT,
        quantity=Decimal('0.50000000'), unit_price=Decimal('110.00000000'),
        cash_amount=Decimal('291.50'), source_account=checking,
        date=_month(as_of, -4, 12), reason=labels['cross_currency'], notes=labels['notes'],
    )
    _operation(
        user=user, product=global_portfolio, asset=crypto, kind=Investment.Kind.YIELD,
        quantity=Decimal('0.02000000'), unit_price=Decimal('115.00000000'),
        date=_month(as_of, -2, 14), reason=labels['yield'], notes=labels['notes'],
    )
    _operation(
        user=user, product=global_portfolio, asset=currency, kind=Investment.Kind.DEPOSIT,
        amount=Decimal('100.00'), cash_amount=Decimal('100.00'),
        source_account=global_account, date=_month(as_of, -3, 11),
        reason=labels['international'],
    )
    _operation(
        user=user, product=global_portfolio, asset=currency, kind=Investment.Kind.YIELD,
        amount=Decimal('2.35'), date=_month(as_of, -1, 20), reason=labels['yield'],
    )
    _operation(
        user=user, product=global_portfolio, asset=equity, kind=Investment.Kind.WITHDRAWAL,
        quantity=Decimal('2.00000000'), unit_price=Decimal('64.00000000'),
        cash_amount=Decimal('127.00'), fees=Decimal('1.00'),
        destination_account=global_account, date=_month(as_of, -1, 24),
        reason=labels['withdrawal'], notes=labels['notes'],
    )
    _operation(
        user=user, product=portfolio, asset=fixed, kind=Investment.Kind.WITHDRAWAL,
        amount=Decimal('600.00'), cash_amount=Decimal('600.00'),
        destination_account=savings, date=_month(as_of, -2, 22), reason=labels['withdrawal'],
    )

    month = as_of.replace(day=1)
    snapshot = commitment_snapshot(user, month, month_basis='reference_month')
    for title, salary, reserve, travel in (
        ('budget_current', '9500.00', '5.00', '150.00'),
        ('budget_alternative', '11000.00', '8.00', '300.00'),
    ):
        _draft(
            user=user, name=labels[title], kind=ScenarioDraft.Kind.BUDGET,
            snapshot=snapshot,
            inputs={
                'planning_month': [month.strftime('%Y-%m')], 'gross_salary': [salary],
                'clt_dependents': ['1'], 'clt_pension': ['0.00'],
                'clt_transport': ['180.00'], 'clt_food': ['60.00'],
                'clt_health': ['90.00'], 'clt_other': ['0.00'],
                'variable_label': [labels['emergency'], labels['investment'], labels['travel']],
                'variable_type': ['percent', 'currency', 'currency'],
                'variable_value': [reserve, '250.00', travel],
            },
        )
    _draft(
        user=user, name=labels['yield_draft'], kind=ScenarioDraft.Kind.YIELD,
        inputs={
            'currency': ['BRL'], 'start_month': [month.strftime('%Y-%m')],
            'months': ['24'], 'initial_balance': ['5000.00'],
            'rate': ['9.000000'], 'rate_period': ['annual'],
            'contribution': ['500.00'], 'withdrawal': ['0.00'],
            'contribution_5': ['1000.00'], 'contribution_11': ['0.00'],
            'withdrawal_11': ['1500.00'],
        },
    )
