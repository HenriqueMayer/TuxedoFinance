from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext, gettext_noop

from categories.models import Category

# Default top-level categories seeded for every new user (PRD FR27, domain
# diagram — docs/svg/diagram.svg). Keeps a brand-new account usable
# immediately, since `Transaction.category` is a required field.
DEFAULT_CATEGORY_NAMES = (
    gettext_noop('Groceries'),
    gettext_noop('Food & Dining'),
    gettext_noop('Subscriptions'),
    gettext_noop('Education'),
    gettext_noop('Fitness'),
    gettext_noop('Transportation'),
    gettext_noop('Pets'),
    gettext_noop('Hobbies & Entertainment'),
    gettext_noop('Services'),
)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='categories_seed_defaults')
def seed_default_categories(sender, instance, created, **kwargs):
    """Seed top-level categories in the language active during account creation."""
    if not created:
        return
    Category.objects.bulk_create(
        Category(user=instance, name=gettext(name)) for name in DEFAULT_CATEGORY_NAMES
    )
