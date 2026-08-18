from __future__ import annotations

import concurrent.futures
import importlib.util
import platform
import sys

from PySide6.QtCore import QObject, Property, Signal, Slot

from .lifecycle import discard_queued_events


class RuntimeService(QObject):
    changed = Signal()
    _resultReady = Signal(object)

    MODULES = (("Pillow", "PIL"), ("NumPy", "numpy"), ("OpenCV", "cv2"), ("psutil", "psutil"))

    def __init__(self, demo=False, parent=None):
        super().__init__(parent)
        self._closed = False
        self._future = None
        self._checking = False
        self._python = "Checking"
        self._deps = "Checking"
        self._runtime = "Starting"
        self._ready = False
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="runtime-check")
        self._resultReady.connect(self._apply)
        if demo:
            self._python, self._deps, self._runtime, self._ready = "3.12 (OK)", "All good", "Ready", True
        else:
            self.check()

    @Property(str, notify=changed)
    def pythonText(self): return self._python
    @Property(str, notify=changed)
    def dependenciesText(self): return self._deps
    @Property(str, notify=changed)
    def runtimeText(self): return self._runtime
    @Property(bool, notify=changed)
    def ready(self): return self._ready
    @Property(bool, notify=changed)
    def checking(self): return self._checking

    @Slot()
    def check(self):
        if self._closed or self._checking: return
        self._checking = True; self.changed.emit()
        self._future = self._executor.submit(self._work)
        self._future.add_done_callback(self._emit_result)

    def _emit_result(self, future):
        if self._closed:
            return
        try:
            result = future.result()
        except Exception:
            return
        if not self._closed:
            self._resultReady.emit(result)

    @classmethod
    def _work(cls):
        version_ok = sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32
        missing = [label for label, module in cls.MODULES if importlib.util.find_spec(module) is None]
        if platform.system() == "Windows" and importlib.util.find_spec("win32api") is None:
            missing.append("pywin32")
        return {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}" + (" (OK)" if version_ok else " (3.12 required)"),
            "deps": "All good" if not missing else "Missing: " + ", ".join(missing),
            "runtime": "Ready" if version_ok and not missing else "Needs attention",
            "ready": version_ok and not missing,
        }

    @Slot(object)
    def _apply(self, result):
        if self._closed:
            return
        self._python = result["python"]; self._deps = result["deps"]; self._runtime = result["runtime"]; self._ready = result["ready"]
        self._checking = False; self.changed.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._future is not None:
            self._future.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
        discard_queued_events(self)
