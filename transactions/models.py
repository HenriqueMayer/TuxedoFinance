from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from categories.models import Category
from payments.models import PaymentMethod

ZERO = Decimal('0.00')


class Transaction(models.Model):
    """A single cash flow record owned by a user (PRD §8.3, FR07).

    `amount` is always stored positive (PRD §8.5) — whether it increases or
    decreases the balance is derived purely from `transaction_type`, never
    from the sign of the stored value. `category` and `payment_method` use
    `on_delete=PROTECT`: an in-use category/payment method cannot be deleted
    (the owning DeleteViews must catch `ProtectedError`). `created_at` is
    immutable; `transaction_date` is the only user-editable date.

    `installments` only applies to credit card payments (`TransactionForm`
    enforces that); `amount` always stores the **full total**, never the value
    of a single installment. When a transaction affects the balance is decided
    by `amount_for_month`, not by `transaction_date` alone: a fixed transaction
    repeats every month, an installment plan spreads over consecutive months,
    and everything else lands once on its own month.

    A fixed transaction runs from `transaction_date` until `fixed_until`
    (inclusive, by month), or forever when `fixed_until` is empty. This is how
    history survives a change: a raise is **two rows** — the old salary ended
    in the month it last paid, and a new row starting the month after — not an
    edit to the single row, which would retroactively rewrite every month it
    ever covered.
    """

    MAX_INSTALLMENTS = 48

    class TransactionType(models.TextChoices):
        INCOME = 'INCOME', 'Income'
        EXPENSE = 'EXPENSE', 'Expense'
        INVESTMENT = 'INVESTMENT', 'Investment'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    title = models.CharField(max_length=150)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='transactions',
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name='transactions',
    )
    installments = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_INSTALLMENTS)],
    )
    is_fixed = models.BooleanField(default=False)
    # Last month a fixed transaction pays out (inclusive). Null = open-ended,
    # which is the right default: most fixed transactions have no known end.
    fixed_until = models.DateField(null=True, blank=True)
    transaction_date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_date', '-created_at']

    def __str__(self):
        return f'{self.title} ({self.get_transaction_type_display()})'

    @property
    def is_installment_plan(self):
        """True when this transaction is split into more than one installment."""
        return self.installments > 1

    @property
    def installment_amount(self):
        """Value of a single installment (`amount` is always the full total).

        Rounded to the cent, so `installment_amount * installments` may fall a
        cent or two short of `amount` (100.00 in 3x → 33.33). The shortfall is
        never lost: `amount_for_month` gives it to the final installment, so
        the occurrences always re-sum to exactly `amount`.
        """
        if not self.is_installment_plan:
            return self.amount
        return (self.amount / self.installments).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def months_from_start(self, year, month):
        """Whole months from this transaction's own month to (`year`, `month`).

        Negative when the target month precedes the transaction.
        """
        return (year - self.transaction_date.year) * 12 + (
            month - self.transaction_date.month
        )

    @property
    def last_fixed_offset(self):
        """Offset of the final month a fixed transaction pays, or `None`.

        `None` means open-ended. A `fixed_until` earlier than the start month
        clamps to 0 rather than going negative: the form rejects that combination,
        but a fixture or data migration could still produce it, and one payment
        is a saner reading of it than a negative number of payments.
        """
        if not self.is_fixed or self.fixed_until is None:
            return None
        return max(
            0, self.months_from_start(self.fixed_until.year, self.fixed_until.month)
        )

    def amount_for_month(self, year, month):
        """How much this transaction adds to (`year`, `month`) — PRD §8.5.

        Three recurrence shapes, mutually exclusive by `TransactionForm.clean`:
          - fixed        → `amount`, every month from its own month until
                           `fixed_until` (inclusive), or forever if unset;
          - installments → one installment per month, for `installments` months;
          - one-off      → `amount`, in its own month only.
        """
        offset = self.months_from_start(year, month)
        if offset < 0:
            return ZERO

        if self.is_fixed:
            last_offset = self.last_fixed_offset
            if last_offset is not None and offset > last_offset:
                return ZERO
            return self.amount

        if self.is_installment_plan:
            if offset >= self.installments:
                return ZERO
            if offset == self.installments - 1:
                # Final installment absorbs the rounding remainder, so the
                # plan's occurrences add up to exactly `amount`.
                return self.amount - self.installment_amount * (self.installments - 1)
            return self.installment_amount

        return self.amount if offset == 0 else ZERO

    def amount_through_month(self, year, month):
        """Cumulative contribution from the start through (`year`, `month`).

        Equivalent to summing `amount_for_month` over every month up to the
        target, but in constant time — this is what the running balances use.
        """
        offset = self.months_from_start(year, month)
        if offset < 0:
            return ZERO

        if self.is_fixed:
            last_offset = self.last_fixed_offset
            if last_offset is not None:
                offset = min(offset, last_offset)
            return self.amount * (offset + 1)

        if self.is_installment_plan:
            paid = min(offset + 1, self.installments)
            if paid == self.installments:
                return self.amount
            return self.installment_amount * paid

        return self.amount
