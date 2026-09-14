"""Bound raw startup-log retention only when no process owns the append file."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import time
import json
from datetime import datetime, timezone

if os.name == "nt":
    from pywintypes import error as WindowsFileError
else:
    WindowsFileError = OSError

MAX_BYTES = 2 * 1024 * 1024


def record_startup(runtime, event, **fields):
    """Low-volume lifecycle evidence; never called by drawing/frame callbacks."""
    try:
        with open_desktop_log(Path(runtime)) as stream:
            stream.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(),
                                     "pid": os.getpid(), "event": event, **fields}) + "\n")
    except OSError:
        pass


def _ordinary(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    return path.is_file() and info.st_nlink == 1 and not (getattr(info, "st_file_attributes", 0) & 0x400)


def _tail(path):
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - MAX_BYTES))
        return stream.read(MAX_BYTES)


def _replace_tail(path, payload):
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_desktop_log(runtime: Path):
    """No rotation during editing. Sharing denial is a healthy active-writer case."""
    path = Path(runtime) / "desktop.log"
    handle = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not all(_ordinary(item) for item in (path, path.with_name("desktop.log.1"), path.with_name("desktop.log.2"))):
            return "unsafe-path"
        if not path.exists() or path.stat().st_size <= MAX_BYTES:
            return "within-budget"
        if os.name != "nt":
            return "unsupported-platform"
        import win32con
        import win32file
        # Deny readers/writers while preserving deletion sharing for replacement
        # semantics. Existing inherited stdout/stderr handles make this fail.
        handle = win32file.CreateFile(str(path), win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            win32con.FILE_SHARE_DELETE, None, win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_OPEN_REPARSE_POINT, None)
        info = win32file.GetFileInformationByHandle(handle)
        if info[0] & (win32con.FILE_ATTRIBUTE_DIRECTORY | win32con.FILE_ATTRIBUTE_REPARSE_POINT) or info[7] != 1:
            return "unsafe-path"
        size = win32file.GetFileSize(handle)
        win32file.SetFilePointer(handle, max(0, size - MAX_BYTES), win32con.FILE_BEGIN)
        _, tail = win32file.ReadFile(handle, min(size, MAX_BYTES))
        previous = path.with_name("desktop.log.1")
        if previous.exists():
            _replace_tail(path.with_name("desktop.log.2"), _tail(previous))
        _replace_tail(previous, tail)
        # Do not discard the active file until the bounded newest tail is durable.
        win32file.SetFilePointer(handle, 0, win32con.FILE_BEGIN)
        win32file.SetEndOfFile(handle)
        win32file.FlushFileBuffers(handle)
        return "rotated"
    except (OSError, WindowsFileError) as error:
        return "in-use" if getattr(error, "winerror", None) in {32, 33} else "unavailable"
    finally:
        if handle is not None:
            handle.Close()


def open_desktop_log(runtime: Path):
    state = prepare_desktop_log(runtime)
    path = Path(runtime) / "desktop.log"
    if state != "unsafe-path":
        for attempt in range(5):
            try:
                return path.open("a", encoding="utf-8")
            except OSError as error:
                if getattr(error, "winerror", None) not in {32, 33} or attempt == 4:
                    break
                time.sleep(.05)
    # Startup must not fail because raw diagnostic storage is unavailable. Native
    # readiness/error markers and structured diagnostics retain their own paths.
    return open(os.devnull, "w", encoding="utf-8")
