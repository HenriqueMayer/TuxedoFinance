"""What the owner intends: spending limits and goals. These records never move money."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from config.currencies import CURRENCIES, DEFAULT_CURRENCY

CURRENCY_CHOICES = [(code, code) for code in CURRENCIES]
POSITIVE = MinValueValidator(Decimal("0.01"))


class SpendingLimit(models.Model):
    """What the owner intends to spend in each month, from ``start_month`` on.

    Without a category, it is the limit of the month. With a category, it is
    the budget of that category and of its subcategories. A row holds until a
    later row of the same category. An empty ``amount`` ends the limit from
    ``start_month`` on. The amount is in the currency of totals.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    category = models.ForeignKey(
        "ledger.Category", on_delete=models.CASCADE, null=True, blank=True, related_name="limits"
    )
    start_month = models.DateField()
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True, validators=[POSITIVE]
    )

    class Meta:
        ordering = ["start_month", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "start_month"],
                condition=models.Q(category__isnull=True),
                name="planning_one_month_limit",
            ),
            models.UniqueConstraint(
                fields=["user", "category", "start_month"],
                condition=models.Q(category__isnull=False),
                name="planning_one_category_limit",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__isnull=True) | models.Q(amount__gt=0),
                name="planning_limit_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(start_month__day=1), name="planning_limit_first_day"
            ),
        ]

    def __str__(self):
        return f"{self.category or 'Month'} · {self.start_month:%Y-%m} · {self.amount}"

    def clean(self):
        errors = {}
        if self.start_month and self.start_month.day != 1:
            errors["start_month"] = _("Choose the first day of a month.")
        if self.category_id and self.user_id:
            if self.category.user_id != self.user_id:
                errors["category"] = _("Choose one of your own records.")
            elif self.category.transaction_type == "INCOME":
                errors["category"] = _("A budget cannot use an income category.")
        if errors:
            raise ValidationError(errors)


class FinancialGoal(models.Model):
    """An amount that the owner wants to hold, with an optional date."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE])
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY)
    target_date = models.DateField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_archived", "target_date", "name", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(target_amount__gt=0), name="planning_goal_positive"
            ),
        ]

    def __str__(self):
        return self.name


class GoalAllocation(models.Model):
    """A part of one balance that the owner reserves for a goal.

    The source is a bank account or a balance investment (an asset valued in
    money). The amount is in the currency of the source. A goal has one
    reservation for each source.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    goal = models.ForeignKey(FinancialGoal, on_delete=models.CASCADE, related_name="allocations")
    bank_account = models.ForeignKey(
        "banking.BankAccount",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="goal_allocations",
    )
    asset = models.ForeignKey(
        "investments.Asset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="goal_allocations",
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[POSITIVE])

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="planning_allocation_positive"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(bank_account__isnull=False, asset__isnull=True)
                    | models.Q(bank_account__isnull=True, asset__isnull=False)
                ),
                name="planning_allocation_one_source",
            ),
            models.UniqueConstraint(
                fields=["goal", "bank_account"],
                condition=models.Q(bank_account__isnull=False),
                name="planning_unique_goal_account",
            ),
            models.UniqueConstraint(
                fields=["goal", "asset"],
                condition=models.Q(asset__isnull=False),
                name="planning_unique_goal_asset",
            ),
        ]

    @property
    def source_key(self):
        if self.bank_account_id:
            return f"account:{self.bank_account_id}"
        return f"investment:{self.asset_id}"

    def clean(self):
        errors = {}
        if self.goal_id and self.user_id and self.goal.user_id != self.user_id:
            errors["goal"] = _("Choose one of your own records.")
        if bool(self.bank_account_id) == bool(self.asset_id):
            errors["bank_account"] = _("Choose one account or one balance investment.")
        elif self.bank_account_id and self.bank_account.user_id != self.user_id:
            errors["bank_account"] = _("Choose one of your own records.")
        elif self.asset_id and self.asset.user_id != self.user_id:
            errors["asset"] = _("Choose one of your own records.")
        elif self.asset_id and self.asset.valuation_mode != "MONETARY":
            errors["asset"] = _("A goal can reserve a balance, not units.")
        if errors:
            raise ValidationError(errors)


class SavedSheet(models.Model):
    """A named set of changes for the sheet of the months ahead.

    ``changes`` holds the changed cells and the added rows
    (``planning.sheet``). The recorded values are not stored: an opened sheet
    reads them again, so it follows the records.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    months = models.PositiveSmallIntegerField(default=6)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def __str__(self):
        return self.name


class MonthClosing(models.Model):
    """A month that the owner reviewed and closed.

    ``income`` and ``expenses`` are the totals that the owner saw, in
    ``currency``. A later difference shows that the month changed since. The
    record locks nothing.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    month = models.DateField()
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=DEFAULT_CURRENCY)
    income = models.DecimalField(max_digits=16, decimal_places=2)
    expenses = models.DecimalField(max_digits=16, decimal_places=2)
    closed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(fields=["user", "month"], name="planning_one_closing_a_month"),
            models.CheckConstraint(
                condition=models.Q(month__day=1), name="planning_closing_first_day"
            ),
        ]

    def __str__(self):
        return f"{self.month:%Y-%m}"
