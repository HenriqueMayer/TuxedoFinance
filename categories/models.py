from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy


def validate_parent_hierarchy(category_key, parent_key, parent_by_key):
    """Validate the effective owned graph for both model IDs and CSV names."""
    visited = {category_key} if category_key is not None else set()
    while parent_key is not None:
        if parent_key in visited:
            raise ValidationError({
                'parent_category': _('Choose a parent category that does not create a circular hierarchy.'),
            })
        if parent_key not in parent_by_key:
            raise ValidationError({'parent_category': _('The parent category must belong to you.')})
        visited.add(parent_key)
        parent_key = parent_by_key[parent_key]


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
        if self.parent_category_id is not None:
            parents = dict(Category.objects.filter(user_id=self.user_id).values_list('pk', 'parent_category_id'))
            validate_parent_hierarchy(self.pk, self.parent_category_id, parents)
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
        if self.pk and self.transaction_type and self.transaction_splits.exclude(transaction__transaction_type=self.transaction_type).exists():
            raise ValidationError({'transaction_type': _('This category has splits of another transaction type.')})
        if self.pk and self.transaction_type == self.TransactionType.INCOME and self.invoice_credits.exists():
            raise ValidationError({'transaction_type': _('This category has invoice credits and must remain available for expenses.')})
        if self.pk:
            from planning.services import validate_budget_category_change
            validate_budget_category_change(self)

    def descendant_ids(self):
        """Keep the ordinary parent picker safe, including for legacy cycles."""
        children = {}
        for category_id, parent_id in Category.objects.filter(user_id=self.user_id).values_list('pk', 'parent_category_id'):
            children.setdefault(parent_id, []).append(category_id)
        visited = {self.pk}
        pending = list(children.get(self.pk, []))
        while pending:
            category_id = pending.pop()
            if category_id not in visited:
                visited.add(category_id)
                pending.extend(children.get(category_id, []))
        return visited - {self.pk}
