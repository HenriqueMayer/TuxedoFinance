from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from payments.models import PaymentMethod

# One default payment method per `method_type`, seeded for every new user
# (PRD FR14, PRD §8.4). Keeps a brand-new account usable immediately, since
# `Transaction.payment_method` is a required field.
DEFAULT_PAYMENT_METHODS = (
    (PaymentMethod.MethodType.CREDIT_CARD, 'Credit Card'),
    (PaymentMethod.MethodType.DEBIT_CARD, 'Debit Card'),
    (PaymentMethod.MethodType.CHECKING_ACCOUNT, 'Checking Account'),
    (PaymentMethod.MethodType.PIX, 'PIX'),
)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='payments_seed_defaults')
def seed_default_payment_methods(sender, instance, created, **kwargs):
    """Seed one default payment method per `method_type` for a new user (FR14)."""
    if not created:
        return
    PaymentMethod.objects.bulk_create(
        PaymentMethod(user=instance, name=name, method_type=method_type)
        for method_type, name in DEFAULT_PAYMENT_METHODS
    )
