# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import sqlite3
import tempfile
from pathlib import Path
import unittest

from scripts.sqlite_backup import copy_database


class SQLiteBackupTests(unittest.TestCase):
    def test_copies_committed_wal_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.sqlite3'
            target = Path(directory) / 'backup.sqlite3'
            with sqlite3.connect(source) as database:
                database.execute('PRAGMA journal_mode=WAL')
                database.execute('CREATE TABLE balances (amount TEXT)')
                database.execute("INSERT INTO balances VALUES ('123.45')")
                database.commit()
                copy_database(source, target)
                with sqlite3.connect(target) as backup:
                    self.assertEqual(backup.execute('SELECT amount FROM balances').fetchone(), ('123.45',))
                previous = target.read_bytes()
                with self.assertRaises(FileExistsError):
                    copy_database(source, target)
                self.assertEqual(target.read_bytes(), previous)
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_invalid_source_never_creates_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'broken.sqlite3'
            target = Path(directory) / 'backup.sqlite3'
            source.write_bytes(b'This is not a database')
            with self.assertRaises(sqlite3.DatabaseError):
                copy_database(source, target)
            self.assertFalse(target.exists())
            with self.assertRaises(sqlite3.OperationalError):
                copy_database(Path(directory) / 'missing.sqlite3', target)
            self.assertFalse(target.exists())

    def test_same_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.sqlite3'
            with self.assertRaises(ValueError):
                copy_database(source, source)
