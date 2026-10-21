"""Private, bounded preview quality shared by Studio hosts, never export settings."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import time

from .confirmation_preferences import _ordinary, _try_lock, _unlock
from .model import DEFAULT_PREVIEW_QUALITY, ValidationError, decode_json, validate_preview_quality
from .prepare import LAB_ROOT, atomic_json

MAX_REQUEST_BYTES = 1024
MAX_FILE_BYTES = 4096
LOCK_TIMEOUT_SECONDS = 2.0


class PreviewError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class PreviewPreferences:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.path = self.root / "preview-quality.json"
        self.lock_path = self.root / "preview-quality.lock"
        try:
            relative = self.root.relative_to(LAB_ROOT.absolute())
            if not relative.parts or ".." in relative.parts or ".." in Path(root).parts:
                raise ValueError()
        except ValueError as exc:
            raise PreviewError(500, "Preview storage must remain inside the isolated workspace.") from exc

    def _check_paths(self):
        current = LAB_ROOT.absolute()
        for part in self.root.relative_to(current).parts:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info, directory=True):
                raise PreviewError(500, "Preview storage is redirected or invalid.")
        if not self.root.resolve().is_relative_to(LAB_ROOT.resolve()):
            raise PreviewError(500, "Preview storage is outside the isolated workspace.")
        for path in (self.path, self.lock_path):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info):
                raise PreviewError(500, "Preview storage is redirected or invalid.")

    def _read(self):
        try:
            with self.path.open("rb") as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info):
                    raise PreviewError(500, "Preview storage is redirected or invalid.")
                if info.st_size > MAX_FILE_BYTES:
                    raise ValidationError("Oversized preference.")
                raw = handle.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise ValidationError("Oversized preference.")
            value = decode_json(raw)
            if (not isinstance(value, dict) or set(value) != {"version", "quality"}
                    or type(value["version"]) is not int or value["version"] != 1):
                raise ValidationError("Invalid preference.")
            quality = validate_preview_quality(value["quality"])
            return {"version": 1, "quality": quality}
        except FileNotFoundError:
            return {"version": 1, "quality": DEFAULT_PREVIEW_QUALITY}
        except ValidationError as exc:
            raise PreviewError(409, "Preview preferences are corrupt or incompatible and were not replaced.") from exc

    @contextmanager
    def _locked(self):
        try:
            self._check_paths()
            self.root.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "r+b") as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info) or info.st_size > 1:
                    raise PreviewError(500, "Preview lock storage is invalid.")
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
                    # The stable byte lock survives JSON replacement. Cold writers
                    # initialize it only after acquiring the cross-process lock.
                    if os.fstat(handle.fileno()).st_size == 0:
                        handle.write(b"0")
                        handle.flush()
                    self._check_paths()
                    yield
                finally:
                    _unlock(handle)
        except OSError as exc:
            raise PreviewError(503, "Preview preferences are unavailable or busy.") from exc

    def get(self):
        # Atomic replacement makes GET read-only, including a missing store.
        try:
            self._check_paths()
            return self._read()
        except OSError as exc:
            raise PreviewError(503, "Preview preferences are unavailable or busy.") from exc

    def update(self, value):
        if not isinstance(value, dict) or set(value) != {"quality"}:
            raise PreviewError(422, "Expected exactly quality: fast, balanced or sharp.")
        try:
            quality = validate_preview_quality(value["quality"])
        except ValidationError as exc:
            raise PreviewError(422, str(exc)) from exc
        result = {"version": 1, "quality": quality}
        with self._locked():
            self._read()  # Never overwrite corrupt or future-version preferences.
            atomic_json(self.path, result)
        return result
