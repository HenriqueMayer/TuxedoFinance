# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Snapshots coverage for accounts."""

from django.contrib.auth import get_user_model
from accounts.models import UserPreference
from banking.models import Bank, BankAccount, BankMovement, BankTransfer, CardInvoice, CreditCard, DebitCard, ExchangeRate, InvoicePayment, LoyaltyEntry, LoyaltyProgram, RewardRedemption
from categories.models import Category
from investments.models import Asset, Investment, InvestmentProduct, PriceObservation
from planning.models import CategoryBudget, FinancialGoal, GoalAllocation, SignalDecision, SignalSettings
from sandbox.models import ScenarioDraft
from transactions.models import Transaction


User = get_user_model()


OWNED_MODELS = (
    UserPreference, Bank, BankAccount, DebitCard, CreditCard, CardInvoice,
    BankTransfer, BankMovement, LoyaltyProgram, LoyaltyEntry, RewardRedemption,
    ExchangeRate, Category, Transaction, InvestmentProduct, Asset, Investment,
    ScenarioDraft, InvoicePayment, PriceObservation, CategoryBudget, FinancialGoal,
    GoalAllocation, SignalSettings, SignalDecision,
)


def record_snapshot(user=None):
    """Capture values, timestamps and card memberships to detect unwanted edits."""
    snapshot = {}
    for model in (User, *OWNED_MODELS):
        rows = model.objects.all()
        if user is not None:
            rows = rows.filter(pk=user.pk) if model is User else rows.filter(user=user)
        snapshot[model._meta.label] = list(rows.order_by('pk').values())
    memberships = LoyaltyProgram.cards.through.objects.all()
    if user is not None:
        memberships = memberships.filter(loyaltyprogram__user=user)
    snapshot['loyalty_cards'] = list(memberships.order_by('pk').values())
    return snapshot
