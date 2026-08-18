from __future__ import annotations

import re
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .qt_utils import is_remote_newer


class VersionService(QObject):
    changed = Signal()

    URL = "https://raw.githubusercontent.com/heyitshestia/kloudys-forza-painter-suite/main/VERSION"

    def __init__(self, version_file: Path, demo=False, parent=None):
        super().__init__(parent)
        self._closed = False
        try:
            self._local = version_file.read_text(encoding="utf-8").strip() or "unknown"
        except Exception:
            self._local = "unknown"
        self._latest = self._local
        self._available = False
        self._checking = False
        self._check_succeeded = False
        self._check_status = "Waiting to check GitHub."
        self._blink = True
        self._network = QNetworkAccessManager(self)
        self._network.finished.connect(self._finished)
        self._poll = QTimer(self); self._poll.setInterval(300_000); self._poll.timeout.connect(self.checkNow); self._poll.start()
        self._blink_timer = QTimer(self); self._blink_timer.setInterval(650); self._blink_timer.timeout.connect(self._tick); self._blink_timer.start()
        self._initial_timer = QTimer(self); self._initial_timer.setSingleShot(True); self._initial_timer.setInterval(500); self._initial_timer.timeout.connect(self.checkNow)
        if not demo:
            self._initial_timer.start()

    @Property(str, notify=changed)
    def localVersion(self): return self._local
    @Property(str, notify=changed)
    def latestVersion(self): return self._latest
    @Property(bool, notify=changed)
    def updateAvailable(self): return self._available
    @Property(bool, notify=changed)
    def checking(self): return self._checking
    @Property(str, notify=changed)
    def checkStatus(self): return self._check_status
    @Property(bool, notify=changed)
    def checkSucceeded(self): return self._check_succeeded
    @Property(bool, notify=changed)
    def blinkOn(self): return self._blink
    @Property(str, notify=changed)
    def displayText(self): return f"v{self._local}"

    @Slot()
    def checkNow(self):
        if self._closed or self._checking:
            return
        self._checking = True
        self._check_status = "Checking GitHub for updates..."
        self.changed.emit()
        request = QNetworkRequest(QUrl(f"{self.URL}?cache={time.time_ns()}"))
        request.setRawHeader(b"User-Agent", b"KFPS-QML/1.0")
        request.setRawHeader(b"Cache-Control", b"no-cache, no-store")
        request.setRawHeader(b"Pragma", b"no-cache")
        request.setTransferTimeout(15_000)
        self._network.get(request)

    def _finished(self, reply: QNetworkReply):
        if self._closed:
            reply.deleteLater()
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._check_succeeded = False
                self._check_status = f"Update check failed: {reply.errorString()}"
                return
            remote = bytes(reply.readAll()).decode("utf-8").strip()
            match = re.fullmatch(r"v?(\d+(?:\.\d+){1,3})", remote, flags=re.IGNORECASE)
            if not match:
                raise ValueError("GitHub returned an invalid version file")
            self._latest = match.group(1)
            self._available = is_remote_newer(self._local, self._latest)
            self._check_succeeded = True
            self._check_status = (
                f"Update v{self._latest} is available."
                if self._available
                else f"Up to date with GitHub main (v{self._latest})."
            )
        except Exception as exc:
            self._check_succeeded = False
            self._check_status = f"Update check failed: {exc}"
        finally:
            self._checking = False
            reply.deleteLater()
            self.changed.emit()

    def _tick(self):
        if self._closed:
            return
        if self._available:
            self._blink = not self._blink; self.changed.emit()
        elif not self._blink:
            self._blink = True; self.changed.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._initial_timer.stop(); self._poll.stop(); self._blink_timer.stop()
        for reply in self._network.findChildren(QNetworkReply):
            reply.abort()
