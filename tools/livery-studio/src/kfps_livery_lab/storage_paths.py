"""Trusted roots, bounded ordinary files and a cross-process Windows storage lock."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
import time


class StorageError(ValueError):
    def __init__(self, status, message, *, code=None, entry=None):
        super().__init__(message)
        self.status, self.code, self.entry = status, code, entry

    def response(self):
        result = {"error": str(self)}
        if self.code:
            result["code"] = self.code
        if self.entry is not None:
            result["entry"] = self.entry
        return result


def ordinary(path, *, directory=None, missing=False):
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise StorageError(404, "The local item is no longer available.")
    except OSError as exc:
        raise StorageError(503, "Local storage is unavailable.") from exc
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
            or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
            or (directory is True and not stat.S_ISDIR(info.st_mode))
            or (directory is False and not stat.S_ISREG(info.st_mode))):
        raise StorageError(409, "Storage links, aliases and special files are not supported.")
    return info


class SafeRoot:
    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        if str(self.root).startswith("\\\\"):
            raise StorageError(422, "Managed storage requires a local filesystem root.")
        self.check(self.root, missing=True, directory=True)

    def check(self, path, *, directory=None, missing=False):
        path = Path(path)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise StorageError(422, "The path is outside the selected library.") from exc
        # Check ancestors before resolve(), which would otherwise erase evidence
        # of junctions or symlinks. No browser path is ever passed as an absolute.
        for ancestor in reversed(path.parents):
            ordinary(ancestor, directory=True, missing=True)
        return ordinary(path, directory=directory, missing=missing)

    def mkdir(self, path):
        self.check(path, directory=True, missing=True)
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(503, "The storage directory could not be created.") from exc
        self.check(path, directory=True)

    def read(self, path, maximum):
        before = self.check(path, directory=False)
        if before.st_size > maximum:
            raise StorageError(413, "The selected file exceeds its size limit.")
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                current = self.check(path, directory=False)
                if ((before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
                        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
                        or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1):
                    raise StorageError(409, "The selected file changed while opening.")
                data = stream.read(maximum + 1)
        except OSError as exc:
            raise StorageError(503, "The selected file could not be read.") from exc
        if len(data) > maximum:
            raise StorageError(413, "The selected file exceeds its size limit.")
        if len(data) != opened.st_size:
            raise StorageError(409, "The selected file changed while reading.")
        return data

    @contextmanager
    def lock(self, *, create=True):
        if create:
            self.mkdir(self.root)
        elif self.check(self.root, directory=True, missing=True) is None:
            yield False
            return
        path = self.root / ".storage.lock"
        self.check(path, directory=False, missing=True)
        descriptor, acquired = None, False
        try:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
            current = self.check(path, directory=False)
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or opened.st_size > 1:
                raise StorageError(409, "The storage lock is not a managed ordinary file.")
            if os.name == "nt":
                import msvcrt
                def acquire():
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                def release():
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                def acquire():
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                def release():
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            deadline = time.monotonic() + 5
            while not acquired:
                try:
                    acquire()
                    acquired = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise StorageError(503, "Storage is busy in another Studio window. Retry shortly.")
                    time.sleep(.02)
            self.check(self.root, directory=True)
            yield True
        except OSError as exc:
            raise StorageError(503, "Managed storage is unavailable.") from exc
        finally:
            if descriptor is not None:
                try:
                    if acquired:
                        release()
                finally:
                    os.close(descriptor)


DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)


def relative_parts(value, *, empty=False):
    if not isinstance(value, str) or len(value) > 1024 or (not value and not empty):
        raise StorageError(422, "Invalid library path.")
    if not value and empty:
        return ()
    parts = value.split("/")
    for part in parts:
        if (part in ("", ".", "..") or len(part) > 255 or part[-1:] in (" ", ".")
                or DEVICE.fullmatch(part) or any(c in '<>:"\\|?*' or ord(c) < 32 or ord(c) == 127 for c in part)):
            raise StorageError(422, "Invalid library path.")
    return tuple(parts)
