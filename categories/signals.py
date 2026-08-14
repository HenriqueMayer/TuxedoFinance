from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from categories.models import Category

# Default top-level categories seeded for every new user (PRD FR27, domain
# diagram — docs/svg/diagram.svg). Keeps a brand-new account usable
# immediately, since `Transaction.category` is a required field.
DEFAULT_CATEGORY_NAMES = (
    'Groceries',
    'Food & Dining',
    'Subscriptions',
    'Education',
    'Fitness',
    'Transportation',
    'Pets',
    'Hobbies & Entertainment',
    'Services',
)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='categories_seed_defaults')
def seed_default_categories(sender, instance, created, **kwargs):
    """Seed the default top-level categories for a newly created user (FR27)."""
    if not created:
        return
    Category.objects.bulk_create(
        Category(user=instance, name=name) for name in DEFAULT_CATEGORY_NAMES
    )
