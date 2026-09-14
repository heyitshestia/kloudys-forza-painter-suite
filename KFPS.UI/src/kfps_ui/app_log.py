"""Bounded, asynchronous app history. Redaction and disk I/O stay off the UI thread."""
from __future__ import annotations

from logging.handlers import RotatingFileHandler
import logging
import os
from pathlib import Path
import queue
import stat
import threading


class AppLogWriter:
    def __init__(self, runtime: Path):
        self.runtime = Path(runtime)
        self.queue = queue.Queue(maxsize=1024)
        self.stop = threading.Event()
        self.written = 0
        self.dropped = 0
        self.failed = False
        self.thread = threading.Thread(target=self._run, name="app-log-writer", daemon=True)
        self.thread.start()

    def append(self, text):
        if self.stop.is_set():
            return
        try:
            text = str(text)
            self.queue.put_nowait(text if len(text) <= 8192 else "[oversized log line removed]")
        except queue.Full:
            self.dropped += 1

    def status(self):
        return {"written": self.written, "pending": self.queue.qsize(),
                "dropped": self.dropped, "failed": self.failed}

    def _run(self):
        handler = None
        try:
            from .support_logs import _safe
            from .support_report import redact
            root = self.runtime.parent.resolve()
            folder = self.runtime / "app-logs"
            # Validate existing ancestors before creating the owned log folder.
            self.runtime.mkdir(parents=True, exist_ok=True)
            _safe(root, self.runtime)
            if folder.exists():
                _safe(root, folder)
            folder.mkdir(exist_ok=True)
            path = folder / f"app-{os.getpid()}.log"
            for target in (path, path.with_name(path.name + ".1"), path.with_name(path.name + ".2")):
                try:
                    info = _safe(root, target)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError("unsafe log")
                except FileNotFoundError:
                    pass
            handler = RotatingFileHandler(path, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
            # Logging normally swallows I/O errors; expose them to the report.
            handler.handleError = lambda record: setattr(self, "failed", True)
            while not self.stop.is_set() or not self.queue.empty():
                try:
                    text = self.queue.get(timeout=.05)
                except queue.Empty:
                    continue
                try:
                    text = redact(text, 60000) if len(text) <= 60000 else "[oversized log line removed]"
                    handler.emit(logging.LogRecord("kfps-app", logging.INFO, "", 0, text, (), None))
                    if not self.failed:
                        self.written += 1
                finally:
                    self.queue.task_done()
        except Exception:
            self.failed = True
        finally:
            if handler:
                handler.close()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.failed = True
