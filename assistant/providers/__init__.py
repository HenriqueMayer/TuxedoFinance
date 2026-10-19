# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Resolve only the current owner's explicitly enabled, selected connection."""
from django.conf import settings

from assistant.providers.base import DisconnectedProvider


def get_provider(user=None, connection_id=None):
    if (getattr(settings, 'ASSISTANT_OPENAI_AUTH_ENABLED', False) is not True
            or getattr(settings, 'ASSISTANT_OPENAI_INFERENCE_ENABLED', False) is not True
            or not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False)):
        return DisconnectedProvider()
    from assistant.models import ProviderConnection
    from assistant.providers.openai import OpenAIProvider
    try:
        selected = ProviderConnection.objects.filter(user=user, provider='openai', is_active=True, status='ready')
        connection = selected.filter(pk=connection_id).first() if connection_id is not None else selected.first()
        if (connection and isinstance(connection.scopes, list)
                and {'resource.invoke', 'chatgpt.tokens.use.direct'} <= set(connection.scopes)):
            return OpenAIProvider(user, connection.pk)
    except Exception:
        pass
    return DisconnectedProvider()
