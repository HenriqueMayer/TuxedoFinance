# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit plans and review decisions; these records never create money."""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.currencies import CURRENCIES

ZERO = Decimal('0.00')
CURRENCY_CHOICES = [(code, code) for code in CURRENCIES]
POSITIVE = MinValueValidator(Decimal('0.01'))


class OwnedPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CategoryBudget(OwnedPlan):
    category = models.ForeignKey('categories.Category', on_delete=models.PROTECT, related_name='budgets')
    month = models.DateField(verbose_name=_('Month'))
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='BRL')
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE], verbose_name=_('Budget limit'))

    class Meta:
        ordering = ['month', 'category__name', 'currency']
        constraints = [
            models.UniqueConstraint(fields=['user', 'category', 'month', 'currency'], name='planning_unique_category_budget'),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='planning_budget_positive'),
        ]

    def __str__(self):
        return f'{self.category} · {self.month:%Y-%m} · {self.currency}'

    def clean(self):
        errors = {}
        if self.month and (self.month.day != 1 or not 1901 <= self.month.year <= 9988):
            errors['month'] = _('Select a month between 1901 and 9988.')
        if self.category_id and self.user_id:
            if self.category.user_id != self.user_id:
                errors['category'] = _('Select a category that belongs to you.')
            elif self.category.transaction_type == 'INCOME':
                errors['category'] = _('Expense budgets cannot use an income category.')
            elif self.month:
                # Ancestors and descendants cover the same expenses; reject
                # overlapping limits even when the categories are several levels apart.
                from planning.services import category_family
                overlapping = category_family(self.user, self.category_id)
                if CategoryBudget.objects.filter(
                    user_id=self.user_id, month=self.month, currency=self.currency,
                    category_id__in=overlapping,
                ).exclude(pk=self.pk).exists():
                    errors['category'] = _('A budget for this category, an ancestor or a descendant already exists in this month and currency.')
        if errors:
            raise ValidationError(errors)


class FinancialGoal(OwnedPlan):
    name = models.CharField(max_length=120, verbose_name=_('Name'))
    target_amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE], verbose_name=_('Target amount'))
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='BRL', verbose_name=_('Target currency'))
    target_date = models.DateField(null=True, blank=True, verbose_name=_('Target date'))
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['is_archived', 'target_date', 'name', 'pk']
        constraints = [models.CheckConstraint(condition=models.Q(target_amount__gt=0), name='planning_goal_positive')]

    def __str__(self):
        return self.name


class GoalAllocation(OwnedPlan):
    goal = models.ForeignKey(FinancialGoal, on_delete=models.CASCADE, related_name='allocations')
    bank_account = models.ForeignKey('banking.BankAccount', on_delete=models.PROTECT, null=True, blank=True, related_name='goal_allocations')
    product = models.ForeignKey('investments.InvestmentProduct', on_delete=models.PROTECT, null=True, blank=True, related_name='goal_allocations')
    asset = models.ForeignKey('investments.Asset', on_delete=models.PROTECT, null=True, blank=True, related_name='goal_allocations')
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE], verbose_name=_('Reserved amount'))

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='planning_allocation_positive'),
            models.CheckConstraint(condition=(
                models.Q(bank_account__isnull=False, product__isnull=True, asset__isnull=True)
                | models.Q(bank_account__isnull=True, product__isnull=False, asset__isnull=False)
            ), name='planning_allocation_one_source'),
            models.UniqueConstraint(fields=['goal', 'bank_account'], condition=models.Q(bank_account__isnull=False), name='planning_unique_goal_account'),
            models.UniqueConstraint(fields=['goal', 'product', 'asset'], condition=models.Q(product__isnull=False), name='planning_unique_goal_cashpot'),
        ]

    @property
    def source_key(self):
        return f'account:{self.bank_account_id}' if self.bank_account_id else f'pot:{self.product_id}:{self.asset_id}'

    @property
    def source_currency(self):
        return self.bank_account.currency if self.bank_account_id else self.asset.currency

    @property
    def source_label(self):
        return str(self.bank_account) if self.bank_account_id else f'{self.product} · {self.asset}'

    def clean(self):
        errors = {}
        if self.goal_id and self.user_id and self.goal.user_id != self.user_id:
            errors['goal'] = _('Select a goal that belongs to you.')
        if self.bank_account_id:
            if self.bank_account.user_id != self.user_id:
                errors['bank_account'] = _('Select an account that belongs to you.')
            if self.product_id or self.asset_id:
                errors['bank_account'] = _('Select exactly one source for this reservation.')
        elif self.product_id and self.asset_id:
            if self.product.user_id != self.user_id or self.asset.user_id != self.user_id:
                errors['product'] = _('Select a cash pot that belongs to you.')
            if self.product.purpose != 'MONTHLY_CASH' or self.asset.valuation_mode != 'MONETARY':
                errors['product'] = _('Goals can reserve bank balances or monetary cash pots.')
        else:
            errors['bank_account'] = _('Select a bank account or a monetary cash pot.')
        if errors:
            raise ValidationError(errors)


class SignalSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='planning_signal_settings')
    duplicates_enabled = models.BooleanField(default=True, verbose_name=_('Possible duplicate transactions'))
    subscriptionincrease_enabled = models.BooleanField(default=True, verbose_name=_('Possible subscription increases'))
    budgetoverspend_enabled = models.BooleanField(default=True, verbose_name=_('Budget limits'))
    futurecashshortage_enabled = models.BooleanField(default=True, verbose_name=_('Projected bank cash shortages'))
    duplicate_days = models.PositiveSmallIntegerField(default=3, validators=[MaxValueValidator(14)], verbose_name=_('Duplicate window (days)'))
    subscription_increase_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('10.00'), validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('9999.99'))], verbose_name=_('Minimum increase (%)'))
    forecast_days = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(90)], verbose_name=_('Cash forecast horizon (days)'))


class SignalDecision(OwnedPlan):
    class Action(models.TextChoices):
        ACKNOWLEDGED = 'ACK', _('Acknowledged')
        DISMISSED = 'DISMISS', _('Dismissed')

    key = models.CharField(max_length=100)
    action = models.CharField(max_length=10, choices=Action.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'key'], name='planning_unique_signal_decision')]
