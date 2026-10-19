# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Small, installation-local credential vault with no implicit initialization.

The key is independent of Django's SECRET_KEY. Backups must preserve the whole
private directory, and the OS account running Django must own it exclusively.
This first slice requires POSIX permissions and flock; unsupported systems fail
closed when the vault is used, while importing ordinary application pages works.
"""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import stat
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

try:
    import fcntl
except ImportError:  # Windows must still import the application's settings page.
    fcntl = None


MAX_RECORD_BYTES = 128 * 1024
MAX_CIPHERTEXT_BYTES = MAX_RECORD_BYTES * 2 + 4096
_KEY_FILE = 'vault.key'
_CHECK_FILE = 'key-check.enc'
_HOST_FILE = 'host-id'
_KEY_CHECK = b'tuxedo-assistant-vault:v1'


class VaultError(RuntimeError):
    """A stable diagnostic code, never an underlying exception or credential."""

    def __init__(self, code='vault_error'):
        self.code = code
        super().__init__(code)


@contextmanager
def _storage_errors():
    try:
        yield
    except OSError:
        raise VaultError('storage_error') from None


class CredentialVault:
    """Atomic records; callers own the lock around a complete refresh lifecycle.

    read/write/delete do not lock implicitly, so they can be used inside lock()
    without deadlocking. A lock file remains in place after deletion to preserve
    the inode used by another process waiting for that same record.
    """

    def __init__(self, root=None):
        self.root = Path(os.path.abspath(root if root is not None else settings.ASSISTANT_PRIVATE_DIR))

    def __repr__(self):
        return 'CredentialVault()'

    @staticmethod
    def _require_platform():
        if os.name != 'posix' or fcntl is None or not hasattr(os, 'O_NOFOLLOW'):
            raise VaultError('unsupported_platform')

    @staticmethod
    def _record_name(record_id):
        if not isinstance(record_id, (UUID, str)):
            raise VaultError('invalid_record_id')
        try:
            return str(UUID(str(record_id)))
        except (ValueError, AttributeError):
            raise VaultError('invalid_record_id') from None

    @staticmethod
    def _validate_private(info, *, directory=False):
        expected = 0o700 if directory else 0o600
        valid_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not valid_type or (not directory and info.st_nlink != 1):
            raise VaultError('unsafe_path')
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != expected:
            raise VaultError('unsafe_permissions')

    def _check_ancestors(self, *, create=False):
        """Do not resolve symlinks before checking the configured path.

        Root-owned sticky temporary parents are allowed. A current-owner 0700
        ancestor (commonly the user's home) prevents other users from reaching
        writable descendants. Without that traversal boundary a shared writable
        parent could rename or replace the vault despite its own private mode.
        """
        ancestors = list(reversed(self.root.parents)) + [self.root]
        private_boundary = False
        for path in ancestors:
            try:
                info = path.lstat()
            except FileNotFoundError:
                if not create:
                    raise VaultError('not_initialized') from None
                try:
                    path.mkdir(mode=0o700)
                except FileExistsError:
                    pass  # Another initializer may have created this directory.
                info = path.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise VaultError('unsafe_path')
            if path == self.root:
                self._validate_private(info, directory=True)
            else:
                trusted_temporary = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
                if (info.st_uid not in {0, os.getuid()}
                        or (info.st_mode & 0o022 and not private_boundary and not trusted_temporary)):
                    raise VaultError('unsafe_permissions')
                if info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700:
                    private_boundary = True

    @contextmanager
    def _directory(self, *, create=False):
        self._require_platform()
        with _storage_errors():
            self._check_ancestors(create=create)
            descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with _storage_errors():
                self._validate_private(os.fstat(descriptor), directory=True)
            yield descriptor
        finally:
            with _storage_errors():
                os.close(descriptor)

    def _open_file(self, directory, name, *, create=False):
        flags = os.O_RDWR | os.O_CREAT if create else os.O_RDONLY
        try:
            descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
        except OSError as error:
            # ELOOP means a symlink. Never include its name or the raw OS error.
            if error.errno == errno.ELOOP:
                raise VaultError('unsafe_path') from None
            raise
        try:
            self._validate_private(os.fstat(descriptor))
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    def _read_file(self, directory, name, limit, *, missing_code):
        try:
            descriptor = self._open_file(directory, name)
        except FileNotFoundError:
            raise VaultError(missing_code) from None
        with os.fdopen(descriptor, 'rb') as source:
            if os.fstat(source.fileno()).st_size > limit:
                raise VaultError('record_too_large')
            data = source.read(limit + 1)
        if len(data) > limit:
            raise VaultError('record_too_large')
        return data

    def _check_destination(self, directory, name):
        try:
            descriptor = self._open_file(directory, name)
        except FileNotFoundError:
            return
        os.close(descriptor)

    def _atomic_write(self, directory, name, data, *, replace=True):
        self._check_destination(directory, name)
        temporary = f'.tmp-{uuid4().hex}'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, 'wb') as destination:
                self._validate_private(os.fstat(destination.fileno()))
                destination.write(data)
                destination.flush()
                os.fsync(destination.fileno())
            self._check_destination(directory, name)
            if replace:
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            else:
                # Hard-link publication is atomic and cannot replace an existing
                # key or host identity, including after concurrent initialization.
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
                os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    @contextmanager
    def _file_lock(self, directory, name):
        with _storage_errors():
            descriptor = self._open_file(directory, name, create=True)
        try:
            with _storage_errors():
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                with _storage_errors():
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                with _storage_errors():
                    os.close(descriptor)

    def _fernet(self, directory):
        key = self._read_file(directory, _KEY_FILE, 128, missing_code='key_missing')
        try:
            cipher = Fernet(key)
        except (ValueError, TypeError):
            raise VaultError('key_invalid') from None
        check = self._read_file(directory, _CHECK_FILE, 1024, missing_code='key_invalid')
        try:
            if cipher.decrypt(check) != _KEY_CHECK:
                raise VaultError('key_invalid')
        except InvalidToken:
            raise VaultError('key_invalid') from None
        return cipher

    def _host_id(self, directory):
        raw = self._read_file(directory, _HOST_FILE, 64, missing_code='host_id_invalid')
        try:
            value = raw.decode('ascii')
            identity = UUID(value)
            if identity.version != 4 or value != identity.urn:
                raise ValueError
        except (UnicodeError, ValueError):
            raise VaultError('host_id_invalid') from None
        return value

    def initialize(self):
        """Explicitly create private material, or validate it without rotation.

        A missing key beside any existing material never creates a new key.
        The encrypted check detects key replacement even when no records remain.
        """
        with _storage_errors(), self._directory(create=True) as directory:
            with self._file_lock(directory, '.initialize.lock'):
                names = set(os.listdir(directory))
                if _KEY_FILE not in names:
                    if names - {'.initialize.lock'}:
                        raise VaultError('key_missing')
                    self._atomic_write(directory, _KEY_FILE, Fernet.generate_key(), replace=False)
                if _CHECK_FILE not in names:
                    if any(name.endswith('.json.enc') for name in names):
                        raise VaultError('key_invalid')
                    key = self._read_file(directory, _KEY_FILE, 128, missing_code='key_missing')
                    try:
                        cipher = Fernet(key)
                    except (ValueError, TypeError):
                        raise VaultError('key_invalid') from None
                    self._atomic_write(directory, _CHECK_FILE, cipher.encrypt(_KEY_CHECK), replace=False)
                self._fernet(directory)
                if _HOST_FILE not in names:
                    if any(name.endswith('.json.enc') for name in names):
                        raise VaultError('host_id_invalid')
                    self._atomic_write(directory, _HOST_FILE, uuid4().urn.encode('ascii'), replace=False)
                self._host_id(directory)

    def host_id(self):
        with _storage_errors(), self._directory() as directory:
            self._fernet(directory)
            return self._host_id(directory)

    def _decrypt(self, directory, record_id, cipher):
        encrypted = self._read_file(directory, f'{record_id}.json.enc', MAX_CIPHERTEXT_BYTES,
                                    missing_code='record_not_found')
        try:
            plaintext = cipher.decrypt(encrypted)
            if len(plaintext) > MAX_RECORD_BYTES + 256:
                raise VaultError('record_too_large')
            envelope = json.loads(plaintext)
            if (not isinstance(envelope, dict) or envelope.get('version') != 1
                    or envelope.get('record_id') != record_id or not isinstance(envelope.get('data'), dict)):
                raise VaultError('record_invalid')
        except (InvalidToken, ValueError, TypeError, UnicodeError, RecursionError):
            raise VaultError('record_invalid') from None
        return envelope['data']

    def read(self, record_id):
        record_id = self._record_name(record_id)
        with _storage_errors(), self._directory() as directory:
            cipher = self._fernet(directory)
            self._host_id(directory)
            return self._decrypt(directory, record_id, cipher)

    def write(self, record_id, data):
        record_id = self._record_name(record_id)
        if not isinstance(data, dict):
            raise VaultError('invalid_record')
        try:
            payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            if len(payload) > MAX_RECORD_BYTES:
                raise VaultError('record_too_large')
            plaintext = (f'{{"version":1,"record_id":"{record_id}","data":'.encode('ascii')
                         + payload + b'}')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise VaultError('invalid_record') from None
        with _storage_errors(), self._directory() as directory:
            cipher = self._fernet(directory)
            self._host_id(directory)
            self._atomic_write(directory, f'{record_id}.json.enc', cipher.encrypt(plaintext))

    def delete(self, record_id):
        record_id = self._record_name(record_id)
        with _storage_errors(), self._directory() as directory:
            self._fernet(directory)
            self._host_id(directory)
            name = f'{record_id}.json.enc'
            self._check_destination(directory, name)
            try:
                os.unlink(name, dir_fd=directory)
            except FileNotFoundError:
                return
            os.fsync(directory)

    @contextmanager
    def lock(self, record_id):
        record_id = self._record_name(record_id)
        with self._directory() as directory:
            with _storage_errors():
                self._fernet(directory)
                self._host_id(directory)
            with self._file_lock(directory, f'.{record_id}.lock'):
                yield
