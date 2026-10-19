# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Private, bounded pilot evidence; no database or credential persistence."""

from contextlib import contextmanager
import errno
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import stat
from uuid import uuid4

from .client import PilotError

try:
    import fcntl
except ImportError:
    fcntl = None


MAX_REPORT_BYTES = 2 * 1024 * 1024


def _json_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


@contextmanager
def _storage_errors():
    try:
        yield
    except OSError:
        raise PilotError("storage_error") from None


class PilotStore:
    """One atomic report per opaque key, protected by an explicit caller lock."""

    def __init__(self, root):
        self.root = Path(os.path.abspath(root))

    def __repr__(self):
        return "PilotStore()"

    def path(self, key):
        """Return the hashed report location for display; do not touch storage."""
        return self.root / (self._name(key) + ".json")

    @staticmethod
    def _name(key):
        if not isinstance(key, str) or not key or len(key) > 2048:
            raise PilotError("invalid_storage_key")
        try:
            return sha256(key.encode("utf-8")).hexdigest()
        except UnicodeError:
            raise PilotError("invalid_storage_key") from None

    @staticmethod
    def _private(info, *, directory=False):
        correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not correct_type or (not directory and info.st_nlink != 1):
            raise PilotError("unsafe_storage_path")
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
            raise PilotError("unsafe_storage_permissions")

    @contextmanager
    def _directory(self, *, create=False):
        if os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW"):
            raise PilotError("unsupported_platform")
        private_boundary = False
        for path in [*reversed(self.root.parents), self.root]:
            try:
                info = path.lstat()
            except FileNotFoundError:
                if not create:
                    yield None
                    return
                try:
                    path.mkdir(mode=0o700)
                except FileExistsError:
                    pass
                info = path.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise PilotError("unsafe_storage_path")
            if path == self.root:
                self._private(info, directory=True)
            else:
                sticky_temporary = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
                if (info.st_uid not in {0, os.getuid()}
                        or (info.st_mode & 0o022 and not private_boundary and not sticky_temporary)):
                    raise PilotError("unsafe_storage_permissions")
                private_boundary |= info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self._private(os.fstat(descriptor), directory=True)
            yield descriptor
        finally:
            os.close(descriptor)

    def _file(self, directory, name, *, create=False):
        flags = os.O_RDWR | os.O_CREAT if create else os.O_RDONLY
        try:
            descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise PilotError("unsafe_storage_path") from None
            raise
        try:
            self._private(os.fstat(descriptor))
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    @contextmanager
    def lock(self, key):
        name = self._name(key)
        with _storage_errors(), self._directory(create=True) as directory:
            descriptor = self._file(directory, f".{name}.lock", create=True)
            try:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in {errno.EACCES, errno.EAGAIN}:
                        raise PilotError("pilot_busy") from None
                    raise
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def load(self, key):
        name = self._name(key) + ".json"
        with _storage_errors(), self._directory() as directory:
            if directory is None:
                return None
            try:
                descriptor = self._file(directory, name)
            except FileNotFoundError:
                return None
            with os.fdopen(descriptor, "rb") as source:
                data = source.read(MAX_REPORT_BYTES + 1)
            if len(data) > MAX_REPORT_BYTES:
                raise PilotError("report_limit")
            try:
                report = json.loads(data.decode("utf-8"), parse_constant=_json_number,
                                    parse_float=_json_number)
                if not isinstance(report, dict):
                    raise ValueError
            except (ValueError, UnicodeError, RecursionError):
                raise PilotError("invalid_report") from None
            return report

    def save(self, key, report):
        name = self._name(key) + ".json"
        try:
            if not isinstance(report, dict):
                raise ValueError
            data = json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise PilotError("invalid_report") from None
        if len(data) > MAX_REPORT_BYTES:
            raise PilotError("report_limit")
        with _storage_errors(), self._directory(create=True) as directory:
            self._check_destination(directory, name)
            temporary = f".tmp-{uuid4().hex}"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            try:
                with os.fdopen(descriptor, "wb") as destination:
                    self._private(os.fstat(destination.fileno()))
                    destination.write(data)
                    destination.flush()
                    os.fsync(destination.fileno())
                self._check_destination(directory, name)
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        return self.path(key)

    def _check_destination(self, directory, name):
        try:
            descriptor = self._file(directory, name)
        except FileNotFoundError:
            return
        os.close(descriptor)
