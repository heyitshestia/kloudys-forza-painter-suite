from __future__ import annotations

import queue
from datetime import datetime

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .models import DictListModel


class LogService(QObject):
    textChanged = Signal()
    statusChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._closed = False
        self._model = DictListModel(["timestamp", "text", "level", "line"])
        self._pending: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        self._lines: list[str] = []
        self._status = "Ready"
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

    @Slot()
    def clear(self):
        self._lines.clear(); self._model.replace([]); self.textChanged.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
