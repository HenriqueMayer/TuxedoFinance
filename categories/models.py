from django.conf import settings
from django.db import models


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
    name = models.CharField(max_length=100)
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
