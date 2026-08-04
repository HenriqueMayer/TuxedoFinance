"""Investments — a parallel log of money moved to/from investments.

Deliberately isolated from the `Transaction` universe: the `Transaction` model
already has a `TransactionType.INVESTMENT` choice, but that only marks a cash
outflow — it has no idea *which* investment the money went into, what
institution holds it, or what the running balance looks like. This app is the
manual log where the user records deposits and withdrawals against their
investment portfolio. The two are kept in sync by the user (the `?kind=` and
`reason` fields exist to make that explicit), and the model never references
`Transaction` — so this app can be deleted, reseeded, or diverged from the
transaction log without breaking either side.
"""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from decimal import Decimal


class Investment(models.Model):
    """One deposit or withdrawal against the user's investment portfolio.

    `amount` is always positive (matches the `Transaction` rule of
    `MinValueValidator(Decimal('0.01'))` + always-positive storage; the sign
    comes from `kind`, never from the stored number). `kind` is the only
    thing that decides whether this row adds to or subtracts from the
    portfolio's running balance.

    `reason` is free-form text — it answers "why did this money move?" in a
    way the structured fields do not. The withdrawal case in particular wants
    a record of *why* the user took money out (an emergency, a planned
    rebalance, a goal reaching its target) so future reads of the log can
    answer that without the user's memory.

    `date` is the only date the user edits — when the move actually happened
    in real life. `created_at`/`updated_at` are system-managed.

    No FK to `Transaction`. By design (see module docstring): this is a
    parallel universe the user keeps in sync manually.
    """

    class Kind(models.TextChoices):
        DEPOSIT = 'DEPOSIT', 'Deposit'
        WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investments',
    )
    title = models.CharField(max_length=150)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.title} ({self.get_kind_display()})'

    @property
    def signed_amount(self):
        """The amount with the sign that matches its effect on the balance.

        Deposits are positive (money in), withdrawals negative (money out).
        Used by the list view's `current_balance` calculation and by anything
        else that needs the row's contribution to the running total.
        """
        if self.kind == self.Kind.WITHDRAWAL:
            return -self.amount
        return self.amount
