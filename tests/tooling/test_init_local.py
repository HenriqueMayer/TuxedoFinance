# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from pathlib import Path
import stat
import tempfile
from unittest import TestCase

from scripts.init_local import initialize


class NativeInitializationTests(TestCase):
    def test_initial_key_is_private_and_repeated_setup_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / '.env'
            self.assertTrue(initialize(directory))
            original = target.read_bytes()
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertGreater(len(original.split(b'=', 1)[1].strip()), 50)
            self.assertFalse(initialize(directory))
            self.assertEqual(target.read_bytes(), original)

    def test_existing_symlink_is_not_followed_or_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'original'
            original.write_text('preserved')
            target = Path(directory) / '.env'
            target.symlink_to(original)
            self.assertFalse(initialize(directory))
            self.assertTrue(target.is_symlink())
            self.assertEqual(original.read_text(), 'preserved')
