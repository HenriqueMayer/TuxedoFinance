from django.conf import settings
from django.db import models


class PaymentMethod(models.Model):
    """A user-defined payment method used to record transactions (PRD §8.3).

    `method_type` classifies the method into one of the four PRD §8.4
    options; `name` is a free-form label (e.g. "Nubank Credit", "PIX").
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
