# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic private pilot artifacts; no bank, credential or database access."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
import stat
import tempfile
from unittest import skipUnless
from unittest.mock import patch

from django.test import SimpleTestCase

from ingestion.open_finance.client import PilotError
from ingestion.open_finance.storage import MAX_REPORT_BYTES, PilotStore


@skipUnless(os.name == "posix", "The private pilot store requires POSIX permissions and flock.")
class PilotStoreTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tuxedo-pluggy-storage.")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "private" / "pilot"
        self.store = PilotStore(self.root)
        self.key = "live:user-1:8b659cef-9dbf-492a-99f5-50a07929ae38"
        self.report = {"retrieved_at": "2026-10-19T12:00:00+00:00", "bills": [], "warnings": ["Synthetic"]}

    def path_for(self, key):
        return self.root / (sha256(key.encode()).hexdigest() + ".json")

    def assert_error(self, code, operation):
        with self.assertRaises(PilotError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("PRIVATE_SYNTHETIC", str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_missing_load_and_constructor_do_not_initialize_storage(self):
        self.assertEqual(repr(self.store), "PilotStore()")
        self.assertEqual(self.store.path(self.key), self.path_for(self.key))
        self.assertIsNone(self.store.load(self.key))
        self.assertFalse(self.root.parent.exists())

    def test_private_atomic_round_trip_and_replacement(self):
        with self.store.lock(self.key):
            path = self.store.save(self.key, self.report)
            self.assertEqual(path, self.path_for(self.key))
            self.assertEqual(self.store.load(self.key), self.report)
            replacement = {**self.report, "bills": [{"total": "10.01", "description": "Infinity and NaN are text"}]}
            self.store.save(self.key, replacement)
            self.assertEqual(self.store.load(self.key), replacement)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.root.parent.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in self.root.iterdir()))
        self.assertFalse(any(path.name.startswith(".tmp-") for path in self.root.iterdir()))

    def test_mode_owner_and_item_keys_are_separate_without_path_interpretation(self):
        keys = [self.key, self.key.replace("live:", "demo:"),
                self.key.replace("user-1:", "user-2:"), "../../PRIVATE_SYNTHETIC"]
        for number, key in enumerate(keys):
            self.store.save(key, {"number": number})
        self.assertEqual(len(list(self.root.glob("*.json"))), len(keys))
        for number, key in enumerate(keys):
            self.assertEqual(self.store.load(key), {"number": number})
        self.assertFalse((self.parent / "PRIVATE_SYNTHETIC").exists())

    def test_invalid_keys_are_safe_and_create_nothing(self):
        for key in (None, 1, "", "x" * 2049, "\ud800"):
            for method in (self.store.load, lambda key: self.store.save(key, self.report),
                           lambda key: self.store.lock(key).__enter__()):
                with self.subTest(key_type=type(key).__name__, method=method):
                    self.assert_error("invalid_storage_key", lambda: method(key))
        self.assertFalse(self.root.exists())

    def test_root_and_ancestor_symlinks_are_rejected(self):
        outside = self.parent / "outside"
        outside.mkdir(mode=0o700)
        self.root.parent.mkdir(mode=0o700)
        self.root.symlink_to(outside, target_is_directory=True)
        self.assert_error("unsafe_storage_path", lambda: self.store.save(self.key, self.report))
        self.assert_error("unsafe_storage_path", lambda: self.store.load(self.key))
        self.root.unlink()
        self.root.parent.rmdir()
        self.root.parent.symlink_to(outside, target_is_directory=True)
        self.assert_error("unsafe_storage_path", lambda: self.store.save(self.key, self.report))
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_broad_permissions_are_not_silently_repaired(self):
        path = self.store.save(self.key, self.report)
        path.chmod(0o644)
        self.assert_error("unsafe_storage_permissions", lambda: self.store.load(self.key))
        self.assert_error("unsafe_storage_permissions", lambda: self.store.save(self.key, {}))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        path.chmod(0o600)
        self.root.chmod(0o755)
        self.assert_error("unsafe_storage_permissions", lambda: self.store.load(self.key))
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o755)

    def test_wrong_owner_and_unsafe_shared_parent_fail_closed(self):
        self.store.save(self.key, self.report)
        owner = os.getuid()
        with patch("ingestion.open_finance.storage.os.getuid", return_value=owner + 1):
            self.assert_error("unsafe_storage_permissions", lambda: self.store.load(self.key))
        self.parent.chmod(0o777)
        try:
            self.assert_error("unsafe_storage_permissions", lambda: self.store.load(self.key))
        finally:
            self.parent.chmod(0o700)

    def test_unsupported_platform_does_not_initialize_private_material(self):
        with patch("ingestion.open_finance.storage.fcntl", None):
            self.assert_error("unsupported_platform", lambda: self.store.load(self.key))
            self.assert_error("unsupported_platform", lambda: self.store.save(self.key, self.report))
        self.assertFalse(self.root.exists())

    def test_symlink_report_and_lock_files_never_follow_targets(self):
        self.store.save("initialize", {})
        target = self.parent / "PRIVATE_SYNTHETIC.json"
        target.write_text("{\"outside\":true}")
        target.chmod(0o600)
        path = self.path_for(self.key)
        path.symlink_to(target)
        self.assert_error("unsafe_storage_path", lambda: self.store.load(self.key))
        self.assert_error("unsafe_storage_path", lambda: self.store.save(self.key, self.report))
        lock_path = self.root / ("." + path.stem + ".lock")
        lock_path.symlink_to(target)
        self.assert_error("unsafe_storage_path", lambda: self.store.lock(self.key).__enter__())
        self.assertEqual(target.read_text(), "{\"outside\":true}")

    def test_hardlinked_report_and_nonregular_file_are_rejected(self):
        path = self.store.save(self.key, self.report)
        link = self.parent / "PRIVATE_SYNTHETIC-linked"
        os.link(path, link)
        self.assert_error("unsafe_storage_path", lambda: self.store.load(self.key))
        self.assert_error("unsafe_storage_path", lambda: self.store.save(self.key, {}))
        link.unlink()
        path.unlink()
        os.mkfifo(path, 0o600)
        self.assert_error("unsafe_storage_path", lambda: self.store.load(self.key))

    def test_replace_failure_keeps_old_report_and_removes_temporary_file(self):
        path = self.store.save(self.key, self.report)
        original = path.read_bytes()
        with patch("ingestion.open_finance.storage.os.replace", side_effect=OSError("PRIVATE_SYNTHETIC")):
            self.assert_error("storage_error", lambda: self.store.save(self.key, {"replacement": True}))
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(any(path.name.startswith(".tmp-") for path in self.root.iterdir()))

    def test_file_fsync_failure_keeps_old_report(self):
        path = self.store.save(self.key, self.report)
        original = path.read_bytes()
        with patch("ingestion.open_finance.storage.os.fsync", side_effect=OSError("PRIVATE_SYNTHETIC")):
            self.assert_error("storage_error", lambda: self.store.save(self.key, {"replacement": True}))
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(any(path.name.startswith(".tmp-") for path in self.root.iterdir()))

    def test_bounded_valid_json_only_and_failed_save_preserves_previous_report(self):
        path = self.store.save(self.key, self.report)
        for report in ([], {"value": float("nan")}, {"value": float("inf")}, {"value": object()}):
            with self.subTest(report_type=type(report).__name__):
                self.assert_error("invalid_report", lambda: self.store.save(self.key, report))
                self.assertEqual(self.store.load(self.key), self.report)
        self.assert_error("report_limit", lambda: self.store.save(self.key, {"large": "x" * MAX_REPORT_BYTES}))
        for raw in (b"[]", b"not json", b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e999}', b"\xff"):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.assert_error("invalid_report", lambda: self.store.load(self.key))
        path.write_bytes(b"x" * (MAX_REPORT_BYTES + 1))
        self.assert_error("report_limit", lambda: self.store.load(self.key))

    def test_same_key_is_busy_without_waiting_and_different_key_remains_available(self):
        def try_lock(key):
            with PilotStore(self.root).lock(key):
                return "acquired"

        with ThreadPoolExecutor(max_workers=1) as workers:
            with self.store.lock(self.key):
                future = workers.submit(try_lock, self.key)
                self.assert_error("pilot_busy", lambda: future.result(timeout=2))
                self.assertEqual(workers.submit(try_lock, "another-key").result(timeout=2), "acquired")
            self.assertEqual(workers.submit(try_lock, self.key).result(timeout=2), "acquired")
        self.assertIsNone(self.store.load(self.key))
