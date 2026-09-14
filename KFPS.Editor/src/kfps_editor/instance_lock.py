"""One editor per data directory, including abandoned legacy lock files."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from .bootstrap_log import record_startup


class EditorInstanceLock:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.path = self.runtime / "desktop.lock"
        self.lease = None
        self.qt_lock = None
        self.last_error = None

    def tryLock(self, timeout=0):
        if self.isLocked():
            return False
        if os.name != "nt":
            from PySide6.QtCore import QLockFile
            self.qt_lock = QLockFile(str(self.path))
            self.qt_lock.setStaleLockTime(0)
            if self.qt_lock.tryLock(timeout):
                return True
            if self.qt_lock.error() != QLockFile.LockError.LockFailedError:
                raise RuntimeError("The editor cannot write its startup lock. Check folder access and available disk space. Your saved work has not been changed.")
            return False
        from .windows_lock import acquire_file_lease
        deadline = time.monotonic() + max(0, timeout) / 1000
        while True:
            try:
                lease = acquire_file_lease(self.path, share=1)
                break
            except OSError as error:
                self.last_error = getattr(error, "winerror", None)
                if self.last_error in (32, 33) and time.monotonic() < deadline:
                    time.sleep(min(.05, max(0, deadline - time.monotonic())))
                    continue
                record_startup(self.runtime, "instance-lock-blocked", winerror=self.last_error)
                if self.last_error in (32, 33):
                    return False
                raise RuntimeError("The editor cannot write its startup lock. Check folder access and available disk space. Your saved work has not been changed.") from error
        try:
            previous = lease.read()
            try:
                old_pid = int(previous.splitlines()[0])
            except (ValueError, IndexError):
                old_pid = None
            # Preserve the readable Qt PID/name/hostname format for older editors.
            # None of these fields grants ownership; only the Windows lease does.
            payload = f"{os.getpid()}\n{Path(sys.executable).stem}\n{os.environ.get('COMPUTERNAME', '')}\n\n\n"
            lease.write(payload.encode("utf-8"))
            self.lease = lease
            self.last_error = None
            record_startup(self.runtime, "instance-lock-acquired", previous_pid=old_pid,
                           reused_marker=bool(previous))
            return True
        except Exception:
            lease.Close()
            raise

    def isLocked(self):
        return self.lease is not None or bool(self.qt_lock and self.qt_lock.isLocked())

    def unlock(self):
        if self.lease is not None:
            self.lease.Close()
            self.lease = None
        if self.qt_lock is not None:
            self.qt_lock.unlock()
