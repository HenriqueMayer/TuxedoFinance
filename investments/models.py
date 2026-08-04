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
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.currencies import CURRENCIES


class Investment(models.Model):
    """One deposit or withdrawal against the user's investment portfolio.

    `amount` is always positive (matches the `Transaction` rule of
    `MinValueValidator(Decimal('0.01'))` + always-positive storage; the sign
    comes from `kind`, never from the stored number). `kind` is the only
    thing that decides whether this row adds to or subtracts from the
    portfolio's running balance.

    `currency` is the currency `amount` is denominated in. It defaults to
    `settings.CURRENCY` so rows recorded before multi-currency support was
    added keep their value in the base currency without a manual migration
    step. Entries in a different currency are stored as-is; the conversion
    to the base happens on read, using the most recent `ExchangeRate` for
    that pair (`investments.services.get_latest_rates`).

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
    # ISO 4217 code, validated against the project-wide `core.currencies`
    # registry. The TextChoices below is built dynamically so adding a
    # currency in `core/currencies.py` is the only place the list is
    # defined — exactly how `Transaction.transaction_type` and
    # `PaymentMethod.method_type` already work.
    currency = models.CharField(
        max_length=3,
        choices=[(code, currency.name) for code, currency in CURRENCIES.items()],
        default=settings.CURRENCY,
    )
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.title} ({self.get_kind_display()}, {self.currency})'

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


class ExchangeRate(models.Model):
    """A manual exchange rate the user wants to apply to investments.

    Stores one rate per `(user, from_currency, to_currency)` pair, timestamped
    by `effective_date`. The list view uses the most recent row per pair as
    the "current" rate, and the simulated-total computation reads from the
    same lookup. Rows are append-only by design: if the rate moved, the user
    creates a new row with a newer `effective_date`; the old one stays put
    for history (and is what an automated feed would later be reconciled
    against, when one exists).

    `to_currency` is always `settings.CURRENCY` in this app — the form
    hardcodes it on the way in — but the column itself is generic so the
    model can be repurposed for arbitrary pairs if a future feature needs
    that without a schema change.

    `rate` is stored as `Decimal(18, 8)` to cover exotic pairs (crypto) where
    the rate might be 0.00000123. 8 decimal places is the standard precision
    used by FX APIs; bump if a real feed ever needs more.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exchange_rates',
    )
    from_currency = models.CharField(
        max_length=3,
        choices=[(code, currency.name) for code, currency in CURRENCIES.items()],
    )
    to_currency = models.CharField(
        max_length=3,
        choices=[(code, currency.name) for code, currency in CURRENCIES.items()],
    )
    rate = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))],
    )
    effective_date = models.DateField()
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        constraints = [
            # Append-only over time: a user can have many rows for the same
            # pair, but never two with the same `effective_date` (a duplicate
            # date would be ambiguous — which one is "the" rate on that
            # day?). When an automated feed lands, it will write one row per
            # day per pair; the existing rows are its history.
            models.UniqueConstraint(
                fields=['user', 'from_currency', 'to_currency', 'effective_date'],
                name='unique_rate_per_pair_date_per_user',
            ),
        ]

    def __str__(self):
        return (
            f'1 {self.from_currency} = {self.rate} {self.to_currency} '
            f'(as of {self.effective_date})'
        )
