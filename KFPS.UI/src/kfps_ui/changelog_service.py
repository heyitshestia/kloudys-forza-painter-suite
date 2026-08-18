from __future__ import annotations

import re
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .models import DictListModel


class ChangelogService(QObject):
    changed = Signal()

    URL = "https://raw.githubusercontent.com/heyitshestia/kloudys-forza-painter-suite/main/CHANGELOG.md"

    def __init__(self, path: Path, auto_refresh=False, parent=None):
        super().__init__(parent)
        self._closed = False
        self._path = Path(path)
        self._model = DictListModel(["version", "date", "summary", "details"])
        self._refreshing = False
        self._status = "Showing installed patch notes."
        self._network = QNetworkAccessManager(self)
        self._network.finished.connect(self._finished)
        self._load_local()
        self._initial_timer = QTimer(self)
        self._initial_timer.setSingleShot(True)
        self._initial_timer.setInterval(900)
        self._initial_timer.timeout.connect(self.refresh)
        if auto_refresh:
            self._initial_timer.start()


    @Property(QObject, constant=True)
    def model(self):
        return self._model

    @Property(bool, notify=changed)
    def refreshing(self):
        return self._refreshing

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Slot()
    def refresh(self):
        if self._closed or self._refreshing:
            return
        self._refreshing = True
        self._status = "Refreshing patch notes from GitHub..."
        self.changed.emit()
        request = QNetworkRequest(QUrl(f"{self.URL}?cache={time.time_ns()}"))
        request.setRawHeader(b"User-Agent", b"KFPS-QML/1.0")
        request.setRawHeader(b"Cache-Control", b"no-cache, no-store")
        request.setRawHeader(b"Pragma", b"no-cache")
        request.setTransferTimeout(15_000)
        self._network.get(request)

    def _load_local(self):
        try:
            text = self._path.read_text(encoding="utf-8", errors="replace")
            rows = self._rows_from_text(text)
        except Exception:
            rows = [{"version": "—", "date": "", "summary": "Changelog is unavailable in this package.", "details": ""}]
        self._model.replace(rows)
        self.changed.emit()

    @staticmethod
    def _rows_from_text(text):
        rows = []
        matches = list(re.finditer(r"^##\s+([^\r\n]+)", str(text or ""), flags=re.MULTILINE))
        for i, match in enumerate(matches[:30]):
            version = match.group(1).strip()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            bullets = [
                re.sub(r"^[-*]\s*", "", line).strip()
                for line in text[match.end():end].splitlines()
                if line.strip().startswith(("-", "*"))
            ]
            if not bullets:
                continue
            rows.append({
                "version": version,
                "date": "Current" if i == 0 else "",
                "summary": bullets[0],
                "details": "\n".join(f"- {bullet}" for bullet in bullets[1:]),
            })
        return rows

    def _finished(self, reply: QNetworkReply):
        if self._closed:
            reply.deleteLater()
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._status = f"Patch-note refresh failed: {reply.errorString()}"
                return
            text = bytes(reply.readAll()).decode("utf-8")
            rows = self._rows_from_text(text)
            if not rows:
                raise ValueError("GitHub returned an invalid changelog")
            self._model.replace(rows)
            self._status = "Patch notes refreshed from GitHub."
        except Exception as exc:
            self._status = f"Patch-note refresh failed: {exc}"
        finally:
            self._refreshing = False
            reply.deleteLater()
            self.changed.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._initial_timer.stop()
        for reply in self._network.findChildren(QNetworkReply):
            reply.abort()
