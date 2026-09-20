"""Bounded, metadata-free copies of uploader-provided livery photographs."""
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from .community_preview_store import PreviewError


def read_photos(paths):
    if not paths or len(paths) > 3:
        raise PreviewError("Choose one to three livery photos.")
    result = []
    for value in paths:
        path = Path(value).resolve(strict=True)
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise PreviewError("Choose PNG, JPEG or WebP photos.")
        with path.open("rb") as source:
            raw = source.read(20 * 1024 * 1024 + 1)
        if len(raw) > 20 * 1024 * 1024:
            raise PreviewError("Each livery photo must be 20 MiB or smaller.")
        data = QBuffer()
        data.setData(raw)
        data.open(QIODevice.ReadOnly)
        reader = QImageReader(data)
        reader.setAutoTransform(True)
        if bytes(reader.format()).lower() not in (b"png", b"jpeg", b"webp"):
            raise PreviewError("The file must contain a PNG, JPEG or WebP photo.")
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 64_000_000:
            raise PreviewError("The photo is unreadable or exceeds 64 megapixels.")
        if max(size.width(), size.height()) > 1920:
            reader.setScaledSize(size.scaled(QSize(1920, 1920), Qt.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            raise PreviewError("The livery photo could not be decoded.")
        if max(image.width(), image.height()) > 1920:
            image = image.scaled(1920, 1920, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # A fresh pixel-only image strips EXIF, location, text and source metadata.
        image = image.convertToFormat(QImage.Format_RGBA8888)
        clean = QImage(image.constBits(), image.width(), image.height(), image.bytesPerLine(), QImage.Format_RGBA8888).copy()
        output = QBuffer()
        output.open(QIODevice.WriteOnly)
        if not clean.save(output, "PNG"):
            raise PreviewError("The livery photo could not be prepared.")
        result.append(bytes(output.data()))
    return result
