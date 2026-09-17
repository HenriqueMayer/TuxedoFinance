#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Back up SQLite or restore into a new database; never overwrite a target."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import shutil
import sys
import tempfile


def copy_database(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError('Source and destination must be different files.')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        if original.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise ValueError('Source integrity check failed.')
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(target)) as destination:
                original.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise ValueError('Destination integrity check failed.')
        except BaseException:
            target.unlink()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    if args.source == "-":
        with tempfile.TemporaryDirectory(prefix="tuxedo-restore-") as directory:
            source = Path(directory) / "backup.sqlite3"
            with source.open("wb") as output:
                shutil.copyfileobj(sys.stdin.buffer, output)
            copy_database(source, args.destination)
    else:
        copy_database(args.source, args.destination)
    print('SQLite copy verified; destination was created without overwriting existing data.')
