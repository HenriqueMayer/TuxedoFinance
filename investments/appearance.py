# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Cosmetic position identity, independent of financial or planning settings."""

from django.db import transaction
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


DEFAULT_ICON = 'general'
POSITION_ICONS = (
    ('piggy', '🐷', _('Piggy bank')),
    ('reserve', '🛟', _('Emergency reserve')),
    ('home', '🏠', pgettext_lazy('Investment icon', 'Home')),
    ('goal', '🎯', pgettext_lazy('Investment icon', 'Goal')),
    ('general', '💰', _('General')),
    ('investment', '📈', _('Investment')),
    ('long_term', '🌱', _('Long term')),
    ('travel', '✈️', _('Travel')),
    ('education', '🎓', pgettext_lazy('Investment icon', 'Education')),
    ('vehicle', '🚗', _('Vehicle')),
    ('vacation', '🏖️', _('Vacation')),
    ('security', '🔒', _('Security')),
)
ICON_CHOICES = tuple((key, format_lazy('{} {}', emoji, label)) for key, emoji, label in POSITION_ICONS)
ICON_KEYS = tuple(key for key, _emoji, _label in POSITION_ICONS)


def icon_identity(key=DEFAULT_ICON):
    """Keep presentation bounded even when inspecting older malformed values."""
    selected = next((item for item in POSITION_ICONS if item[0] == key), None)
    value, emoji, label = selected or next(item for item in POSITION_ICONS if item[0] == DEFAULT_ICON)
    return {'key': value, 'emoji': emoji, 'label': label}


def position_appearance_map(user):
    from investments.models import PositionAppearance

    return {(product, asset): icon for product, asset, icon in PositionAppearance.objects.filter(
        user=user, product__user=user, product__bank__user=user, asset__user=user,
    ).values_list('product_id', 'asset_id', 'icon')}


@transaction.atomic
def save_position_appearance(user, product, asset, icon):
    """Changing an emoji must never synchronize or create a financial operation."""
    from investments.models import PositionAppearance

    setting = PositionAppearance.objects.filter(user=user, product=product, asset=asset).first()
    setting = setting or PositionAppearance(user=user, product=product, asset=asset)
    setting.icon = icon
    setting.full_clean()
    setting.save()
    return setting
