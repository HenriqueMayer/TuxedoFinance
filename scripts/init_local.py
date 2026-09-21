#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Create the native installation signing key once, without replacing any file."""
import argparse
import os
from pathlib import Path
import secrets


def initialize(directory):
    target = Path(directory) / '.env'
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, 'w') as output:
        output.write(f'SECRET_KEY={secrets.token_urlsafe(64)}\n')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    created = initialize(args.directory)
    print('Created private .env configuration.' if created else 'Existing .env preserved; its signing key was not changed.')
