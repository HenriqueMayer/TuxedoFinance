# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Versioned instructions are application code, never financial record text."""
from pathlib import Path


INSTRUCTIONS_VERSION = 'v1'


def load_instructions(version=INSTRUCTIONS_VERSION):
    if version != INSTRUCTIONS_VERSION:
        raise ValueError('Unsupported assistant instructions version.')
    return (Path(__file__).parent / version / 'system.txt').read_text(encoding='utf-8')
