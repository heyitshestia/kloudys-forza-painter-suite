from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject


def discard_queued_events(receiver: QObject) -> None:
    QCoreApplication.removePostedEvents(receiver)
