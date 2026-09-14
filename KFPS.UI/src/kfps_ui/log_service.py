from __future__ import annotations

import queue
from collections import deque
import threading
from datetime import datetime

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .models import DictListModel


class LogService(QObject):
    textChanged = Signal()
    statusChanged = Signal()

    def __init__(self, parent=None, *, runtime_root=None):
        super().__init__(parent)
        self._closed = False
        self._model = DictListModel(["timestamp", "text", "level", "line"])
        self._pending: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        self._lines: list[str] = []
        self._status = "Ready"
        self._diagnostic_lines = deque()
        self._diagnostic_chars = 0
        self._diagnostic_lock = threading.Lock()
        self._writer = None
        if runtime_root is not None:
            from .app_log import AppLogWriter
            self._writer = AppLogWriter(runtime_root)
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._flush)
        self._timer.start()


    @Property(QObject, constant=True)
    def model(self):
        return self._model

    def append(self, text: str, level: str = "info", update_status: bool = True):
        if self._closed:
            return
        text = str(text or "").rstrip()
        if not text:
            return
        for line in text.splitlines():
            self._pending.put((line, level))
            diagnostic = f"[{datetime.now().isoformat(timespec='milliseconds')}] {line}"
            if len(diagnostic) > 8192:
                diagnostic = "[oversized log line removed]"
            with self._diagnostic_lock:
                self._diagnostic_lines.append(diagnostic)
                self._diagnostic_chars += len(diagnostic)
                while len(self._diagnostic_lines) > 2500 or self._diagnostic_chars > 1024 * 1024:
                    self._diagnostic_chars -= len(self._diagnostic_lines.popleft())
            if self._writer:
                self._writer.append(diagnostic)
        if update_status:
            self._status = text.splitlines()[-1][:130]
            self.statusChanged.emit()

    @Slot(str)
    def log(self, text: str): self.append(text)

    def _flush(self):
        if self._closed:
            return
        rows = []
        for _ in range(48):
            try:
                text, level = self._pending.get_nowait()
            except Exception:
                break
            stamp = datetime.now().strftime("%H:%M:%S")
            line = f"[{stamp}] {text}"
            self._lines.append(line)
            rows.append({"timestamp": stamp, "text": text, "level": level, "line": line})
        if not rows:
            return
        if len(self._lines) > 2500:
            del self._lines[: len(self._lines) - 2500]
        self._model.append_many(rows, max_rows=2500)
        self.textChanged.emit()

    @Property(str, notify=textChanged)
    def plainText(self): return "\n".join(self._lines)
    @Property(str, notify=statusChanged)
    def status(self): return self._status

    def diagnostic_snapshot(self):
        with self._diagnostic_lock:
            text = "\n".join(self._diagnostic_lines)
        return text, self._writer.status() if self._writer else {"enabled": False}

    @Slot()
    def clear(self):
        self._lines.clear(); self._model.replace([]); self.textChanged.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        if self._writer:
            self._writer.close()
