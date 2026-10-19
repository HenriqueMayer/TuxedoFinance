# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Future providers plug into a local contract; none is connected by default."""
from assistant.providers.base import DisconnectedProvider


def get_provider():
    return DisconnectedProvider()
