"""Private, bounded per-action confirmations shared by Studio hosts, not themes."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import stat
import time

from .model import ValidationError, decode_json
from .prepare import atomic_json

LAB_ROOT = Path(__file__).resolve().parents[2]
MAX_REQUEST_BYTES = 1024
MAX_FILE_BYTES = 4096
LOCK_TIMEOUT_SECONDS = 2.0
ACTIONS = frozenset(('colour.selection.v1', 'colour.all.v1', 'source.open.v1',
                     'source.apply.selection.v1', 'source.apply.all.v1'))


class ConfirmationError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _try_lock(handle):
    handle.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle):
    handle.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ordinary(info, *, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    return (expected(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400
            and (directory or info.st_nlink == 1))


class ConfirmationPreferences:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.path = self.root / 'action-confirmations.json'
        self.lock_path = self.root / 'action-confirmations.lock'
        # Defer disk access to the API so broken optional preferences do not
        # prevent Studio starting. Failed reads never authorize skipping.
        try:
            relative = self.root.relative_to(LAB_ROOT.absolute())
            if not relative.parts or '..' in relative.parts:
                raise ValueError()
        except ValueError as exc:
            raise ConfirmationError(500, 'Confirmation storage must remain inside the isolated workspace.') from exc

    def _check_paths(self):
        current = LAB_ROOT.absolute()
        for segment in self.root.relative_to(current).parts:
            current /= segment
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info, directory=True):
                raise ConfirmationError(500, 'Confirmation storage is redirected or invalid.')
        if not self.root.resolve().is_relative_to(LAB_ROOT.resolve()):
            raise ConfirmationError(500, 'Confirmation storage is outside the isolated workspace.')
        for path in (self.path, self.lock_path):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info):
                raise ConfirmationError(500, 'Confirmation storage is redirected or invalid.')

    @contextmanager
    def _locked(self):
        try:
            self._check_paths()
            self.root.mkdir(parents=True, exist_ok=True)
            flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
            descriptor = os.open(self.lock_path, flags, 0o600)
            with os.fdopen(descriptor, 'r+b') as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info) or info.st_size > 1:
                    raise ConfirmationError(500, 'Confirmation lock storage is invalid.')
                deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        _try_lock(handle)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or time.monotonic() >= deadline:
                            raise
                        time.sleep(.02)
                try:
                    # Byte locks may extend past EOF. Initialize only after
                    # acquisition; another cold host may already own this byte.
                    if os.fstat(handle.fileno()).st_size == 0:
                        handle.write(b'0')
                        handle.flush()
                    self._check_paths()
                    yield
                finally:
                    _unlock(handle)
        except OSError as exc:
            raise ConfirmationError(503, 'Confirmation preferences are unavailable or busy. Confirmations remain required.') from exc

    def _read(self):
        try:
            with self.path.open('rb') as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info):
                    raise ConfirmationError(500, 'Confirmation storage is redirected or invalid.')
                if info.st_size > MAX_FILE_BYTES:
                    raise ValidationError('Oversized preferences.')
                raw = handle.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise ValidationError('Oversized preferences.')
            value = decode_json(raw)
            if (not isinstance(value, dict) or set(value) != {'version', 'skipped'}
                    or type(value['version']) is not int or value['version'] != 1
                    or not isinstance(value['skipped'], list) or len(value['skipped']) > len(ACTIONS)
                    or any(not isinstance(key, str) or key not in ACTIONS for key in value['skipped'])
                    or len(set(value['skipped'])) != len(value['skipped'])):
                raise ValidationError('Invalid preferences.')
            return {'version': 1, 'skipped': sorted(value['skipped'])}
        except FileNotFoundError:
            return {'version': 1, 'skipped': []}
        except ValidationError as exc:
            raise ConfirmationError(409, 'Confirmation preferences are corrupt or incompatible and were not replaced. Confirmations remain required.') from exc

    def get(self):
        with self._locked():
            return self._read()

    def update(self, value):
        reset = isinstance(value, dict) and set(value) == {'reset'} and value['reset'] is True
        if not reset and (not isinstance(value, dict) or set(value) != {'action', 'skip'}
                          or not isinstance(value['action'], str) or value['action'] not in ACTIONS
                          or type(value['skip']) is not bool):
            raise ConfirmationError(422, 'Expected a supported action and boolean skip, or reset: true.')
        with self._locked():
            current = self._read()
            skipped = set(current['skipped'])
            if reset:
                skipped.clear()
            elif value['skip']:
                skipped.add(value['action'])
            else:
                skipped.discard(value['action'])
            result = {'version': 1, 'skipped': sorted(skipped)}
            # A separate stable lock survives replacement of the JSON inode.
            # Reload/merge/replace is one cross-process transaction.
            atomic_json(self.path, result)
            return result
