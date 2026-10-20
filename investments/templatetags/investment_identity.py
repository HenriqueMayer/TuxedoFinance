# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Render native emoji from one user-owned lookup per template render."""

from django import template

from investments.appearance import DEFAULT_ICON, icon_identity, position_appearance_map

register = template.Library()


@register.simple_tag(takes_context=True)
def position_icon(context, product, asset):
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return icon_identity()['emoji']
    # Includes have their own render-context frames. Cache on this request,
    # scoped to its authenticated owner, to avoid one lookup per row/include.
    cached = getattr(request, '_investment_position_appearance', None)
    if cached is None or cached[0] != request.user.pk:
        cached = (request.user.pk, position_appearance_map(request.user))
        request._investment_position_appearance = cached
    cache = cached[1]
    product_id = product.pk if hasattr(product, 'pk') else product
    asset_id = asset.pk if hasattr(asset, 'pk') else asset
    return icon_identity(cache.get((product_id, asset_id), DEFAULT_ICON))['emoji']
