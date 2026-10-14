# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django import template

from core.navigation import with_return_url

register = template.Library()


@register.simple_tag(takes_context=True)
def contextual_url(context, target, origin=None, fragment=None):
    request = context.get('request')
    if origin is None:
        origin = request.get_full_path() if request is not None else ''
    return with_return_url(target, origin, fragment=fragment)
