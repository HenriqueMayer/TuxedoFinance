from calendar import monthrange

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PaymentMethod(models.Model):
    """A user-defined payment method used to record transactions (PRD §8.3).

    `method_type` classifies the method into one of the four PRD §8.4
    options; `name` is a free-form label (e.g. "Nubank Credit", "PIX").

    A credit card may also carry a **billing cycle**. `best_purchase_day` is
    what makes a purchase leave the account in a later month than it was made;
    `due_day` is a note about which day of that month the bill is paid and
    never moves money on its own. `statement_offset` is the whole rule;
    everything else in the project reads it through
    `Transaction.months_from_start`.
    """

    class MethodType(models.TextChoices):
        CREDIT_CARD = 'CREDIT_CARD', 'Credit Card'
        DEBIT_CARD = 'DEBIT_CARD', 'Debit Card'
        CHECKING_ACCOUNT = 'CHECKING_ACCOUNT', 'Checking Account'
        PIX = 'PIX', 'PIX'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_methods',
    )
    name = models.CharField(max_length=100)
    method_type = models.CharField(max_length=20, choices=MethodType.choices)
    # Credit card billing cycle. `best_purchase_day` alone decides which month
    # a purchase is paid in; null means "no cycle" and the card behaves like
    # cash, which is what every method did before these columns existed and is
    # still the right default for one the user has not configured. `due_day` is
    # only ever displayed — it says which day of the billed month the money
    # goes out, and leaving it empty changes no figure anywhere.
    best_purchase_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    due_day = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_payment_method_per_user'),
        ]

    def __str__(self):
        # The FR14 defaults are named exactly after their own type ("Credit
        # Card", "PIX", ...), so appending the type unconditionally rendered
        # "Credit Card (Credit Card)" in every dropdown. Only qualify the name
        # when it actually adds information (e.g. "Nubank Credit (Credit Card)").
        type_display = self.get_method_type_display()
        if self.name.strip().casefold() == type_display.casefold():
            return self.name
        return f'{self.name} ({type_display})'

    @property
    def has_billing_cycle(self):
        """True when this card can defer a purchase to a later month.

        Needs `best_purchase_day` and nothing else — `due_day` is a display
        detail and a card without one still bills on the month the statement
        closes. Restricted to credit cards on purpose: debit, PIX and a
        checking account all take the money the moment the purchase happens, so
        there is no statement for a purchase to fall on the far side of.
        """
        return (
            self.method_type == self.MethodType.CREDIT_CARD
            and self.best_purchase_day is not None
        )

    def statement_offset(self, purchase_date):
        """Whole months from a purchase to the month it comes off the balance.

        One shift, decided entirely by `best_purchase_day`: it is the day the
        new cycle opens, which is exactly what makes it the *best* day to buy,
        since a purchase from that day on is billed a whole cycle later. So
        `day >= best_purchase_day` pushes the purchase onto the next month's
        bill, and anything earlier stays on the one closing this month.

        A card opening on the 24th: a purchase on 20 June comes out of June, a
        purchase on 25 June comes out of July, and one on 25 July comes out of
        August. `due_day` deliberately plays no part — it records *which day*
        of the billed month the money goes out, not which month, so changing it
        never moves a transaction between months.

        Returns 0 for any method without a cycle, which keeps every existing
        transaction landing exactly where it did before.
        """
        if not self.has_billing_cycle:
            return 0

        # A cycle opening on the 31st still has to open in February. Clamping
        # to the month's last day makes "the day the cycle opens" meaningful in
        # every month rather than silently skipping the short ones.
        days_in_month = monthrange(purchase_date.year, purchase_date.month)[1]
        opens_on = min(self.best_purchase_day, days_in_month)

        return 1 if purchase_date.day >= opens_on else 0

    def due_date_in(self, year, month):
        """The card's due day within a given month, or `None` if unset.

        Clamped to the month's length so a due day of 31 still resolves in
        February — the bill is paid on the last day rather than not at all.
        """
        if self.due_day is None:
            return None
        return min(self.due_day, monthrange(year, month)[1])
