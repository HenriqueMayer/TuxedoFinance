# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django import template

from core.assets import asset_url, frontend_revision

register = template.Library()


@register.simple_tag
def asset(name):
    return asset_url(name)


@register.simple_tag(takes_context=True)
def asset_revision(context):
    request = context.get('request')
    if request is not None and hasattr(request, 'tuxedo_asset_revision'):
        return request.tuxedo_asset_revision
    return frontend_revision()
