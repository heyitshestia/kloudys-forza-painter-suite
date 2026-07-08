from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class AnnouncementService(QObject):
    changed = Signal()

    DEFAULT_URL = "https://gist.githubusercontent.com/heyitshestia/e74fc2a8a94d8729e8f38cfe0f627790/raw/kfps-live-status.json"

    def __init__(self, demo: bool = False, parent=None):
        super().__init__(parent)
        self._url = os.environ.get("KFPS_ANNOUNCEMENT_URL", self.DEFAULT_URL).strip()
        self._enabled = False
        self._title = ""
        self._message = ""
        self._severity = "info"
        self._link = ""
        self._checking = False
        self._network = QNetworkAccessManager(self)
        self._network.finished.connect(self._finished)
        self._poll = QTimer(self)
        self._poll.setInterval(60_000)
        self._poll.timeout.connect(self.checkNow)
        self._poll.start()
        if not demo:
            QTimer.singleShot(250, self.checkNow)
            QTimer.singleShot(8_000, self.checkNow)

    @Property(bool, notify=changed)
    def enabled(self):
        return self._enabled and bool(self.displayText)

    @Property(str, notify=changed)
    def title(self):
        return self._title

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(str, notify=changed)
    def severity(self):
        return self._severity

    @Property(str, notify=changed)
    def link(self):
        return self._link

    @Property(bool, notify=changed)
    def checking(self):
        return self._checking

    @Property(str, notify=changed)
    def displayText(self):
        parts = [part for part in (self._title.strip(), self._message.strip()) if part]
        return "  |  ".join(parts)

    @Slot()
    def checkNow(self):
        if self._checking or not self._url:
            return
        self._checking = True
        self.changed.emit()
        separator = "&" if "?" in self._url else "?"
        request = QNetworkRequest(QUrl(f"{self._url}{separator}t={int(time.time())}"))
        request.setRawHeader(b"User-Agent", b"KFPS-QML/1.0")
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute, QNetworkRequest.CacheLoadControl.AlwaysNetwork)
        self._network.get(request)

    def _finished(self, reply: QNetworkReply):
        changed = False
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            enabled = bool(payload.get("enabled", False))
            title = str(payload.get("title", "") or "").strip()
            message = str(payload.get("message", "") or "").strip()
            severity = str(payload.get("severity", "info") or "info").strip().lower()
            if severity not in {"info", "warning", "critical", "success"}:
                severity = "info"
            link = str(payload.get("link", "") or "").strip()
            values = (enabled, title, message, severity, link)
            old = (self._enabled, self._title, self._message, self._severity, self._link)
            if values != old:
                self._enabled, self._title, self._message, self._severity, self._link = values
                changed = True
        except Exception:
            pass
        finally:
            self._checking = False
            reply.deleteLater()
            if changed:
                self.changed.emit()
            else:
                self.changed.emit()
