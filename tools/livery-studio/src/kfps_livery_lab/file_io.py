"""Windows filesystem paths, kept separate from URLs and stored logical paths."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import tempfile
import time


def logical_path(path):
    value = os.fspath(path)
    if os.name == "nt":
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
            if not re.match(r"^[A-Za-z]:\\", value):
                raise ValueError("Windows device paths are not supported.")
        if value.startswith(("\\\\.\\", "\\??\\")):
            raise ValueError("Windows device paths are not supported.")
        for spelling in (value, os.path.abspath(value)):
            parsed = Path(spelling)
            if parsed.drive and not parsed.root:
                raise ValueError("Drive-relative paths are not supported.")
            for part in parsed.parts[1 if parsed.anchor else 0:]:
                if part not in (".", "..") and (
                        part.endswith((" ", ".")) or any(c in '<>:"|?*\0' for c in part)
                        or re.fullmatch(r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)):
                    raise ValueError("Ambiguous Windows filesystem path.")
    return Path(os.path.abspath(value))


def io_path(path):
    """For filesystem calls only; callers still enforce ownership/containment."""
    path = logical_path(path)
    if os.name != "nt":
        return path
    # Validate before abspath: Win32 may otherwise erase a trailing dot/space.
    value = str(path)
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    if not re.match(r"^[A-Za-z]:\\", value):
        raise ValueError("An absolute filesystem path is required.")
    return Path("\\\\?\\" + value)


def resolved_path(path, *, strict=False):
    return logical_path(io_path(path).resolve(strict=strict))


@contextmanager
def atomic_stream(path):
    """Exclusive, same-directory staging with a bounded name and atomic replace."""
    destination = io_path(path)
    descriptor, name = tempfile.mkstemp(prefix=".k-", suffix=".tmp", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if os.fstat(stream.fileno()).st_nlink != 1:
                raise ValueError("The staging file is not exclusive.")
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(5):
            try:
                os.replace(temporary, destination)
                break
            except PermissionError as error:
                if os.name != "nt" or getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 4:
                    raise
                # Windows may briefly retain a replaced file's delete-pending
                # handle. Never fall back to deleting the published destination.
                time.sleep(.01 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)
