from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy


class Category(models.Model):
    """A user-defined category used to classify transactions (PRD §8.3).

    `parent_category` is an optional self-relationship: a category with no
    parent is a top-level category; one with a parent is a subcategory
    (e.g. `Uber` -> `Transportation`).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='categories',
    )
    class TransactionType(models.TextChoices):
        INCOME = 'INCOME', gettext_lazy('Income')
        EXPENSE = 'EXPENSE', gettext_lazy('Expense')

    name = models.CharField(max_length=100)
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
        null=True,
        blank=True,
        help_text=_('Optional. Unclassified categories can be used for income and expenses.'),
    )
    parent_category = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subcategories',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_category_per_user'),
        ]

    def __str__(self):
        if self.parent_category:
            return f'{self.parent_category.name} > {self.name}'
        return self.name

    def clean(self):
        if (
            self.pk
            and self.transaction_type
            and self.transactions.exclude(transaction_type=self.transaction_type).exists()
        ):
            raise ValidationError({
                'transaction_type': _(
                    'This category has transactions of another type and cannot be classified that way.'
                )
            })
