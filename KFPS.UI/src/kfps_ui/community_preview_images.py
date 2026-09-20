"""Lazy local thumbnails: only visible QML delegates decode images."""
import json
from contextlib import closing
import re
import sqlite3
import threading
import time

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class PreviewImages(QQuickImageProvider):
    def __init__(self, database):
        super().__init__(QQuickImageProvider.Image)
        self.database = str(database)
        self._lock = threading.Lock()
        self._access = ("", 0, 0)

    def set_access(self, username, offset, generation):
        with self._lock:
            self._access = (username, offset, generation)

    def requestImage(self, ident, size, requestedSize):
        image = QImage()
        match = re.fullmatch(r"(\d+)/([0-9a-f]{32})", ident)
        with self._lock:
            username, offset, generation = self._access
        if not match or int(match[1]) != generation:
            return image
        now = time.time() + offset
        try:
            with closing(sqlite3.connect(self.database, timeout=1)) as db:
                row = db.execute("""SELECT preview,metadata FROM artwork WHERE id=? AND state='published'
                    AND (starts IS NULL OR starts<=?) AND (ends IS NULL OR ends>?)""", (match[2], now, now)).fetchone()
                if row and not db.execute("SELECT 1 FROM ignored WHERE account=? AND creator=?",
                                          (username, json.loads(row[1])["creator"])).fetchone():
                    image = QImage.fromData(bytes(row[0] or b""))
        except (OSError, ValueError, sqlite3.Error):
            pass
        with self._lock:
            if self._access != (username, offset, generation):
                return QImage()
        if not image.isNull():
            bounds = requestedSize if requestedSize.isValid() else QSize(400, 260)
            image = image.scaled(bounds.boundedTo(QSize(560, 400)), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image
