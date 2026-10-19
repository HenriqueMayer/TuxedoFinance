# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Versioned instructions are application code, never financial record text."""
from pathlib import Path


INSTRUCTIONS_VERSION = 'v2'
SUPPORTED_INSTRUCTIONS_VERSIONS = ('v1', 'v2')


def load_instructions(version=INSTRUCTIONS_VERSION):
    if version not in SUPPORTED_INSTRUCTIONS_VERSIONS:
        raise ValueError('Unsupported assistant instructions version.')
    return (Path(__file__).parent / version / 'system.txt').read_text(encoding='utf-8')
