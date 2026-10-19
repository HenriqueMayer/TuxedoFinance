# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Synthetic, isolated filesystem coverage; no account or provider requests."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import time
from unittest import mock, skipUnless
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from django.test import SimpleTestCase, override_settings

from assistant.connections.vault import CredentialVault, MAX_RECORD_BYTES, VaultError


def _increment_locked(root, record_id, iterations):
    """A process worker deliberately separates reading and writing under lock."""
    vault = CredentialVault(root)
    for _ in range(iterations):
        with vault.lock(record_id):
            value = vault.read(record_id)['counter']
            time.sleep(0.002)
            vault.write(record_id, {'counter': value + 1})


@skipUnless(os.name == 'posix', 'The private vault requires POSIX ownership, permissions and flock.')
class CredentialVaultTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuxedo-vault-test.')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'private' / 'assistant'
        self.vault = CredentialVault(self.root)
        self.record_id = uuid4()

    def assert_code(self, code, call):
        with self.assertRaises(VaultError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        self.assertNotIn('SYNTHETIC_SECRET', repr(caught.exception))

    def test_constructor_and_uninitialized_reads_do_not_create_any_files(self):
        with override_settings(ASSISTANT_PRIVATE_DIR=self.root):
            vault = CredentialVault()
        self.assertEqual(vault.root, self.root)
        self.assertEqual(repr(vault), 'CredentialVault()')
        self.assert_code('not_initialized', vault.host_id)
        self.assert_code('not_initialized', lambda: vault.read(self.record_id))
        self.assert_code('not_initialized', lambda: vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET'}))
        self.assert_code('not_initialized', lambda: vault.delete(self.record_id))
        self.assert_code('not_initialized', lambda: vault.lock(self.record_id).__enter__())
        self.assertFalse(self.root.parent.exists())

    def test_independent_key_and_host_survive_restart_and_initialization_is_idempotent(self):
        with override_settings(SECRET_KEY='SYNTHETIC_SECRET_DJANGO_KEY'):
            self.vault.initialize()
            host = self.vault.host_id()
            first = {path.name: path.read_bytes() for path in self.root.iterdir()}
        self.assertEqual(UUID(host).version, 4)
        self.assertEqual(host, UUID(host).urn)
        with override_settings(SECRET_KEY='A_DIFFERENT_SYNTHETIC_DJANGO_KEY'):
            restarted = CredentialVault(self.root)
            restarted.initialize()
            self.assertEqual(restarted.host_id(), host)
            self.assertEqual({path.name: path.read_bytes() for path in self.root.iterdir()}, first)
        self.assertNotIn(b'SYNTHETIC_SECRET', first['vault.key'])

    def test_ciphertext_round_trip_permissions_no_plaintext_and_idempotent_delete(self):
        self.vault.initialize()
        payload = {'access_token': 'SYNTHETIC_SECRET_ACCESS', 'refresh_token': 'SYNTHETIC_SECRET_REFRESH',
                   'expires_at': 12345, 'registration': {'client_id': 'Synthetic fixture'}, 'unicode': 'ação'}
        self.vault.write(str(self.record_id).upper(), payload)
        self.assertEqual(self.vault.read(self.record_id), payload)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.root.parent.stat().st_mode), 0o700)
        for path in self.root.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn(b'SYNTHETIC_SECRET', path.read_bytes())
        self.vault.delete(self.record_id)
        self.vault.delete(self.record_id)
        self.assert_code('record_not_found', lambda: self.vault.read(self.record_id))

    def test_missing_key_fails_closed_and_does_not_replace_existing_material(self):
        self.vault.initialize()
        self.vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET'})
        encrypted = (self.root / f'{self.record_id}.json.enc').read_bytes()
        (self.root / 'vault.key').unlink()
        self.assert_code('key_missing', self.vault.initialize)
        self.assert_code('key_missing', lambda: self.vault.read(self.record_id))
        self.assert_code('key_missing', lambda: self.vault.write(self.record_id, {'new': 'value'}))
        self.assert_code('key_missing', lambda: self.vault.delete(self.record_id))
        self.assertFalse((self.root / 'vault.key').exists())
        self.assertEqual((self.root / f'{self.record_id}.json.enc').read_bytes(), encrypted)

    def test_wrong_and_malformed_key_are_not_rotated_even_without_records(self):
        self.vault.initialize()
        key_path = self.root / 'vault.key'
        original = key_path.read_bytes()
        for wrong_key in (Fernet.generate_key(), b'SYNTHETIC_SECRET_INVALID_KEY'):
            with self.subTest(wrong_key_length=len(wrong_key)):
                key_path.write_bytes(wrong_key)
                self.assert_code('key_invalid', self.vault.initialize)
                self.assert_code('key_invalid', self.vault.host_id)
                self.assertEqual(key_path.read_bytes(), wrong_key)
        key_path.write_bytes(original)
        self.assertTrue(self.vault.host_id().startswith('urn:uuid:'))

    def test_uuid_paths_and_bounded_json_are_validated_without_leaking_input(self):
        for invalid in ('../../SYNTHETIC_SECRET', '/tmp/SYNTHETIC_SECRET', '', 123, None, object()):
            with self.subTest(type=type(invalid).__name__):
                for operation in (self.vault.read, self.vault.delete,
                                  lambda value: self.vault.write(value, {}),
                                  lambda value: self.vault.lock(value).__enter__()):
                    self.assert_code('invalid_record_id', lambda: operation(invalid))
        self.vault.initialize()
        for data in ([], 'SYNTHETIC_SECRET', {'token': object()}, {'value': float('nan')}):
            self.assert_code('invalid_record', lambda: self.vault.write(self.record_id, data))
        self.assert_code('record_too_large', lambda: self.vault.write(self.record_id, {'token': 'x' * MAX_RECORD_BYTES}))
        self.assertFalse((self.root / f'{self.record_id}.json.enc').exists())

    def test_root_and_parent_symlinks_are_rejected_without_touching_targets(self):
        target = Path(self.temporary.name) / 'actual'
        target.mkdir(mode=0o700)
        self.root.parent.mkdir(mode=0o700)
        self.root.symlink_to(target, target_is_directory=True)
        self.assert_code('unsafe_path', self.vault.initialize)
        self.assertEqual(list(target.iterdir()), [])
        via_parent = CredentialVault(self.root / 'child')
        self.assert_code('unsafe_path', via_parent.initialize)
        self.assertEqual(list(target.iterdir()), [])

    def test_symlink_key_record_and_lock_are_rejected(self):
        self.vault.initialize()
        target = Path(self.temporary.name) / 'untouched'
        target.write_bytes(b'SYNTHETIC_SECRET_TARGET')
        target.chmod(0o600)
        key = self.root / 'vault.key'
        original = key.read_bytes()
        key.unlink()
        key.symlink_to(target)
        self.assert_code('unsafe_path', self.vault.host_id)
        key.unlink()
        key.write_bytes(original)
        key.chmod(0o600)
        record = self.root / f'{self.record_id}.json.enc'
        record.symlink_to(target)
        self.assert_code('unsafe_path', lambda: self.vault.read(self.record_id))
        self.assert_code('unsafe_path', lambda: self.vault.write(self.record_id, {}))
        self.assert_code('unsafe_path', lambda: self.vault.delete(self.record_id))
        lock = self.root / f'.{self.record_id}.lock'
        lock.symlink_to(target)
        self.assert_code('unsafe_path', lambda: self.vault.lock(self.record_id).__enter__())
        self.assertEqual(target.read_bytes(), b'SYNTHETIC_SECRET_TARGET')

    def test_insecure_modes_ownership_hardlinks_and_special_files_are_rejected(self):
        self.vault.initialize()
        self.root.chmod(0o755)
        self.assert_code('unsafe_permissions', self.vault.host_id)
        self.root.chmod(0o700)
        key = self.root / 'vault.key'
        key.chmod(0o640)
        self.assert_code('unsafe_permissions', self.vault.host_id)
        key.chmod(0o600)
        with mock.patch('assistant.connections.vault.os.getuid', return_value=os.getuid() + 1):
            self.assert_code('unsafe_permissions', self.vault.host_id)
        linked = Path(self.temporary.name) / 'key-hardlink'
        os.link(key, linked)
        self.assert_code('unsafe_path', self.vault.host_id)
        linked.unlink()
        record = self.root / f'{self.record_id}.json.enc'
        os.mkfifo(record, 0o600)
        self.assert_code('unsafe_path', lambda: self.vault.read(self.record_id))

    def test_corruption_swapped_records_and_missing_host_fail_closed(self):
        self.vault.initialize()
        self.vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET'})
        other_id = uuid4()
        other = self.root / f'{other_id}.json.enc'
        other.write_bytes((self.root / f'{self.record_id}.json.enc').read_bytes())
        other.chmod(0o600)
        self.assert_code('record_invalid', lambda: self.vault.read(other_id))
        other.write_bytes(b'CORRUPTED_SYNTHETIC_SECRET')
        self.assert_code('record_invalid', lambda: self.vault.read(other_id))
        # Key/host validation is independent of another record's lifecycle:
        # an unrelated corruption or concurrent deletion cannot block this one.
        self.vault.initialize()
        self.assertEqual(self.vault.read(self.record_id), {'token': 'SYNTHETIC_SECRET'})
        other.unlink()
        (self.root / 'host-id').unlink()
        self.assert_code('host_id_invalid', self.vault.initialize)
        self.assert_code('host_id_invalid', lambda: self.vault.read(self.record_id))

    def test_atomic_replace_failure_preserves_previous_record_and_cleans_temporary(self):
        self.vault.initialize()
        self.vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET_OLD'})
        original = (self.root / f'{self.record_id}.json.enc').read_bytes()
        with mock.patch('assistant.connections.vault.os.replace', side_effect=OSError('SYNTHETIC_SECRET_OS_ERROR')):
            self.assert_code('storage_error', lambda: self.vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET_NEW'}))
        self.assertEqual((self.root / f'{self.record_id}.json.enc').read_bytes(), original)
        self.assertFalse(list(self.root.glob('.tmp-*')))
        self.vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET_NEW'})
        self.assertEqual(self.vault.read(self.record_id), {'token': 'SYNTHETIC_SECRET_NEW'})

    def test_interrupted_initial_setup_reuses_the_published_key(self):
        self.root.parent.mkdir(mode=0o700)
        self.root.mkdir(mode=0o700)
        key_path = self.root / 'vault.key'
        original = Fernet.generate_key()
        key_path.write_bytes(original)
        key_path.chmod(0o600)
        self.vault.initialize()
        self.assertEqual(key_path.read_bytes(), original)
        self.assertTrue(self.vault.host_id().startswith('urn:uuid:'))

    def test_shared_writable_parent_is_rejected_without_creating_vault(self):
        Path(self.temporary.name).chmod(0o755)
        self.root.parent.mkdir(mode=0o777)
        self.root.parent.chmod(0o777)
        self.assert_code('unsafe_permissions', self.vault.initialize)
        self.assertFalse(self.root.exists())

    def test_private_ancestor_protects_group_writable_installation_path(self):
        self.root.parent.mkdir(mode=0o775)
        self.root.parent.chmod(0o775)
        self.vault.initialize()
        self.assertTrue(self.vault.host_id().startswith('urn:uuid:'))
        self.assertEqual(stat.S_IMODE(self.root.parent.stat().st_mode), 0o775)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)

    def test_concurrent_initializers_reuse_one_key_and_identity(self):
        def initialize(_):
            vault = CredentialVault(self.root)
            vault.initialize()
            return vault.host_id()

        with ThreadPoolExecutor(max_workers=4) as executor:
            identities = list(executor.map(initialize, range(4)))
        self.assertEqual(len(set(identities)), 1)
        self.assertFalse(list(self.root.glob('.tmp-*')))

    def test_unrelated_record_deleted_after_listing_does_not_block_initialization(self):
        self.vault.initialize()
        self.vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET'})
        unrelated = uuid4()
        self.vault.write(unrelated, {'other': 'Synthetic fixture'})
        list_directory = os.listdir

        def listing_before_concurrent_delete(descriptor):
            names = list_directory(descriptor)
            (self.root / f'{unrelated}.json.enc').unlink()
            return names

        with mock.patch('assistant.connections.vault.os.listdir', side_effect=listing_before_concurrent_delete):
            self.vault.initialize()
        self.assertEqual(self.vault.read(self.record_id), {'token': 'SYNTHETIC_SECRET'})

    def test_unrelated_record_mutations_and_initialization_can_run_concurrently(self):
        self.vault.initialize()
        self.vault.write(self.record_id, {'token': 'SYNTHETIC_SECRET'})
        unrelated = uuid4()

        def mutate_unrelated():
            for number in range(20):
                with self.vault.lock(unrelated):
                    self.vault.write(unrelated, {'number': number})
                    self.vault.delete(unrelated)

        with ThreadPoolExecutor(max_workers=1) as executor:
            mutation = executor.submit(mutate_unrelated)
            for _ in range(20):
                self.vault.initialize()
                self.assertEqual(self.vault.read(self.record_id), {'token': 'SYNTHETIC_SECRET'})
            mutation.result(timeout=10)

    def test_record_lock_serializes_threads_and_allows_write_and_delete_inside_it(self):
        self.vault.initialize()
        self.vault.write(self.record_id, {'counter': 0})
        with ThreadPoolExecutor(max_workers=4) as executor:
            tasks = [executor.submit(_increment_locked, self.root, self.record_id, 8) for _ in range(4)]
            for task in tasks:
                task.result(timeout=10)
        self.assertEqual(self.vault.read(self.record_id), {'counter': 32})
        with self.vault.lock(self.record_id):
            self.vault.delete(self.record_id)
            self.vault.write(self.record_id, {'counter': 1})
        self.assertTrue((self.root / f'.{self.record_id}.lock').exists())

    def test_lock_preserves_caller_failure_and_releases_for_recovery(self):
        self.vault.initialize()
        failure = OSError('Synthetic transport failure')
        with self.assertRaises(OSError) as caught:
            with self.vault.lock(self.record_id):
                raise failure
        self.assertIs(caught.exception, failure)
        with self.vault.lock(self.record_id):
            self.vault.write(self.record_id, {'counter': 1})
        self.assertEqual(self.vault.read(self.record_id), {'counter': 1})

    def test_record_lock_serializes_independent_processes(self):
        self.vault.initialize()
        self.vault.write(self.record_id, {'counter': 0})
        context = multiprocessing.get_context('fork')
        workers = [context.Process(target=_increment_locked, args=(self.root, self.record_id, 8)) for _ in range(3)]
        for worker in workers:
            worker.start()
        try:
            for worker in workers:
                worker.join(timeout=10)
                self.assertEqual(worker.exitcode, 0)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
        self.assertEqual(self.vault.read(self.record_id), {'counter': 24})

    def test_unsupported_platform_fails_closed_without_import_or_filesystem_side_effects(self):
        with mock.patch('assistant.connections.vault.fcntl', None):
            self.assert_code('unsupported_platform', self.vault.initialize)
            self.assert_code('unsupported_platform', self.vault.host_id)
        self.assertFalse(self.root.parent.exists())
