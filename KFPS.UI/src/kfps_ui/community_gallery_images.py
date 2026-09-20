"""Lazy, bounded in-memory Community thumbnails. No credentials in image URLs."""
from collections import OrderedDict
from threading import RLock

from PySide6.QtCore import QObject, Signal, QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class ImageRequests(QObject):
    requested = Signal(str)


class GalleryImages(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.events = ImageRequests()
        self._images = OrderedDict()
        self._bytes = 0
        self._lock = RLock()
        self.maximum_bytes = 48 * 1024 * 1024

    def clear(self):
        with self._lock:
            self._images.clear()
            self._bytes = 0

    def put(self, key, image):
        with self._lock:
            old = self._images.pop(key, None)
            if old is not None:
                self._bytes -= old.sizeInBytes()
            self._images[key] = image
            self._bytes += image.sizeInBytes()
            while self._bytes > self.maximum_bytes and self._images:
                _, old = self._images.popitem(last=False)
                self._bytes -= old.sizeInBytes()

    def requestImage(self, ident, size, requested_size):
        key = ident.split("?", 1)[0]
        with self._lock:
            image = self._images.get(key)
            if image is not None:
                self._images.move_to_end(key)
                result = QImage(image)
            else:
                result = QImage(1, 1, QImage.Format_RGBA8888)
                result.fill(Qt.transparent)
        if image is None:
            self.events.requested.emit(key)
        size.setWidth(result.width())
        size.setHeight(result.height())
        return result
